"""Tests for routing service idempotency — _compute_dispatch_id and _dispatch_rule_actions.

Coverage targets:
  - _compute_dispatch_id: determinism, collision resistance, output length,
    SHA-256 derivation correctness
  - _dispatch_rule_actions via RoutingService: skip when DISPATCHED, re-dispatch when
    FAILED, proceed when no existing record

DB is an external-state boundary — AsyncMock simulates it.
Each RoutingAction commits independently — tested via commit call counts.
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.adapters.channel.schemas import DeliveryResult
from src.core.config import Settings
from src.models.routing import RoutingAction, RoutingActionStatus
from src.services.routing import RoutingService, _compute_dispatch_id
from src.services.schemas.routing import RoutingActionDef, RoutingContext, RuleMatchResult

# ---------------------------------------------------------------------------
# Fixed UUIDs — assigned once at module level for stable hash comparisons
# ---------------------------------------------------------------------------

_EMAIL_ID: uuid.UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_RULE_ID: uuid.UUID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_ALT_EMAIL_ID: uuid.UUID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_ALT_RULE_ID: uuid.UUID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_CHANNEL: str = "slack"
_DESTINATION: str = "#engineering"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    """Create a Settings instance with test-safe defaults."""
    defaults: dict[str, object] = {
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "database_url_sync": "postgresql+psycopg2://test:test@localhost/test",
        "jwt_secret_key": "test-secret-key-for-routing-idempotency-tests",
        "routing_vip_senders": "",
        "routing_dashboard_base_url": "http://localhost:3000",
        "routing_snippet_length": 150,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_routing_context(
    email_id: uuid.UUID = _EMAIL_ID,
    *,
    action_slug: str = "reply",
    type_slug: str = "complaint",
    sender_email: str = "customer@example.com",
) -> RoutingContext:
    return RoutingContext(
        email_id=email_id,
        action_slug=action_slug,
        type_slug=type_slug,
        confidence="high",
        sender_email=sender_email,
        sender_domain=sender_email.split("@")[-1],
        subject="Test Subject",
        snippet="Short snippet for testing purposes.",
        sender_name="Test Customer",
    )


def _make_rule_match(
    rule_id: uuid.UUID = _RULE_ID,
    *,
    channel: str = _CHANNEL,
    destination: str = _DESTINATION,
    priority: int = 50,
) -> RuleMatchResult:
    return RuleMatchResult(
        rule_id=rule_id,
        rule_name="Test Rule",
        priority=priority,
        actions=[RoutingActionDef(channel=channel, destination=destination)],
    )


def _make_existing_action(
    *,
    dispatch_id: str,
    status: RoutingActionStatus,
) -> RoutingAction:
    """Build a RoutingAction ORM mock representing an existing DB record."""
    action = MagicMock(spec=RoutingAction)
    action.id = uuid.uuid4()
    action.dispatch_id = dispatch_id
    action.status = status
    return action


def _make_routing_service(
    *,
    adapter: MagicMock | None = None,
    settings: Settings | None = None,
) -> RoutingService:
    """Construct a RoutingService with a mocked channel adapter."""
    if settings is None:
        settings = _make_settings()
    if adapter is None:
        adapter = MagicMock()
    return RoutingService(
        channel_adapters={_CHANNEL: adapter},
        settings=settings,
    )


# ---------------------------------------------------------------------------
# _compute_dispatch_id — pure function tests (no DB, no async)
# ---------------------------------------------------------------------------


class TestComputeDispatchId:
    def test_dispatch_id_deterministic(self) -> None:
        """Same inputs always produce the same dispatch_id."""
        first = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        second = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        assert first == second

    def test_dispatch_id_different_inputs_produce_different_hashes(self) -> None:
        """Different inputs produce distinct dispatch IDs.

        Verifies all four discriminators: email_id, rule_id, channel, destination.
        """
        base = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)

        diff_email = _compute_dispatch_id(_ALT_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        diff_rule = _compute_dispatch_id(_EMAIL_ID, _ALT_RULE_ID, _CHANNEL, _DESTINATION)
        diff_channel = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, "email", _DESTINATION)
        diff_dest = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, "#general")

        assert base != diff_email
        assert base != diff_rule
        assert base != diff_channel
        assert base != diff_dest
        # All four variants are mutually distinct
        assert len({base, diff_email, diff_rule, diff_channel, diff_dest}) == 5

    def test_dispatch_id_is_32_chars(self) -> None:
        """Output is exactly 32 hexadecimal characters."""
        result = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        assert len(result) == 32

    def test_dispatch_id_contains_only_hex_chars(self) -> None:
        """Output is a valid hex string (lowercase letters and digits only)."""
        result = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        assert all(c in "0123456789abcdef" for c in result)

    def test_dispatch_id_uses_sha256(self) -> None:
        """Verify the hash matches independently computed SHA-256[:32]."""
        raw = f"{_EMAIL_ID}:{_RULE_ID}:{_CHANNEL}:{_DESTINATION}"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:32]
        result = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        assert result == expected


# ---------------------------------------------------------------------------
# RoutingService._dispatch_rule_actions — idempotency scenarios
# ---------------------------------------------------------------------------


class TestDispatchIdempotency:
    """Tests for idempotency logic inside _dispatch_rule_actions.

    Strategy: bypass the full route() pipeline by calling the private method
    directly, supplying a mocked DB session and a mocked channel adapter.
    The DB mock simulates the _find_existing_dispatch() query outcome.
    """

    def _expected_dispatch_id(self) -> str:
        return _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)

    def _build_db_mock(self, existing_action: RoutingAction | None) -> AsyncMock:
        """Create an AsyncMock DB session whose execute() returns ``existing_action``."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        # scalar_one_or_none() controls the find-existing-dispatch result
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = existing_action
        db.execute = AsyncMock(return_value=scalar_result)
        return db

    @pytest.mark.asyncio
    async def test_skip_already_dispatched_action(self) -> None:
        """When an existing RoutingAction with DISPATCHED status is found for the
        same dispatch_id, the channel adapter send_notification is NOT called
        and the existing action id is returned.

        Design constraint: idempotency check via DB, never CRM/channel API.
        """
        dispatch_id = self._expected_dispatch_id()
        existing = _make_existing_action(
            dispatch_id=dispatch_id,
            status=RoutingActionStatus.DISPATCHED,
        )
        db = self._build_db_mock(existing)

        adapter = AsyncMock()
        service = _make_routing_service(adapter=adapter)

        context = _make_routing_context()
        match = _make_rule_match()
        email = MagicMock()

        action_ids, dispatched, failed = await service._dispatch_rule_actions(
            context, match, email, db
        )

        # Adapter must NOT have been called — we already dispatched
        adapter.send_notification.assert_not_called()

        # The existing action id is returned and counted as dispatched
        assert existing.id in action_ids
        assert dispatched == 1
        assert failed == 0

    @pytest.mark.asyncio
    async def test_retry_failed_action_allowed(self) -> None:
        """When an existing RoutingAction has FAILED status, re-dispatch IS allowed.

        The adapter send_notification is called and a new success action is recorded.
        """
        dispatch_id = self._expected_dispatch_id()
        existing = _make_existing_action(
            dispatch_id=dispatch_id,
            status=RoutingActionStatus.FAILED,
        )
        db = self._build_db_mock(existing)

        adapter = AsyncMock()
        adapter.send_notification = AsyncMock(
            return_value=DeliveryResult(success=True, message_ts="1234567890.123456")
        )
        service = _make_routing_service(adapter=adapter)

        context = _make_routing_context()
        match = _make_rule_match()
        email = MagicMock()

        action_ids, dispatched, failed = await service._dispatch_rule_actions(
            context, match, email, db
        )

        # Adapter WAS called — FAILED records may be retried
        adapter.send_notification.assert_called_once()

        assert len(action_ids) == 1
        assert dispatched == 1
        assert failed == 0

    @pytest.mark.asyncio
    async def test_no_existing_dispatch_proceeds(self) -> None:
        """When no existing RoutingAction is found, dispatch proceeds normally.

        Verifies happy path: adapter called once, one action_id returned,
        DB commit called for the new RoutingAction (D13 independent commit).
        """
        db = self._build_db_mock(existing_action=None)

        adapter = AsyncMock()
        adapter.send_notification = AsyncMock(
            return_value=DeliveryResult(success=True, message_ts="1111111111.000001")
        )
        service = _make_routing_service(adapter=adapter)

        context = _make_routing_context()
        match = _make_rule_match()
        email = MagicMock()

        action_ids, dispatched, failed = await service._dispatch_rule_actions(
            context, match, email, db
        )

        adapter.send_notification.assert_called_once()
        assert len(action_ids) == 1
        assert dispatched == 1
        assert failed == 0

        # D13: independent commit was issued for the new RoutingAction
        assert db.commit.call_count >= 1

    @pytest.mark.asyncio
    async def test_idempotency_check_db_error_counts_as_failed(self) -> None:
        """When the idempotency DB query raises SQLAlchemyError, the action
        is counted as failed and the adapter is never called.

        External-state failures are captured, not propagated.
        """
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=SQLAlchemyError("DB timeout"))
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        adapter = AsyncMock()
        service = _make_routing_service(adapter=adapter)

        context = _make_routing_context()
        match = _make_rule_match()
        email = MagicMock()

        action_ids, dispatched, failed = await service._dispatch_rule_actions(
            context, match, email, db
        )

        adapter.send_notification.assert_not_called()
        assert action_ids == []
        assert dispatched == 0
        assert failed == 1

    @pytest.mark.asyncio
    async def test_dispatch_id_computed_from_context_and_match(self) -> None:
        """The dispatch_id fed to the idempotency check is computed from
        context.email_id, match.rule_id, action.channel, and action.destination.

        Verifies D8: dispatch_id computation is local — no try/except, no DB.
        """
        db = self._build_db_mock(existing_action=None)

        # Capture the dispatch_id actually used by the service by intercepting
        # _find_existing_dispatch with a spy
        recorded_dispatch_ids: list[str] = []

        async def _spy_find(
            self_inner: RoutingService,
            dispatch_id: str,
            db_inner: object,
        ) -> None:
            recorded_dispatch_ids.append(dispatch_id)
            return None

        adapter = AsyncMock()
        adapter.send_notification = AsyncMock(
            return_value=DeliveryResult(success=True, message_ts="ts-001")
        )
        service = _make_routing_service(adapter=adapter)

        context = _make_routing_context(email_id=_EMAIL_ID)
        match = _make_rule_match(rule_id=_RULE_ID, channel=_CHANNEL, destination=_DESTINATION)
        email = MagicMock()

        with patch.object(RoutingService, "_find_existing_dispatch", new=_spy_find):
            await service._dispatch_rule_actions(context, match, email, db)

        assert len(recorded_dispatch_ids) == 1
        expected = _compute_dispatch_id(_EMAIL_ID, _RULE_ID, _CHANNEL, _DESTINATION)
        assert recorded_dispatch_ids[0] == expected
