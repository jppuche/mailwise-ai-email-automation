"""E2E tests: pipeline partial failure — D13 non-atomic design.

Each test verifies that when a pipeline task fails, the data committed by
the PREVIOUS stage is still preserved in the database.

Architecture notes:
  - Tasks are called via task.run() (sync, bind=True pattern).
  - The NEXT task's .delay() is patched to prevent actual chaining.
  - Failure injection: mock adapter methods raise domain exceptions.
  - DB assertions use asyncio.run() from sync test context.
  - classify_task: LLMConnectionError -> service commits CLASSIFICATION_FAILED,
    then re-raises; task.retry() raises celery.exceptions.Retry.
  - route_task: ChannelDeliveryError silenced per-action by RoutingService;
    all actions fail -> ROUTING_FAILED state; task returns normally (no Retry).
  - pipeline_crm_sync_task: CRMConnectionError at connect() -> bare except ->
    task.retry() raises celery.exceptions.Retry (before service.sync() runs).
  - pipeline_draft_task: LLMConnectionError -> DraftGenerationService silences it
    -> transitions email to DRAFT_FAILED, no Retry raised (terminal task).

D13 verification: previous-stage DB records survive subsequent task failure.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import celery.exceptions
import pytest

from src.adapters.channel.exceptions import ChannelDeliveryError
from src.adapters.crm.exceptions import CRMConnectionError
from src.adapters.llm.exceptions import LLMConnectionError
from src.models.email import EmailState
from tests.e2e.conftest import (
    MockChannelAdapter,
    MockCRMAdapter,
    MockLLMAdapter,
    _make_session_factory,
    cleanup_email,
    get_classification,
    get_crm_sync_record,
    get_draft,
    get_email_state,
    get_routing_actions,
    insert_categories,
    insert_email,
    insert_routing_rule,
)
from tests.factories import (
    ClassificationResultFactory,
    CRMSyncRecordFactory,
    RoutingActionFactory,
)

# ---------------------------------------------------------------------------
# Helper: insert a ClassificationResult into the real DB
# ---------------------------------------------------------------------------


async def _insert_classification(session_factory, email_id, action_cat, type_cat):
    """Insert a ClassificationResult row for the given email and category IDs."""
    record = ClassificationResultFactory(
        email_id=email_id,
        action_category_id=action_cat.id,
        type_category_id=type_cat.id,
    )
    async with session_factory() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


async def _insert_routing_action(session_factory, email_id, rule_id):
    """Insert a RoutingAction row for the given email and rule."""
    action = RoutingActionFactory(email_id=email_id, rule_id=rule_id)
    async with session_factory() as session:
        session.add(action)
        await session.commit()
        await session.refresh(action)
    return action


async def _insert_crm_sync_record(session_factory, email_id):
    """Insert a CRMSyncRecord row for the given email."""
    record = CRMSyncRecordFactory(email_id=email_id)
    async with session_factory() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Test 1: classify_task failure preserves SANITIZED state data
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_classify_failure_preserves_sanitized_state(migrated_db):
    """D13: when classify_task fails, NO ClassificationResult is written.

    The LLM call fails, so:
      - ClassificationService transitions email -> CLASSIFICATION_FAILED.
      - Re-raises LLMConnectionError.
      - classify_task's except Exception calls self.retry() -> raises Retry.
      - No ClassificationResult was created (failure happened before persist).
      - route_task.delay is NOT called.
    """
    from src.tasks.pipeline import classify_task

    session_factory = _make_session_factory()

    # Insert email in SANITIZED state + seed categories
    email = asyncio.run(insert_email(session_factory, state=EmailState.SANITIZED))
    asyncio.run(insert_categories(session_factory, action_slug="support", type_slug="question"))

    email_id = email.id
    email_id_str = str(email_id)

    # Build a MockLLMAdapter whose classify() raises LLMConnectionError
    mock_llm_instance = MockLLMAdapter()
    mock_llm_instance.classify = AsyncMock(
        side_effect=LLMConnectionError("LLM unreachable — test failure")
    )

    try:
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch("src.tasks.pipeline.route_task") as mock_route_delay,
        ):
            mock_route_delay.delay = MagicMock()

            with pytest.raises(celery.exceptions.Retry):
                classify_task.run(email_id_str)

        # State: service committed CLASSIFICATION_FAILED before re-raising
        final_state = asyncio.run(get_email_state(session_factory, email_id))
        assert final_state == EmailState.CLASSIFICATION_FAILED, (
            f"Expected CLASSIFICATION_FAILED, got {final_state}"
        )

        # D13: no ClassificationResult was persisted (failure before persist step)
        classification = asyncio.run(get_classification(session_factory, email_id))
        assert classification is None, "No ClassificationResult should exist when LLM call fails"

        # Chain not called — retry was raised before route_task.delay
        mock_route_delay.delay.assert_not_called()

    finally:
        asyncio.run(cleanup_email(session_factory, email_id))


# ---------------------------------------------------------------------------
# Test 2: route_task failure preserves CLASSIFIED state + ClassificationResult
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_route_failure_preserves_classified_state(migrated_db):
    """D13: when route_task fails (all channel dispatches fail), ClassificationResult survives.

    The Slack adapter's send_notification raises ChannelDeliveryError.
    RoutingService silences channel errors per-action (records FAILED RoutingAction).
    All actions fail -> email transitions to ROUTING_FAILED (no exception raised).
    pipeline_crm_sync_task.delay is NOT called because was_routed=False.

    The ClassificationResult persisted by the previous stage is still in DB.
    """
    from src.tasks.pipeline import route_task

    session_factory = _make_session_factory()

    # Insert email in CLASSIFIED state + categories + ClassificationResult + routing rule
    email = asyncio.run(insert_email(session_factory, state=EmailState.CLASSIFIED))
    action_cat, type_cat = asyncio.run(
        insert_categories(session_factory, action_slug="support", type_slug="question")
    )
    asyncio.run(_insert_classification(session_factory, email.id, action_cat, type_cat))
    asyncio.run(
        insert_routing_rule(
            session_factory,
            action_slug="support",
            channel="slack",
            destination="C_TEST_CHANNEL",
        )
    )

    email_id = email.id
    email_id_str = str(email_id)

    # Build a MockChannelAdapter whose send_notification raises ChannelDeliveryError
    mock_channel_instance = MockChannelAdapter()
    mock_channel_instance.send_notification = AsyncMock(
        side_effect=ChannelDeliveryError("channel_not_found — test failure")
    )

    try:
        with (
            patch(
                "src.adapters.channel.slack.SlackAdapter",
                return_value=mock_channel_instance,
            ),
            # Provide a non-empty slack_bot_token so the adapter is registered
            patch(
                "src.core.config.get_settings",
                return_value=_make_test_settings(slack_bot_token="xoxb-test-token"),
            ),
            patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_delay,
        ):
            mock_crm_delay.delay = MagicMock()

            # route_task does NOT raise Retry — ChannelDeliveryError is silenced
            # by RoutingService; email ends in ROUTING_FAILED
            route_task.run(email_id_str)

        # State: ROUTING_FAILED (all channel dispatches failed)
        final_state = asyncio.run(get_email_state(session_factory, email_id))
        assert final_state in (EmailState.CLASSIFIED, EmailState.ROUTING_FAILED), (
            f"Expected CLASSIFIED or ROUTING_FAILED, got {final_state}"
        )

        # D13: ClassificationResult from previous stage still exists
        classification = asyncio.run(get_classification(session_factory, email_id))
        assert classification is not None, (
            "ClassificationResult must survive route_task failure (D13)"
        )
        assert classification.email_id == email_id

        # Chain not called — was_routed=False means crm_sync not enqueued
        mock_crm_delay.delay.assert_not_called()

    finally:
        asyncio.run(cleanup_email(session_factory, email_id))


# ---------------------------------------------------------------------------
# Test 3: pipeline_crm_sync_task failure preserves RoutingActions
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_crm_sync_failure_preserves_routed_state(migrated_db):
    """D13: when pipeline_crm_sync_task fails, RoutingActions from route_task survive.

    HubSpotAdapter.connect raises CRMConnectionError — this propagates through
    _run_crm_sync's bare except Exception handler, causing task.retry() -> Retry raised
    before any CRMSyncRecord is committed.

    NOTE: We patch connect() (not lookup_contact) because CRMSyncService silences
    CRMAdapterError subclasses in _do_contact_lookup (records as failed op, continues).
    Patching connect() ensures the exception reaches the task-level bare except handler,
    which matches the spec's expected behavior: Retry raised, no CRMSyncRecord created.

    pipeline_draft_task.delay is NOT called.
    RoutingAction records from the previous stage are still in the DB.
    No CRMSyncRecord is created (failure happens before service.sync()).
    """
    from src.tasks.pipeline import pipeline_crm_sync_task

    session_factory = _make_session_factory()

    # Insert a routing rule so RoutingActionFactory has a valid rule_id
    rule = asyncio.run(
        insert_routing_rule(
            session_factory,
            action_slug="support",
            channel="slack",
            destination="C_TEST_CHANNEL",
        )
    )

    # Insert email in ROUTED state + a RoutingAction for it
    email = asyncio.run(insert_email(session_factory, state=EmailState.ROUTED))
    asyncio.run(_insert_routing_action(session_factory, email.id, rule.id))

    email_id = email.id
    email_id_str = str(email_id)

    # Build a MockCRMAdapter whose connect() raises CRMConnectionError
    # (fails before service.sync() is called, so no CRMSyncRecord is written)
    mock_crm_instance = MockCRMAdapter()
    mock_crm_instance.connect = AsyncMock(
        side_effect=CRMConnectionError("HubSpot unreachable — test failure")
    )

    try:
        with (
            patch(
                "src.adapters.crm.hubspot.HubSpotAdapter",
                return_value=mock_crm_instance,
            ),
            patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_delay,
        ):
            mock_draft_delay.delay = MagicMock()

            with pytest.raises(celery.exceptions.Retry):
                pipeline_crm_sync_task.run(email_id_str)

        # State: ROUTED (connect failed before any state transition was committed)
        final_state = asyncio.run(get_email_state(session_factory, email_id))
        assert final_state in (EmailState.ROUTED, EmailState.CRM_SYNC_FAILED), (
            f"Expected ROUTED or CRM_SYNC_FAILED, got {final_state}"
        )

        # D13: RoutingActions from the previous stage still exist
        routing_actions = asyncio.run(get_routing_actions(session_factory, email_id))
        assert len(routing_actions) > 0, (
            "RoutingAction records must survive crm_sync_task failure (D13)"
        )

        # No CRMSyncRecord was committed (failure before service.sync())
        crm_record = asyncio.run(get_crm_sync_record(session_factory, email_id))
        assert crm_record is None, (
            "No CRMSyncRecord should exist when CRM connect fails before sync"
        )

        # Chain not called — Retry was raised, pipeline_draft_task never enqueued
        mock_draft_delay.delay.assert_not_called()

    finally:
        asyncio.run(cleanup_email(session_factory, email_id))


# ---------------------------------------------------------------------------
# Test 4: pipeline_draft_task failure preserves CRMSyncRecord
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_draft_failure_preserves_crm_synced_state(migrated_db):
    """D13: when pipeline_draft_task fails, CRMSyncRecord from crm_sync_task survives.

    LiteLLMAdapter.generate_draft raises LLMConnectionError (not LLMRateLimitError).

    DraftGenerationService.generate() silences LLMConnectionError (not LLMRateLimitError):
      - Transitions email -> DRAFT_FAILED, commits, returns DraftResult.
      - No exception propagates to _run_draft_generation's try block.
      - task.retry() is NOT called (service handled the error internally).

    The important D13 assertion: CRMSyncRecord committed by the previous stage
    (pipeline_crm_sync_task) is still present in the database after draft failure.
    No Draft record is created because the service returned early.

    NOTE: pipeline_draft_task is the terminal task — there is no next task to chain.
    """
    from src.tasks.pipeline import pipeline_draft_task

    session_factory = _make_session_factory()

    # Insert email in CRM_SYNCED state + a CRMSyncRecord for it
    email = asyncio.run(insert_email(session_factory, state=EmailState.CRM_SYNCED))
    asyncio.run(_insert_crm_sync_record(session_factory, email.id))

    email_id = email.id
    email_id_str = str(email_id)

    # Build a MockLLMAdapter whose generate_draft raises LLMConnectionError
    mock_llm_instance = MockLLMAdapter()
    mock_llm_instance.generate_draft = AsyncMock(
        side_effect=LLMConnectionError("LLM unreachable during draft — test failure")
    )

    try:
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch(
                "src.adapters.email.gmail.GmailAdapter",
                return_value=MagicMock(),
            ),
        ):
            # DraftGenerationService silences LLMConnectionError -> returns DraftResult
            # No Retry raised. Task completes without exception.
            pipeline_draft_task.run(email_id_str)

        # State: DRAFT_FAILED (service transitioned and committed before returning)
        final_state = asyncio.run(get_email_state(session_factory, email_id))
        assert final_state == EmailState.DRAFT_FAILED, (
            f"Expected DRAFT_FAILED (service silences LLMConnectionError), got {final_state}"
        )

        # D13: CRMSyncRecord from the previous stage still exists
        crm_record = asyncio.run(get_crm_sync_record(session_factory, email_id))
        assert crm_record is not None, (
            "CRMSyncRecord must survive pipeline_draft_task failure (D13)"
        )
        assert crm_record.email_id == email_id

        # No Draft was committed (failure occurred before draft persist step)
        draft = asyncio.run(get_draft(session_factory, email_id))
        assert draft is None, "No Draft should exist when draft generation fails before persist"

    finally:
        asyncio.run(cleanup_email(session_factory, email_id))


# ---------------------------------------------------------------------------
# Settings factory for route_task test (needs non-empty slack_bot_token)
# ---------------------------------------------------------------------------


def _make_test_settings(*, slack_bot_token: str):
    """Return a Settings-like object with overridden slack_bot_token.

    Uses a real Settings instance from env and overrides slack_bot_token
    so the routing task registers the (mocked) SlackAdapter.

    Implementation: subclass MagicMock with spec from the real Settings
    instance, then copy every field value via model_dump(). This ensures
    all attribute accesses during RoutingService construction succeed.
    """
    from src.core.config import get_settings

    real_settings = get_settings()
    field_values = real_settings.model_dump()
    field_values["slack_bot_token"] = slack_bot_token

    mock_settings = MagicMock(spec=real_settings)
    for field_name, value in field_values.items():
        setattr(mock_settings, field_name, value)

    return mock_settings
