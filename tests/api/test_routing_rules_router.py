"""Unit tests for GET/POST/PUT/DELETE /api/v1/routing-rules/ endpoints.

Pattern:
  - dependency_overrides for auth, DB, and RoutingService
  - mock_db.execute returns MagicMock scalars per query
  - No real DB or Redis
  - Tests document observable HTTP behaviour, not router internals

Tests use assertions (conditionals) only — no try/except in test bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.api.deps import get_routing_service
from src.api.main import app
from src.models.routing import RoutingRule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COND = {"field": "action_category", "operator": "eq", "value": "respond"}
_ACTION = {"channel": "slack", "destination": "#test", "template_id": None}


def _make_mock_rule(
    rule_id: uuid.UUID | None = None,
    name: str = "Test Rule",
    priority: int = 1,
    is_active: bool = True,
) -> MagicMock:
    """Build a MagicMock RoutingRule ORM object."""
    rule = MagicMock(spec=RoutingRule)
    rule.id = rule_id or uuid.uuid4()
    rule.name = name
    rule.is_active = is_active
    rule.priority = priority
    rule.conditions = [_COND]
    rule.actions = [_ACTION]
    rule.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    rule.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return rule


def _scalar_result(obj: object) -> MagicMock:
    """Return a mock execute-result whose scalar_one_or_none() returns *obj*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _scalars_all_result(items: list[object]) -> MagicMock:
    """Return a mock execute-result whose scalars().all() returns *items*."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _scalar_one_result(value: object) -> MagicMock:
    """Return a mock execute-result whose scalar_one() returns *value*."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


# ---------------------------------------------------------------------------
# TestListRules
# ---------------------------------------------------------------------------


class TestListRules:
    """GET /api/v1/routing-rules/ — list all rules (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_gets_200_with_rules(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin user retrieves a list of routing rules."""
        rule = _make_mock_rule()
        mock_db.execute.return_value = _scalars_all_result([rule])

        response = await admin_client.get("/api/v1/routing-rules/")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["name"] == "Test Rule"
        assert body[0]["priority"] == 1
        assert "id" in body[0]

    @pytest.mark.asyncio
    async def test_reviewer_gets_403(self, reviewer_client: AsyncClient) -> None:
        """Reviewer role is not allowed to list routing rules."""
        response = await reviewer_client.get("/api/v1/routing-rules/")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, unauthenticated_client: AsyncClient) -> None:
        """Missing token returns 401."""
        response = await unauthenticated_client.get("/api/v1/routing-rules/")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestCreateRule
# ---------------------------------------------------------------------------


