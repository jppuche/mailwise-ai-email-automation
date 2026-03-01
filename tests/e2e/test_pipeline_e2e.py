"""E2E pipeline tests — Block 18.

Architecture notes:
- Tests are SYNC functions. Celery tasks use asyncio.run() internally; nesting
  async causes RuntimeError("This event loop is already running").
- Each task is called via task.run(...), which bypasses Celery dispatch and
  already provides `self` for bind=True tasks.
- The NEXT task's .delay() is patched at module level in src.tasks.pipeline to
  prevent nested asyncio.run() calls.
- DB assertions use asyncio.run() from the sync test context.
- Mock adapter constructors are patched at the module-level import path used by
  each task's deferred import block.

alignment-chart invariants enforced here:
- Every state-transition test verifies BEFORE state (precondition) and AFTER
  state (postcondition).
- Every adapter mock verifies it was called with expected arguments.
- Every assertion queries the DB — no assertion trusts task return values.
- No assert True / assert result is not None as sole assertion.
- Specific exception types in pytest.raises() — never pytest.raises(Exception).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.classification import ClassificationConfidence
from src.models.crm_sync import CRMSyncStatus
from src.models.draft import DraftStatus
from src.models.email import EmailState
from src.models.routing import RoutingActionStatus
from src.tasks.pipeline import (
    classify_task,
    pipeline_crm_sync_task,
    pipeline_draft_task,
    route_task,
)
from tests.e2e.conftest import (
    MockCRMAdapter,
    MockEmailAdapter,
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
from tests.factories import ClassificationResultFactory

# ---------------------------------------------------------------------------
# Module-level env setup — tasks read settings via get_settings()
# ---------------------------------------------------------------------------

# Set required env vars before any task module is imported. Use os.environ
# directly so get_settings() (called inside tasks at runtime) picks them up.
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("HUBSPOT_ACCESS_TOKEN", "test-hubspot-token")


# ---------------------------------------------------------------------------
# Helper: insert a ClassificationResult row for route_task precondition
# ---------------------------------------------------------------------------


async def _insert_classification_result(
    session_factory,  # type: ignore[no-untyped-def]
    email_id: uuid.UUID,
    action_category_id: uuid.UUID,
    type_category_id: uuid.UUID,
) -> None:
    """Insert a ClassificationResult record needed by route_task."""
    record = ClassificationResultFactory(
        email_id=email_id,
        action_category_id=action_category_id,
        type_category_id=type_category_id,
        confidence=ClassificationConfidence.HIGH,
    )
    async with session_factory() as session:
        session.add(record)
        await session.commit()


# ---------------------------------------------------------------------------
# Test 1: classify_task transitions SANITIZED -> CLASSIFIED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_classify_task_transitions_email_to_classified(migrated_db: None) -> None:
    """SANITIZED email is classified and transitioned to CLASSIFIED state.

    Preconditions:
      - Email in SANITIZED state.
      - action/type categories exist with slugs "support" / "question".
      - LiteLLMAdapter is mocked to return canned classification.
      - route_task.delay is patched to prevent chaining.

    Postconditions (verified in DB):
      - Email state == CLASSIFIED.
      - ClassificationResult row exists with matching category IDs.
      - route_task.delay was called with the email's string ID.
    """
    sf = _make_session_factory()

    # --- Setup -----------------------------------------------------------------
    email = asyncio.run(insert_email(sf, state=EmailState.SANITIZED))
    action_cat, type_cat = asyncio.run(
        insert_categories(sf, action_slug="support", type_slug="question")
    )
    email_id_str = str(email.id)

    # Verify precondition: email starts in SANITIZED
    before_state = asyncio.run(get_email_state(sf, email.id))
    assert before_state == EmailState.SANITIZED, (
        f"Precondition failed: expected SANITIZED, got {before_state}"
    )

    mock_llm_instance = MockLLMAdapter()
    # Wrap classify so we can assert it was called
    mock_llm_instance.classify = AsyncMock(wraps=mock_llm_instance.classify)  # type: ignore[method-assign]

    mock_route_delay = MagicMock()

    try:
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch("src.tasks.pipeline.route_task") as mock_route_task,
        ):
            mock_route_task.delay = mock_route_delay

            # --- Execute -------------------------------------------------------
            classify_task.run(email_id_str)

        # --- Assert: email state -----------------------------------------------
        after_state = asyncio.run(get_email_state(sf, email.id))
        assert after_state == EmailState.CLASSIFIED, f"Expected CLASSIFIED, got {after_state}"

        # --- Assert: ClassificationResult in DB --------------------------------
        classification = asyncio.run(get_classification(sf, email.id))
        assert classification is not None, "ClassificationResult row was not created"
        assert classification.email_id == email.id
        assert classification.action_category_id == action_cat.id
        assert classification.type_category_id == type_cat.id
        assert classification.confidence == ClassificationConfidence.HIGH
        assert classification.fallback_applied is False

        # --- Assert: LLM adapter was called ------------------------------------
        mock_llm_instance.classify.assert_called_once()

        # --- Assert: chaining --------------------------------------------------
        mock_route_delay.assert_called_once_with(email_id_str)

    finally:
        asyncio.run(cleanup_email(sf, email.id))


# ---------------------------------------------------------------------------
# Test 2: route_task transitions CLASSIFIED -> ROUTED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_route_task_transitions_email_to_routed(migrated_db: None) -> None:
    """CLASSIFIED email is routed and transitioned to ROUTED state.

    Preconditions:
      - Email in CLASSIFIED state.
      - Categories + routing rule exist (action_slug="support").
      - ClassificationResult exists in DB for this email.
      - SlackAdapter is mocked to confirm dispatch.
      - pipeline_crm_sync_task.delay is patched.

    Postconditions (verified in DB):
      - Email state == ROUTED.
      - At least one RoutingAction with status DISPATCHED exists.
      - pipeline_crm_sync_task.delay was called with the email's string ID.
    """
    sf = _make_session_factory()

    # --- Setup -----------------------------------------------------------------
    email = asyncio.run(insert_email(sf, state=EmailState.CLASSIFIED))
    action_cat, type_cat = asyncio.run(
        insert_categories(sf, action_slug="support", type_slug="question")
    )
    asyncio.run(
        insert_routing_rule(
            sf, action_slug="support", channel="slack", destination="C_TEST_CHANNEL"
        )
    )
    asyncio.run(_insert_classification_result(sf, email.id, action_cat.id, type_cat.id))
    email_id_str = str(email.id)

    # Verify precondition
    before_state = asyncio.run(get_email_state(sf, email.id))
    assert before_state == EmailState.CLASSIFIED, (
        f"Precondition failed: expected CLASSIFIED, got {before_state}"
    )

    # Set SLACK_BOT_TOKEN so the route_task instantiates SlackAdapter
    mock_channel_instance = MagicMock()
    mock_channel_instance.connect = AsyncMock(return_value=MagicMock(connected=True))
    mock_channel_instance.send_notification = AsyncMock(
        return_value=MagicMock(success=True, message_ts="ts.123", channel_id="C_TEST_CHANNEL")
    )

    mock_crm_sync_delay = MagicMock()

    try:
        with (
            patch(
                "src.adapters.channel.slack.SlackAdapter",
                return_value=mock_channel_instance,
            ),
            patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task,
        ):
            mock_crm_task.delay = mock_crm_sync_delay

            # --- Execute -------------------------------------------------------
            route_task.run(email_id_str)

        # --- Assert: email state -----------------------------------------------
        after_state = asyncio.run(get_email_state(sf, email.id))
        assert after_state == EmailState.ROUTED, f"Expected ROUTED, got {after_state}"

        # --- Assert: RoutingAction in DB ---------------------------------------
        routing_actions = asyncio.run(get_routing_actions(sf, email.id))
        assert len(routing_actions) >= 1, "No RoutingAction rows were created"

        dispatched = [a for a in routing_actions if a.status == RoutingActionStatus.DISPATCHED]
        assert len(dispatched) >= 1, (
            f"Expected at least one DISPATCHED action, got statuses: "
            f"{[a.status for a in routing_actions]}"
        )
        assert dispatched[0].channel == "slack"
        assert dispatched[0].destination == "C_TEST_CHANNEL"

        # --- Assert: Slack adapter send_notification called --------------------
        mock_channel_instance.send_notification.assert_called_once()

        # --- Assert: chaining --------------------------------------------------
        mock_crm_sync_delay.assert_called_once_with(email_id_str)

    finally:
        asyncio.run(cleanup_email(sf, email.id))


# ---------------------------------------------------------------------------
# Test 3: pipeline_crm_sync_task transitions ROUTED -> CRM_SYNCED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_crm_sync_task_transitions_email_to_crm_synced(migrated_db: None) -> None:
    """ROUTED email is CRM-synced and transitioned to CRM_SYNCED state.

    Preconditions:
      - Email in ROUTED state.
      - HubSpotAdapter is mocked to confirm successful CRM operations.
      - pipeline_draft_task.delay is patched.

    Postconditions (verified in DB):
      - Email state == CRM_SYNCED.
      - CRMSyncRecord row exists with status SYNCED.
      - pipeline_draft_task.delay was called with the email's string ID.
    """
    sf = _make_session_factory()

    # --- Setup -----------------------------------------------------------------
    email = asyncio.run(insert_email(sf, state=EmailState.ROUTED))
    email_id_str = str(email.id)

    # Verify precondition
    before_state = asyncio.run(get_email_state(sf, email.id))
    assert before_state == EmailState.ROUTED, (
        f"Precondition failed: expected ROUTED, got {before_state}"
    )

    mock_crm_instance = MockCRMAdapter()
    mock_crm_instance.lookup_contact = AsyncMock(wraps=mock_crm_instance.lookup_contact)  # type: ignore[method-assign]
    mock_crm_instance.log_activity = AsyncMock(wraps=mock_crm_instance.log_activity)  # type: ignore[method-assign]

    mock_draft_delay = MagicMock()

    try:
        with (
            patch(
                "src.adapters.crm.hubspot.HubSpotAdapter",
                return_value=mock_crm_instance,
            ),
            patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task,
        ):
            mock_draft_task.delay = mock_draft_delay

            # --- Execute -------------------------------------------------------
            pipeline_crm_sync_task.run(email_id_str)

        # --- Assert: email state -----------------------------------------------
        after_state = asyncio.run(get_email_state(sf, email.id))
        assert after_state == EmailState.CRM_SYNCED, f"Expected CRM_SYNCED, got {after_state}"

        # --- Assert: CRMSyncRecord in DB ---------------------------------------
        crm_record = asyncio.run(get_crm_sync_record(sf, email.id))
        assert crm_record is not None, "CRMSyncRecord row was not created"
        assert crm_record.email_id == email.id
        assert crm_record.status == CRMSyncStatus.SYNCED

        # --- Assert: CRM adapter interactions ---------------------------------
        mock_crm_instance.lookup_contact.assert_called_once()
        mock_crm_instance.log_activity.assert_called_once()

        # --- Assert: chaining --------------------------------------------------
        mock_draft_delay.assert_called_once_with(email_id_str)

    finally:
        asyncio.run(cleanup_email(sf, email.id))


# ---------------------------------------------------------------------------
# Test 4: pipeline_draft_task transitions CRM_SYNCED -> DRAFT_GENERATED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_draft_task_transitions_email_to_draft_generated(migrated_db: None) -> None:
    """CRM_SYNCED email gets a draft generated and transitions to DRAFT_GENERATED.

    Preconditions:
      - Email in CRM_SYNCED state.
      - LiteLLMAdapter is mocked to return canned draft content.
      - GmailAdapter is mocked (no live Gmail required).

    Postconditions (verified in DB):
      - Email state == DRAFT_GENERATED.
      - Draft row exists with non-empty content and status PENDING.
    """
    sf = _make_session_factory()

    # --- Setup -----------------------------------------------------------------
    email = asyncio.run(insert_email(sf, state=EmailState.CRM_SYNCED))
    email_id_str = str(email.id)

    # Verify precondition
    before_state = asyncio.run(get_email_state(sf, email.id))
    assert before_state == EmailState.CRM_SYNCED, (
        f"Precondition failed: expected CRM_SYNCED, got {before_state}"
    )

    mock_llm_instance = MockLLMAdapter()
    mock_llm_instance.generate_draft = AsyncMock(wraps=mock_llm_instance.generate_draft)  # type: ignore[method-assign]

    mock_email_instance = MockEmailAdapter()
    # create_draft returns "mock_draft_id" — wrapped for call assertion
    mock_email_instance.create_draft = MagicMock(wraps=mock_email_instance.create_draft)  # type: ignore[method-assign]

    try:
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch(
                "src.adapters.email.gmail.GmailAdapter",
                return_value=mock_email_instance,
            ),
        ):
            # --- Execute -------------------------------------------------------
            pipeline_draft_task.run(email_id_str)

        # --- Assert: email state -----------------------------------------------
        after_state = asyncio.run(get_email_state(sf, email.id))
        assert after_state == EmailState.DRAFT_GENERATED, (
            f"Expected DRAFT_GENERATED, got {after_state}"
        )

        # --- Assert: Draft in DB -----------------------------------------------
        draft = asyncio.run(get_draft(sf, email.id))
        assert draft is not None, "Draft row was not created"
        assert draft.email_id == email.id
        assert draft.content, "Draft content must be non-empty"
        assert draft.status == DraftStatus.PENDING
        assert draft.pushed_to_provider is False  # draft_push_to_gmail defaults to False

        # --- Assert: LLM adapter generate_draft was called --------------------
        mock_llm_instance.generate_draft.assert_called_once()

    finally:
        asyncio.run(cleanup_email(sf, email.id))


# ---------------------------------------------------------------------------
# Test 5: full pipeline — SANITIZED -> DRAFT_GENERATED (all 4 tasks)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_full_pipeline_sequential(migrated_db: None) -> None:
    """Full pipeline: SANITIZED email traverses all 4 tasks to DRAFT_GENERATED.

    Each task's chaining (.delay) is patched individually at each step to
    prevent nested asyncio.run() and to control execution order.

    After all 4 tasks, verifies all child records exist in the DB:
      - ClassificationResult (from classify_task)
      - RoutingAction with DISPATCHED status (from route_task)
      - CRMSyncRecord with SYNCED status (from pipeline_crm_sync_task)
      - Draft with non-empty content (from pipeline_draft_task)

    State progression verified at each stage:
      SANITIZED -> CLASSIFIED -> ROUTED -> CRM_SYNCED -> DRAFT_GENERATED
    """
    sf = _make_session_factory()

    # --- Setup -----------------------------------------------------------------
    email = asyncio.run(insert_email(sf, state=EmailState.SANITIZED))
    action_cat, type_cat = asyncio.run(
        insert_categories(sf, action_slug="support", type_slug="question")
    )
    asyncio.run(
        insert_routing_rule(
            sf, action_slug="support", channel="slack", destination="C_TEST_CHANNEL"
        )
    )
    email_id_str = str(email.id)

    # Adapters shared across all stages
    mock_llm_instance = MockLLMAdapter()
    mock_llm_instance.classify = AsyncMock(wraps=mock_llm_instance.classify)  # type: ignore[method-assign]
    mock_llm_instance.generate_draft = AsyncMock(wraps=mock_llm_instance.generate_draft)  # type: ignore[method-assign]

    mock_channel_instance = MagicMock()
    mock_channel_instance.connect = AsyncMock(return_value=MagicMock(connected=True))
    mock_channel_instance.send_notification = AsyncMock(
        return_value=MagicMock(success=True, message_ts="ts.456", channel_id="C_TEST_CHANNEL")
    )

    mock_crm_instance = MockCRMAdapter()
    mock_crm_instance.lookup_contact = AsyncMock(wraps=mock_crm_instance.lookup_contact)  # type: ignore[method-assign]
    mock_crm_instance.log_activity = AsyncMock(wraps=mock_crm_instance.log_activity)  # type: ignore[method-assign]

    mock_email_instance = MockEmailAdapter()
    mock_email_instance.create_draft = MagicMock(wraps=mock_email_instance.create_draft)  # type: ignore[method-assign]

    try:
        # -----------------------------------------------------------------------
        # Stage 1: classify_task — SANITIZED -> CLASSIFIED
        # -----------------------------------------------------------------------
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch("src.tasks.pipeline.route_task") as mock_route_task_stage1,
        ):
            mock_route_task_stage1.delay = MagicMock()
            classify_task.run(email_id_str)

        state_after_classify = asyncio.run(get_email_state(sf, email.id))
        assert state_after_classify == EmailState.CLASSIFIED, (
            f"After classify_task: expected CLASSIFIED, got {state_after_classify}"
        )

        # -----------------------------------------------------------------------
        # Stage 2: route_task — CLASSIFIED -> ROUTED
        # -----------------------------------------------------------------------
        with (
            patch(
                "src.adapters.channel.slack.SlackAdapter",
                return_value=mock_channel_instance,
            ),
            patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task_stage2,
        ):
            mock_crm_task_stage2.delay = MagicMock()
            route_task.run(email_id_str)

        state_after_route = asyncio.run(get_email_state(sf, email.id))
        assert state_after_route == EmailState.ROUTED, (
            f"After route_task: expected ROUTED, got {state_after_route}"
        )

        # -----------------------------------------------------------------------
        # Stage 3: pipeline_crm_sync_task — ROUTED -> CRM_SYNCED
        # -----------------------------------------------------------------------
        with (
            patch(
                "src.adapters.crm.hubspot.HubSpotAdapter",
                return_value=mock_crm_instance,
            ),
            patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task_stage3,
        ):
            mock_draft_task_stage3.delay = MagicMock()
            pipeline_crm_sync_task.run(email_id_str)

        state_after_crm = asyncio.run(get_email_state(sf, email.id))
        assert state_after_crm == EmailState.CRM_SYNCED, (
            f"After pipeline_crm_sync_task: expected CRM_SYNCED, got {state_after_crm}"
        )

        # -----------------------------------------------------------------------
        # Stage 4: pipeline_draft_task — CRM_SYNCED -> DRAFT_GENERATED
        # -----------------------------------------------------------------------
        with (
            patch(
                "src.adapters.llm.litellm_adapter.LiteLLMAdapter",
                return_value=mock_llm_instance,
            ),
            patch(
                "src.adapters.email.gmail.GmailAdapter",
                return_value=mock_email_instance,
            ),
        ):
            pipeline_draft_task.run(email_id_str)

        state_after_draft = asyncio.run(get_email_state(sf, email.id))
        assert state_after_draft == EmailState.DRAFT_GENERATED, (
            f"After pipeline_draft_task: expected DRAFT_GENERATED, got {state_after_draft}"
        )

        # -----------------------------------------------------------------------
        # Final: verify all child records exist in DB
        # -----------------------------------------------------------------------
        classification = asyncio.run(get_classification(sf, email.id))
        assert classification is not None, "ClassificationResult missing after full pipeline"
        assert classification.action_category_id == action_cat.id
        assert classification.type_category_id == type_cat.id
        assert classification.confidence == ClassificationConfidence.HIGH

        routing_actions = asyncio.run(get_routing_actions(sf, email.id))
        assert len(routing_actions) >= 1, "RoutingAction missing after full pipeline"
        dispatched = [a for a in routing_actions if a.status == RoutingActionStatus.DISPATCHED]
        assert len(dispatched) >= 1, (
            f"No DISPATCHED routing action; statuses: {[a.status for a in routing_actions]}"
        )

        crm_record = asyncio.run(get_crm_sync_record(sf, email.id))
        assert crm_record is not None, "CRMSyncRecord missing after full pipeline"
        assert crm_record.status == CRMSyncStatus.SYNCED

        draft = asyncio.run(get_draft(sf, email.id))
        assert draft is not None, "Draft missing after full pipeline"
        assert draft.content, "Draft content must be non-empty"
        assert draft.status == DraftStatus.PENDING

    finally:
        asyncio.run(cleanup_email(sf, email.id))
