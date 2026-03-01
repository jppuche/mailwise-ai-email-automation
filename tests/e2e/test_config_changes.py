"""E2E tests: configuration changes (categories, routing rules) affect pipeline runs.

Architecture:
  - Tests are SYNC functions (not async def) — Celery tasks use asyncio.run()
    internally; nesting async would cause RuntimeError.
  - Each task is called via task.run() to bypass Celery dispatch and control
    the test boundary precisely.
  - The NEXT task's .delay() is patched to prevent chaining into a nested
    asyncio.run() call (which would also conflict with Celery eager mode).
  - LiteLLMAdapter and SlackAdapter are patched at the module-import level
    (inside the task's deferred import scope) to inject mock adapters.
  - classify_task requires a SANITIZED email; route_task requires CLASSIFIED.

Patch targets:
  - src.adapters.llm.litellm_adapter.LiteLLMAdapter   (classify_task)
  - src.adapters.channel.slack.SlackAdapter             (route_task)
  - src.tasks.pipeline.route_task                       (chain prevention in classify)
  - src.tasks.pipeline.pipeline_crm_sync_task           (chain prevention in route)
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult
from src.models.email import EmailState
from tests.e2e.conftest import (
    MockChannelAdapter,
    MockLLMAdapter,
    _make_session_factory,
    cleanup_email,
    get_classification,
    get_email_state,
    get_routing_actions,
    insert_categories,
    insert_email,
    insert_routing_rule,
)
from tests.factories import (
    ClassificationResultFactory,
    RoutingRuleFactory,
)

# ---------------------------------------------------------------------------
# Async helpers for config-change-specific DB operations
# ---------------------------------------------------------------------------


async def insert_category_pair(
    session_factory: async_sessionmaker[AsyncSession],
    action_slug: str,
    type_slug: str,
) -> tuple[ActionCategory, TypeCategory]:
    """Insert a new action+type category pair, idempotent by slug."""
    return await insert_categories(session_factory, action_slug=action_slug, type_slug=type_slug)


async def insert_classification_result(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
    action_category_id: uuid.UUID,
    type_category_id: uuid.UUID,
) -> ClassificationResult:
    """Insert a pre-existing ClassificationResult for the given email."""
    clf = ClassificationResultFactory(
        email_id=email_id,
        action_category_id=action_category_id,
        type_category_id=type_category_id,
    )
    async with session_factory() as session:
        session.add(clf)
        await session.commit()
        await session.refresh(clf)
    return clf


async def cleanup_routing_rule(
    session_factory: async_sessionmaker[AsyncSession],
    rule_id: uuid.UUID,
) -> None:
    """Delete a test routing rule by ID."""
    from src.models.routing import RoutingRule

    async with session_factory() as session:
        result = await session.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule is not None:
            await session.delete(rule)
            await session.commit()


async def cleanup_category_if_inserted(
    session_factory: async_sessionmaker[AsyncSession],
    action_slug: str,
    type_slug: str,
) -> None:
    """Remove newly-inserted test categories (leaves seed data alone).

    Only deletes if the slug was NOT a standard seed category — we rely
    on unique slugs per test to avoid interfering with existing DB state.
    """
    async with session_factory() as session:
        action_result = await session.execute(
            select(ActionCategory).where(ActionCategory.slug == action_slug)
        )
        action_cat = action_result.scalar_one_or_none()
        if action_cat is not None:
            await session.delete(action_cat)

        type_result = await session.execute(
            select(TypeCategory).where(TypeCategory.slug == type_slug)
        )
        type_cat = type_result.scalar_one_or_none()
        if type_cat is not None:
            await session.delete(type_cat)

        await session.commit()


# ---------------------------------------------------------------------------
# Test 1: new category is available for classification
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_new_category_available_for_classification(migrated_db: None) -> None:
    """Inserting new categories allows the classifier to produce results referencing them.

    Flow:
      1. Insert a new ActionCategory + TypeCategory with unique test slugs.
      2. Insert an email in SANITIZED state.
      3. Patch LiteLLMAdapter so classify() returns the new category slugs.
      4. Patch route_task.delay to prevent chaining.
      5. Run classify_task.run() directly.
      6. Assert: ClassificationResult in DB references the new category IDs.
      7. Assert: email.state == CLASSIFIED.

    Alignment: Lawful Good — verifies DB FK integrity for dynamic categories.
    """
    session_factory = _make_session_factory()

    # Unique slugs to avoid collision with seed data
    action_slug = f"e2e_new_action_{uuid.uuid4().hex[:8]}"
    type_slug = f"e2e_new_type_{uuid.uuid4().hex[:8]}"

    action_cat, type_cat = asyncio.run(
        insert_category_pair(session_factory, action_slug, type_slug)
    )
    email = asyncio.run(insert_email(session_factory, state=EmailState.SANITIZED))

    from src.tasks.pipeline import classify_task

    try:
        # Pre-condition: categories exist, email is SANITIZED
        assert action_cat.slug == action_slug, (
            f"Pre-condition: action category slug mismatch: {action_cat.slug}"
        )
        assert type_cat.slug == type_slug, (
            f"Pre-condition: type category slug mismatch: {type_cat.slug}"
        )

        # Configure mock LLM to return the new category slugs
        mock_llm = MockLLMAdapter()
        mock_llm._action_slug = action_slug
        mock_llm._type_slug = type_slug
        mock_llm.classify = AsyncMock(wraps=mock_llm.classify)  # type: ignore[method-assign]

        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm,
            ),
            patch("src.tasks.pipeline.route_task") as mock_route_delay,
        ):
            mock_route_delay.delay = MagicMock()

            # Act: run classify_task directly (bypasses Celery dispatch)
            classify_task.run(str(email.id))

        # Assert: email transitioned to CLASSIFIED
        email_state = asyncio.run(get_email_state(session_factory, email.id))
        assert email_state == EmailState.CLASSIFIED, (
            f"Expected email.state=CLASSIFIED after classify_task, got {email_state}"
        )

        # Assert: ClassificationResult references the new category IDs
        clf = asyncio.run(get_classification(session_factory, email.id))
        assert clf is not None, "ClassificationResult not found after classify_task"
        assert clf.action_category_id == action_cat.id, (
            f"Expected action_category_id={action_cat.id}, got {clf.action_category_id}. "
            f"New category must be resolved by slug lookup in ClassificationService."
        )
        assert clf.type_category_id == type_cat.id, (
            f"Expected type_category_id={type_cat.id}, got {clf.type_category_id}"
        )

    finally:
        asyncio.run(cleanup_email(session_factory, email.id))
        asyncio.run(cleanup_category_if_inserted(session_factory, action_slug, type_slug))


# ---------------------------------------------------------------------------
# Test 2: new routing rule activates for the next routing run
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_new_routing_rule_activates_for_next_routing(migrated_db: None) -> None:
    """A newly inserted active routing rule is matched on the next route_task run.

    Flow:
      1. Insert standard categories (support/question) + email in CLASSIFIED state.
      2. Insert a ClassificationResult pointing to those categories.
      3. Insert a NEW routing rule matching action_category=support (active).
      4. Patch SlackAdapter + pipeline_crm_sync_task.delay.
      5. Run route_task.run() directly.
      6. Assert: RoutingAction created with new rule's destination.
      7. Assert: email.state == ROUTED.

    Alignment: Lawful Good — verifies that rules added between pipeline runs
    take effect immediately on the next run (no caching).
    """
    session_factory = _make_session_factory()

    # Use standard seed slugs (guaranteed to exist after migration)
    action_cat, type_cat = asyncio.run(
        insert_categories(session_factory, action_slug="support", type_slug="question")
    )
    email = asyncio.run(insert_email(session_factory, state=EmailState.CLASSIFIED))
    asyncio.run(insert_classification_result(session_factory, email.id, action_cat.id, type_cat.id))

    # Insert a new routing rule — unique destination to identify it after routing
    new_destination = f"C_E2E_TEST_{uuid.uuid4().hex[:8]}"
    rule = asyncio.run(
        insert_routing_rule(
            session_factory,
            action_slug="support",
            channel="slack",
            destination=new_destination,
        )
    )

    from src.tasks.pipeline import route_task

    try:
        mock_channel = MockChannelAdapter()
        mock_channel.send_notification = AsyncMock(  # type: ignore[method-assign]
            wraps=mock_channel.send_notification
        )

        with (
            patch(
                "src.adapters.channel.slack.SlackAdapter",
                return_value=mock_channel,
            ),
            patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_delay,
        ):
            mock_crm_delay.delay = MagicMock()

            # Act: run route_task directly
            route_task.run(str(email.id))

        # Assert: email transitioned to ROUTED
        email_state = asyncio.run(get_email_state(session_factory, email.id))
        assert email_state == EmailState.ROUTED, (
            f"Expected email.state=ROUTED after route_task, got {email_state}"
        )

        # Assert: at least one RoutingAction references the new rule
        routing_actions = asyncio.run(get_routing_actions(session_factory, email.id))
        assert len(routing_actions) > 0, (
            "Expected at least one RoutingAction after route_task, found none"
        )

        destinations = [ra.destination for ra in routing_actions]
        assert new_destination in destinations, (
            f"Expected RoutingAction with destination={new_destination!r} "
            f"(new rule), found: {destinations}"
        )

        rule_ids = [str(ra.rule_id) for ra in routing_actions if ra.rule_id is not None]
        assert str(rule.id) in rule_ids, (
            f"Expected RoutingAction.rule_id={rule.id} for the new rule, found rule_ids: {rule_ids}"
        )

    finally:
        asyncio.run(cleanup_email(session_factory, email.id))
        asyncio.run(cleanup_routing_rule(session_factory, rule.id))


# ---------------------------------------------------------------------------
# Test 3: disabled routing rule is skipped
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_disabled_routing_rule_skipped(migrated_db: None) -> None:
    """An inactive routing rule (is_active=False) is not matched during routing.

    Flow:
      1. Insert standard categories + email in CLASSIFIED state.
      2. Insert a ClassificationResult pointing to those categories.
      3. Insert a routing rule with is_active=False matching action_category=support.
      4. Ensure no OTHER active rules match (unique destination used to isolate).
      5. Patch SlackAdapter + pipeline_crm_sync_task.delay.
      6. Run route_task.run() directly.
      7. Assert: No RoutingAction with the disabled rule's destination exists.
      8. Assert: email.state == ROUTED (routing still completes, just 0 actions dispatched
         for this rule — the task transitions state regardless of match count).

    Alignment: Lawful Good — verifies pre-mortem Cat 10 (version-coupled behavior):
    is_active flag is respected at runtime, not just at rule-creation time.
    """
    session_factory = _make_session_factory()

    action_cat, type_cat = asyncio.run(
        insert_categories(session_factory, action_slug="support", type_slug="question")
    )
    email = asyncio.run(insert_email(session_factory, state=EmailState.CLASSIFIED))
    asyncio.run(insert_classification_result(session_factory, email.id, action_cat.id, type_cat.id))

    # Insert a DISABLED routing rule — unique destination to confirm it is NOT matched
    disabled_destination = f"C_E2E_DISABLED_{uuid.uuid4().hex[:8]}"
    disabled_rule = RoutingRuleFactory(
        is_active=False,
        conditions=[{"field": "action_category", "operator": "eq", "value": "support"}],
        actions=[
            {
                "channel": "slack",
                "destination": disabled_destination,
                "template_id": None,
            }
        ],
    )

    async def _insert_disabled_rule() -> None:
        async with session_factory() as session:
            session.add(disabled_rule)
            await session.commit()

    asyncio.run(_insert_disabled_rule())

    from src.tasks.pipeline import route_task

    try:
        mock_channel = MockChannelAdapter()
        mock_channel.send_notification = AsyncMock(  # type: ignore[method-assign]
            wraps=mock_channel.send_notification
        )

        with (
            patch(
                "src.adapters.channel.slack.SlackAdapter",
                return_value=mock_channel,
            ),
            patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_delay,
        ):
            mock_crm_delay.delay = MagicMock()

            # Act: run route_task directly
            route_task.run(str(email.id))

        # Assert: email transitioned to ROUTED (routing task always transitions)
        email_state = asyncio.run(get_email_state(session_factory, email.id))
        assert email_state == EmailState.ROUTED, (
            f"Expected email.state=ROUTED after route_task, got {email_state}"
        )

        # Assert: the DISABLED rule's destination is NOT in any RoutingAction
        routing_actions = asyncio.run(get_routing_actions(session_factory, email.id))
        destinations = [ra.destination for ra in routing_actions]
        assert disabled_destination not in destinations, (
            f"Disabled rule destination {disabled_destination!r} MUST NOT appear "
            f"in RoutingActions, but found: {destinations}"
        )

        # Assert: the disabled rule_id is NOT referenced in any RoutingAction
        rule_ids = [str(ra.rule_id) for ra in routing_actions if ra.rule_id is not None]
        assert str(disabled_rule.id) not in rule_ids, (
            f"Disabled rule {disabled_rule.id} MUST NOT be referenced in RoutingActions, "
            f"but found rule_ids: {rule_ids}"
        )

    finally:
        asyncio.run(cleanup_email(session_factory, email.id))
        asyncio.run(cleanup_routing_rule(session_factory, disabled_rule.id))