class TestCreateRule:
    """POST /api/v1/routing-rules/ — create a new rule (admin only, 201)."""

    @pytest.mark.asyncio
    async def test_admin_creates_rule_gets_201(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin creates a rule and gets 201 with the created rule in the body."""
        # The router calls db.add(rule) then db.flush(), db.refresh(rule).
        # execute() → scalar_one_or_none=None (no existing rules → priority=1).
        mock_db.execute.return_value = _scalar_result(None)

        # refresh populates server_default timestamps on the ORM object
        async def _refresh_timestamps(obj: object) -> None:
            obj.created_at = datetime(2024, 1, 1, tzinfo=UTC)  # type: ignore[attr-defined]
            obj.updated_at = datetime(2024, 1, 1, tzinfo=UTC)  # type: ignore[attr-defined]

        mock_db.refresh.side_effect = _refresh_timestamps

        payload = {
            "name": "New Rule",
            "is_active": True,
            "conditions": [{"field": "action_category", "operator": "eq", "value": "respond"}],
            "actions": [{"channel": "slack", "destination": "#general"}],
        }
        response = await admin_client.post("/api/v1/routing-rules/", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "New Rule"
        assert body["is_active"] is True
        assert "id" in body
        assert body["priority"] == 1  # MAX=None → next_priority=1

    @pytest.mark.asyncio
    async def test_priority_auto_assigned_as_max_plus_one(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Priority is auto-assigned as MAX(priority)+1 when rules already exist."""
        mock_db.execute.return_value = _scalar_result(5)  # MAX = 5

        async def _refresh_timestamps(obj: object) -> None:
            obj.created_at = datetime(2024, 1, 1, tzinfo=UTC)  # type: ignore[attr-defined]
            obj.updated_at = datetime(2024, 1, 1, tzinfo=UTC)  # type: ignore[attr-defined]

        mock_db.refresh.side_effect = _refresh_timestamps

        payload = {
            "name": "Rule with auto-priority",
            "conditions": [{"field": "action_category", "operator": "eq", "value": "archive"}],
            "actions": [{"channel": "slack", "destination": "#archive"}],
        }
        response = await admin_client.post("/api/v1/routing-rules/", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["priority"] == 6  # 5 + 1

    @pytest.mark.asyncio
    async def test_reviewer_cannot_create_rule(self, reviewer_client: AsyncClient) -> None:
        """Reviewer role cannot create routing rules."""
        payload = {
            "name": "Reviewer Rule",
            "conditions": [{"field": "action_category", "operator": "eq", "value": "respond"}],
            "actions": [{"channel": "slack", "destination": "#general"}],
        }
        response = await reviewer_client.post("/api/v1/routing-rules/", json=payload)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_conditions_gets_422(self, admin_client: AsyncClient) -> None:
        """Empty conditions list fails validation (min_length=1)."""
        payload = {
            "name": "Invalid Rule",
            "conditions": [],
            "actions": [{"channel": "slack", "destination": "#general"}],
        }
        response = await admin_client.post("/api/v1/routing-rules/", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestGetRule
# ---------------------------------------------------------------------------


class TestGetRule:
    """GET /api/v1/routing-rules/{rule_id} — single rule detail (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_gets_rule_by_id(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin fetches an existing rule by UUID."""
        rule_id = uuid.uuid4()
        rule = _make_mock_rule(rule_id=rule_id, name="Specific Rule")
        mock_db.execute.return_value = _scalar_result(rule)

        response = await admin_client.get(f"/api/v1/routing-rules/{rule_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(rule_id)
        assert body["name"] == "Specific Rule"

    @pytest.mark.asyncio
    async def test_missing_rule_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Non-existent rule ID returns 404."""
        mock_db.execute.return_value = _scalar_result(None)

        missing_id = uuid.uuid4()
        response = await admin_client.get(f"/api/v1/routing-rules/{missing_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reviewer_gets_403(self, reviewer_client: AsyncClient) -> None:
        """Reviewer cannot access individual routing rules."""
        response = await reviewer_client.get(f"/api/v1/routing-rules/{uuid.uuid4()}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestUpdateRule
# ---------------------------------------------------------------------------


class TestUpdateRule:
    """PUT /api/v1/routing-rules/{rule_id} — partial update (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_partial_update_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin performs a partial update on name and is_active fields."""
        rule_id = uuid.uuid4()
        rule = _make_mock_rule(rule_id=rule_id)
        mock_db.execute.return_value = _scalar_result(rule)
        mock_db.refresh.return_value = None

        payload = {"name": "Updated Name", "is_active": False}
        response = await admin_client.put(f"/api/v1/routing-rules/{rule_id}", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(rule_id)

    @pytest.mark.asyncio
    async def test_update_missing_rule_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Updating a non-existent rule returns 404."""
        mock_db.execute.return_value = _scalar_result(None)

        payload = {"name": "Ghost Rule"}
        response = await admin_client.put(f"/api/v1/routing-rules/{uuid.uuid4()}", json=payload)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reviewer_cannot_update_rule(self, reviewer_client: AsyncClient) -> None:
        """Reviewer cannot update routing rules."""
        payload = {"name": "Not Allowed"}
        response = await reviewer_client.put(f"/api/v1/routing-rules/{uuid.uuid4()}", json=payload)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestDeleteRule
# ---------------------------------------------------------------------------


class TestDeleteRule:
    """DELETE /api/v1/routing-rules/{rule_id} — delete rule (admin only, 204)."""

    @pytest.mark.asyncio
    async def test_admin_deletes_rule_gets_204(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin deletes an existing rule and receives 204 No Content."""
        rule_id = uuid.uuid4()
        rule = _make_mock_rule(rule_id=rule_id)
        mock_db.execute.return_value = _scalar_result(rule)

        response = await admin_client.delete(f"/api/v1/routing-rules/{rule_id}")

        assert response.status_code == 204
        assert response.content == b""

    @pytest.mark.asyncio
    async def test_delete_missing_rule_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Deleting a non-existent rule returns 404."""
        mock_db.execute.return_value = _scalar_result(None)

        response = await admin_client.delete(f"/api/v1/routing-rules/{uuid.uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reviewer_cannot_delete_rule(self, reviewer_client: AsyncClient) -> None:
        """Reviewer cannot delete routing rules."""
        response = await reviewer_client.delete(f"/api/v1/routing-rules/{uuid.uuid4()}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# TestReorderRules
# ---------------------------------------------------------------------------


class TestReorderRules:
    """PUT /api/v1/routing-rules/reorder — bulk re-prioritize (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_reorders_rules_gets_200(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin reorders two rules; response reflects new priorities."""
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        rule_a = _make_mock_rule(rule_id=id_a, name="Rule A", priority=2)
        rule_b = _make_mock_rule(rule_id=id_b, name="Rule B", priority=1)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [rule_a, rule_b]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        mock_db.execute.return_value = execute_result

        payload = {"ordered_ids": [str(id_a), str(id_b)]}
        response = await admin_client.put("/api/v1/routing-rules/reorder", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        # First in ordered_ids gets priority 1
        assert body[0]["id"] == str(id_a)
        assert body[0]["priority"] == 1
        assert body[1]["id"] == str(id_b)
        assert body[1]["priority"] == 2

    @pytest.mark.asyncio
    async def test_reorder_with_missing_rule_gets_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reorder request with an unknown rule ID returns 404."""
        known_id = uuid.uuid4()
        unknown_id = uuid.uuid4()
        rule = _make_mock_rule(rule_id=known_id)

        scalars_mock = MagicMock()
        # Only one rule found — the second ID is missing
        scalars_mock.all.return_value = [rule]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        mock_db.execute.return_value = execute_result

        payload = {"ordered_ids": [str(known_id), str(unknown_id)]}
        response = await admin_client.put("/api/v1/routing-rules/reorder", json=payload)

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestTestRules
# ---------------------------------------------------------------------------


class TestTestRules:
    """POST /api/v1/routing-rules/test — dry-run evaluation (admin only)."""

    @pytest.mark.asyncio
    async def test_admin_dry_run_gets_200_with_dry_run_flag(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin performs a dry-run and gets dry_run=True in the response."""
        from src.services.schemas.routing import (
            RoutingActionDef,
            RoutingContext,
            RuleMatchResult,
            RuleTestResult,
        )

        email_id = uuid.uuid4()
        rule_id = uuid.uuid4()

        action_def = RoutingActionDef(channel="slack", destination="#general", template_id=None)
        match_result = RuleMatchResult(
            rule_id=rule_id,
            rule_name="Matched Rule",
            priority=1,
            actions=[action_def],
        )
        context = RoutingContext(
            email_id=email_id,
            action_slug="respond",
            type_slug="inquiry",
            confidence="high",
            sender_email="user@example.com",
            sender_domain="example.com",
            subject="Test Subject",
            snippet="Test snippet",
        )
        test_result = RuleTestResult(
            context=context,
            rules_matched=[match_result],
            would_dispatch=[action_def],
            total_actions=1,
            dry_run=True,
        )

        mock_routing_service = AsyncMock()
        mock_routing_service.test_route.return_value = test_result

        app.dependency_overrides[get_routing_service] = lambda: mock_routing_service

        payload = {
            "email_id": str(email_id),
            "action_slug": "respond",
            "type_slug": "inquiry",
            "confidence": "high",
            "sender_email": "user@example.com",
            "sender_domain": "example.com",
            "subject": "Test Subject",
            "snippet": "Test snippet",
        }

        try:
            response = await admin_client.post("/api/v1/routing-rules/test", json=payload)
        finally:
            app.dependency_overrides.pop(get_routing_service, None)

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["total_actions"] == 1
        assert len(body["matching_rules"]) == 1
        assert body["matching_rules"][0]["rule_name"] == "Matched Rule"

    @pytest.mark.asyncio
    async def test_reviewer_cannot_run_dry_run(self, reviewer_client: AsyncClient) -> None:
        """Reviewer cannot access the dry-run test endpoint."""
        payload = {
            "email_id": str(uuid.uuid4()),
            "action_slug": "respond",
            "type_slug": "inquiry",
            "confidence": "high",
            "sender_email": "user@example.com",
            "sender_domain": "example.com",
            "subject": "Test",
            "snippet": "Snippet",
        }
        response = await reviewer_client.post("/api/v1/routing-rules/test", json=payload)
        assert response.status_code == 403
