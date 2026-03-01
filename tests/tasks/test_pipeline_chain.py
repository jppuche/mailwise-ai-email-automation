"""Tests for the pipeline chain orchestration in src/tasks/pipeline.py.

Focus: task chaining behaviour — each task enqueues the correct downstream
task under the correct conditions. Internal service logic is tested in the
respective service test files.

Strategy:
  - ``run_pipeline`` is a plain function: mock ``classify_task.delay``.
  - For each async ``_run_*`` bridge: patch the upstream async function
    (e.g. ``_run_ingestion``) AND mock ``.delay()`` on downstream tasks
    to verify chaining decisions.
  - ``pipeline_crm_sync_task`` requires an extra DB query to inspect
    email state after CRM sync; that query is patched via sys.modules
    injection of ``AsyncSessionLocal``.
  - All external service calls are mocked — no real DB, broker, or LLM.

Alignment-chart (D8 — local computation = chain decision):
  - Chaining decisions (``if was_routed``, ``if email.state == CRM_SYNCED``)
    are local conditionals, not try/except. These tests verify those paths.

Tests:
  1. run_pipeline_enqueues_classify
  2. ingest_task_enqueues_classify_for_each_ingested_email
  3. ingest_task_skips_classify_when_not_ingested
  4. classify_task_enqueues_route_on_success
  5. route_task_enqueues_crm_sync_when_routed
  6. route_task_no_chain_when_not_routed
  7. crm_sync_chains_to_draft_on_crm_synced
  8. crm_sync_no_chain_when_crm_sync_failed
  9. pipeline_draft_task_delegates_to_run_draft_generation
"""

from __future__ import annotations

import inspect
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.pipeline import (
    _run_classification,
    _run_crm_sync_with_chain,
    _run_ingestion_pipeline,
    _run_routing,
    classify_task,
    ingest_task,
    pipeline_crm_sync_task,
    pipeline_draft_task,
    route_task,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

EMAIL_ID = str(uuid.uuid4())
EMAIL_UUID = uuid.UUID(EMAIL_ID)
ACCOUNT_ID = "test-account-id"
SINCE_ISO = "2026-03-01T00:00:00+00:00"


def _make_mock_task() -> MagicMock:
    """Celery task self mock — ``task.retry`` raises so tests can assert it."""
    task = MagicMock()
    task.retry.side_effect = RuntimeError("task.retry called")
    return task


def _close_coro_and_return(coro: object) -> None:
    """Side-effect for asyncio.run mocks: close the coroutine to suppress ResourceWarning."""
    if inspect.iscoroutine(coro):
        coro.close()


def _build_db_context(email: MagicMock | None) -> AsyncMock:
    """AsyncSessionLocal context manager returning a mock DB session."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = email
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_ingestion_result(email_id: uuid.UUID) -> MagicMock:
    """Single IngestionResult mock with is_ingested=True."""
    result = MagicMock()
    result.is_ingested = True
    result.email_id = email_id
    return result


def _make_ingestion_result_not_ingested() -> MagicMock:
    """Single IngestionResult mock with is_ingested=False (skipped/failed)."""
    result = MagicMock()
    result.is_ingested = False
    result.email_id = None
    return result


def _make_batch_result(individual_results: list[MagicMock]) -> MagicMock:
    """IngestionBatchResult mock wrapping the given individual results."""
    batch = MagicMock()
    batch.lock_acquired = True
    batch.ingested = sum(1 for r in individual_results if r.is_ingested)
    batch.skipped = 0
    batch.failed = 0
    batch.results = individual_results
    return batch


# ---------------------------------------------------------------------------
# Helper: inject sys.modules patches and restore after test
# ---------------------------------------------------------------------------


def _apply_patches(patches: dict[str, MagicMock]) -> dict[str, types.ModuleType | None]:
    """Inject all patches into sys.modules, returning originals for restore."""
    originals: dict[str, types.ModuleType | None] = {}
    for key, val in patches.items():
        originals[key] = sys.modules.get(key)
        sys.modules[key] = val
    return originals


def _restore_patches(originals: dict[str, types.ModuleType | None]) -> None:
    """Restore sys.modules to its state before _apply_patches was called."""
    for key, original in originals.items():
        if original is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = original


# ---------------------------------------------------------------------------
# 1. run_pipeline — enqueues classify_task
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """run_pipeline() enqueues classify_task for the given email_id."""

    @patch("src.tasks.pipeline.classify_task")
    def test_run_pipeline_enqueues_classify(self, mock_classify_task: MagicMock) -> None:
        """run_pipeline(uuid) calls classify_task.delay(str(uuid))."""
        email_id = EMAIL_UUID
        run_pipeline(email_id)

        mock_classify_task.delay.assert_called_once_with(str(email_id))

    @patch("src.tasks.pipeline.classify_task")
    def test_run_pipeline_passes_string_id(self, mock_classify_task: MagicMock) -> None:
        """classify_task.delay receives a str, not a uuid.UUID instance."""
        email_id = EMAIL_UUID
        run_pipeline(email_id)

        call_arg = mock_classify_task.delay.call_args.args[0]
        assert isinstance(call_arg, str)
        assert call_arg == str(email_id)

    @patch("src.tasks.pipeline.classify_task")
    def test_run_pipeline_returns_none(self, mock_classify_task: MagicMock) -> None:
        """run_pipeline is fire-and-forget — returns None (no exception raised)."""
        # run_pipeline is annotated -> None, so no return value to assert.
        # Verify it completes without raising.
        run_pipeline(EMAIL_UUID)  # must not raise


# ---------------------------------------------------------------------------
# 2. ingest_task — thin sync wrapper
# ---------------------------------------------------------------------------


class TestIngestTaskEntryPoint:
    """ingest_task() delegates to asyncio.run().

    Note: With @celery_app.task(bind=True), ingest_task.run is already bound
    to the Celery task instance. Its signature exposes (account_id, since_iso)
    directly. We do NOT pass a mock_task — the Celery task self is the real
    task object. For retry propagation, asyncio.run side_effect triggers
    ingest_task's own task.retry() call which raises MaxRetriesExceededError
    or Ignore — we verify the exception propagates.
    """

    @patch("src.tasks.pipeline.asyncio.run")
    def test_ingest_task_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        ingest_task.run(ACCOUNT_ID, SINCE_ISO)

        mock_run.assert_called_once()

    @patch("src.tasks.pipeline.asyncio.run")
    def test_ingest_task_propagates_exception_from_asyncio_run(self, mock_run: MagicMock) -> None:
        """If asyncio.run raises, ingest_task calls self.retry which re-raises.

        Celery propagates the original exception via ``raise self.retry(exc=exc) from exc``.
        The original RuntimeError surfaces as the raised exception in tests.
        """
        mock_run.side_effect = RuntimeError("upstream failure")

        with pytest.raises(RuntimeError, match="upstream failure"):
            ingest_task.run(ACCOUNT_ID, SINCE_ISO)


# ---------------------------------------------------------------------------
# 3. _run_ingestion_pipeline — classify chaining per ingested email
# ---------------------------------------------------------------------------


class TestRunIngestionPipeline:
    """_run_ingestion_pipeline enqueues classify_task.delay for each ingested email."""

    @pytest.mark.asyncio
    async def test_enqueues_classify_for_each_ingested_email(self) -> None:
        """Two ingested emails -> classify_task.delay called twice."""
        email_id_1 = uuid.uuid4()
        email_id_2 = uuid.uuid4()

        result_1 = _make_ingestion_result(email_id_1)
        result_2 = _make_ingestion_result(email_id_2)
        batch_result = _make_batch_result([result_1, result_2])

        mock_run_ingestion = AsyncMock(return_value=batch_result)
        mock_classify_delay = MagicMock()

        # Patch _run_ingestion at the module level it's imported from inside the pipeline
        ingestion_mod = MagicMock()
        ingestion_mod._run_ingestion = mock_run_ingestion

        originals = _apply_patches({"src.tasks.ingestion_task": ingestion_mod})
        try:
            with patch("src.tasks.pipeline.classify_task") as mock_classify_task:
                mock_classify_task.delay = mock_classify_delay
                await _run_ingestion_pipeline(ACCOUNT_ID, SINCE_ISO)
        finally:
            _restore_patches(originals)

        assert mock_classify_delay.call_count == 2
        called_ids = {call.args[0] for call in mock_classify_delay.call_args_list}
        assert str(email_id_1) in called_ids
        assert str(email_id_2) in called_ids

    @pytest.mark.asyncio
    async def test_skips_classify_for_non_ingested_emails(self) -> None:
        """Skipped / failed emails with is_ingested=False are not enqueued."""
        skipped = _make_ingestion_result_not_ingested()
        batch_result = _make_batch_result([skipped])

        mock_run_ingestion = AsyncMock(return_value=batch_result)

        ingestion_mod = MagicMock()
        ingestion_mod._run_ingestion = mock_run_ingestion

        originals = _apply_patches({"src.tasks.ingestion_task": ingestion_mod})
        try:
            with patch("src.tasks.pipeline.classify_task") as mock_classify_task:
                await _run_ingestion_pipeline(ACCOUNT_ID, SINCE_ISO)
        finally:
            _restore_patches(originals)

        mock_classify_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueues_classify_with_str_email_id(self) -> None:
        """classify_task.delay receives str, not uuid.UUID."""
        email_id = uuid.uuid4()
        result = _make_ingestion_result(email_id)
        batch_result = _make_batch_result([result])

        mock_run_ingestion = AsyncMock(return_value=batch_result)

        ingestion_mod = MagicMock()
        ingestion_mod._run_ingestion = mock_run_ingestion

        originals = _apply_patches({"src.tasks.ingestion_task": ingestion_mod})
        try:
            with patch("src.tasks.pipeline.classify_task") as mock_classify_task:
                await _run_ingestion_pipeline(ACCOUNT_ID, SINCE_ISO)
        finally:
            _restore_patches(originals)

        call_arg = mock_classify_task.delay.call_args.args[0]
        assert isinstance(call_arg, str)
        assert call_arg == str(email_id)

    @pytest.mark.asyncio
    async def test_empty_batch_no_classify_enqueued(self) -> None:
        """Empty results list -> no classify_task.delay calls."""
        batch_result = _make_batch_result([])

        mock_run_ingestion = AsyncMock(return_value=batch_result)

        ingestion_mod = MagicMock()
        ingestion_mod._run_ingestion = mock_run_ingestion

        originals = _apply_patches({"src.tasks.ingestion_task": ingestion_mod})
        try:
            with patch("src.tasks.pipeline.classify_task") as mock_classify_task:
                await _run_ingestion_pipeline(ACCOUNT_ID, SINCE_ISO)
        finally:
            _restore_patches(originals)

        mock_classify_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# 4. classify_task — thin sync wrapper
# ---------------------------------------------------------------------------


class TestClassifyTaskEntryPoint:
    """classify_task() delegates to asyncio.run().

    classify_task.run is bound to the Celery task; signature is (email_id,).
    """

    @patch("src.tasks.pipeline.asyncio.run")
    def test_classify_task_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        classify_task.run(EMAIL_ID)

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 5. _run_classification — route chaining on success
# ---------------------------------------------------------------------------


def _make_mock_settings_for_classify() -> MagicMock:
    settings = MagicMock()
    settings.llm_model_classify = "gpt-4o-mini"
    settings.llm_model_draft = "gpt-4o"
    settings.llm_fallback_model = "gpt-3.5-turbo"
    settings.openai_api_key = "test-key"
    settings.llm_base_url = ""
    settings.llm_timeout_seconds = 30
    settings.celery_backoff_base = 60
    return settings


def _make_classification_service_result() -> MagicMock:
    """Mock ClassificationServiceResult with required fields for logging."""
    result = MagicMock()
    result.action_slug = "respond"
    result.confidence = "high"
    return result


def _make_classify_sys_patches(
    mock_email: MagicMock | None,
    classify_side_effect: Exception | None = None,
    classify_return: MagicMock | None = None,
) -> tuple[dict[str, MagicMock], MagicMock, MagicMock]:
    """Build sys.modules patches for _run_classification.

    Returns (patches_dict, mock_service, mock_db_ctx).
    """
    from src.adapters.llm.exceptions import LLMRateLimitError
    from src.adapters.llm.schemas import LLMConfig

    mock_settings = _make_mock_settings_for_classify()
    mock_db_ctx = _build_db_context(mock_email)

    mock_service = MagicMock()
    if classify_side_effect is not None:
        mock_service.classify_email = AsyncMock(side_effect=classify_side_effect)
    else:
        ret = (
            classify_return
            if classify_return is not None
            else _make_classification_service_result()
        )
        mock_service.classify_email = AsyncMock(return_value=ret)

    # Module mocks
    mock_config_mod = MagicMock()
    mock_config_mod.get_settings.return_value = mock_settings

    mock_llm_adapter_mod = MagicMock()
    mock_llm_adapter_mod.LiteLLMAdapter.return_value = MagicMock()

    mock_llm_schemas_mod = MagicMock()
    mock_llm_schemas_mod.LLMConfig = LLMConfig

    mock_db_mod = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

    mock_classification_svc_mod = MagicMock()
    mock_classification_svc_mod.ClassificationService.return_value = mock_service

    mock_llm_exc_mod = MagicMock()
    mock_llm_exc_mod.LLMRateLimitError = LLMRateLimitError

    from src.models.email import Email

    mock_email_mod = MagicMock()
    mock_email_mod.Email = Email

    patches = {
        "src.core.config": mock_config_mod,
        "src.adapters.llm.litellm_adapter": mock_llm_adapter_mod,
        "src.adapters.llm.schemas": mock_llm_schemas_mod,
        "src.core.database": mock_db_mod,
        "src.services.classification": mock_classification_svc_mod,
        "src.adapters.llm.exceptions": mock_llm_exc_mod,
        "src.models.email": mock_email_mod,
    }
    return patches, mock_service, mock_db_ctx


class TestRunClassification:
    """_run_classification enqueues route_task on successful classification."""

    @pytest.mark.asyncio
    async def test_enqueues_route_task_on_success(self) -> None:
        """Successful classification -> route_task.delay(email_id_str) called."""
        mock_email = MagicMock()
        mock_email.id = EMAIL_UUID

        patches, mock_service, _ = _make_classify_sys_patches(mock_email)
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.route_task") as mock_route_task:
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_route_task.delay.assert_called_once_with(EMAIL_ID)

    @pytest.mark.asyncio
    async def test_no_route_enqueued_when_email_not_found(self) -> None:
        """Email not found in DB -> early return, no route_task.delay."""
        patches, _, _ = _make_classify_sys_patches(None)
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.route_task") as mock_route_task:
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_route_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_rate_limit_retries_without_chaining(self) -> None:
        """LLMRateLimitError -> task.retry raised, route_task NOT enqueued."""
        from src.adapters.llm.exceptions import LLMRateLimitError

        mock_email = MagicMock()
        mock_email.id = EMAIL_UUID
        exc = LLMRateLimitError("rate limited", retry_after_seconds=30)

        patches, _, _ = _make_classify_sys_patches(mock_email, classify_side_effect=exc)
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry called")

        originals = _apply_patches(patches)
        try:
            with (
                patch("src.tasks.pipeline.route_task") as mock_route_task,
                pytest.raises(RuntimeError, match="task.retry called"),
            ):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_route_task.delay.assert_not_called()
        mock_task.retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception_retries_without_chaining(self) -> None:
        """Unexpected exception -> task.retry raised, route_task NOT enqueued."""
        mock_email = MagicMock()
        mock_email.id = EMAIL_UUID
        exc = ConnectionError("DB gone")

        patches, _, _ = _make_classify_sys_patches(mock_email, classify_side_effect=exc)
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry generic")

        originals = _apply_patches(patches)
        try:
            with (
                patch("src.tasks.pipeline.route_task") as mock_route_task,
                pytest.raises(RuntimeError, match="task.retry generic"),
            ):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_route_task.delay.assert_not_called()
        mock_task.retry.assert_called_once()


# ---------------------------------------------------------------------------
# 6. route_task — thin sync wrapper
# ---------------------------------------------------------------------------


class TestRouteTaskEntryPoint:
    """route_task() delegates to asyncio.run().

    route_task.run is bound to the Celery task; signature is (email_id,).
    """

    @patch("src.tasks.pipeline.asyncio.run")
    def test_route_task_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        route_task.run(EMAIL_ID)

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 7. _run_routing — CRM sync chaining
# ---------------------------------------------------------------------------


def _make_mock_settings_for_routing() -> MagicMock:
    settings = MagicMock()
    settings.slack_bot_token = ""  # empty -> no Slack adapter built
    return settings


def _make_routing_result(was_routed: bool) -> MagicMock:
    result = MagicMock()
    result.was_routed = was_routed
    result.actions_dispatched = 1 if was_routed else 0
    return result


def _make_routing_sys_patches(
    was_routed: bool = True,
    route_side_effect: Exception | None = None,
) -> tuple[dict[str, MagicMock], MagicMock]:
    """Build sys.modules patches for _run_routing.

    Returns (patches_dict, mock_service).
    """
    mock_settings = _make_mock_settings_for_routing()

    mock_service = MagicMock()
    if route_side_effect is not None:
        mock_service.route = AsyncMock(side_effect=route_side_effect)
    else:
        mock_service.route = AsyncMock(return_value=_make_routing_result(was_routed))

    mock_db_ctx = _build_db_context(MagicMock())

    mock_config_mod = MagicMock()
    mock_config_mod.get_settings.return_value = mock_settings

    mock_routing_svc_mod = MagicMock()
    mock_routing_svc_mod.RoutingService.return_value = mock_service

    mock_db_mod = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

    mock_slack_mod = MagicMock()
    mock_slack_mod.SlackAdapter.return_value = AsyncMock()

    mock_channel_schemas_mod = MagicMock()

    patches = {
        "src.core.config": mock_config_mod,
        "src.services.routing": mock_routing_svc_mod,
        "src.core.database": mock_db_mod,
        "src.adapters.channel.slack": mock_slack_mod,
        "src.adapters.channel.schemas": mock_channel_schemas_mod,
    }
    return patches, mock_service


class TestRunRouting:
    """_run_routing enqueues pipeline_crm_sync_task when was_routed=True."""

    @pytest.mark.asyncio
    async def test_enqueues_crm_sync_when_routed(self) -> None:
        """was_routed=True -> pipeline_crm_sync_task.delay(email_id_str) called."""
        patches, _ = _make_routing_sys_patches(was_routed=True)
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task:
                await _run_routing(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_crm_task.delay.assert_called_once_with(EMAIL_ID)

    @pytest.mark.asyncio
    async def test_no_crm_sync_when_not_routed(self) -> None:
        """was_routed=False -> pipeline_crm_sync_task.delay NOT called."""
        patches, _ = _make_routing_sys_patches(was_routed=False)
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task:
                await _run_routing(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_crm_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_retries_without_chaining(self) -> None:
        """Exception in route() -> task.retry raised, no CRM sync enqueued."""
        exc = RuntimeError("routing failure")
        patches, _ = _make_routing_sys_patches(route_side_effect=exc)
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry called")

        originals = _apply_patches(patches)
        try:
            with (
                patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task,
                pytest.raises(RuntimeError, match="task.retry called"),
            ):
                await _run_routing(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_crm_task.delay.assert_not_called()
        mock_task.retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_crm_sync_receives_correct_email_id_str(self) -> None:
        """pipeline_crm_sync_task.delay receives the same email_id_str passed in."""
        patches, _ = _make_routing_sys_patches(was_routed=True)
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_crm_sync_task") as mock_crm_task:
                await _run_routing(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        call_arg = mock_crm_task.delay.call_args.args[0]
        assert call_arg == EMAIL_ID
        assert isinstance(call_arg, str)


# ---------------------------------------------------------------------------
# 8. pipeline_crm_sync_task — thin sync wrapper
# ---------------------------------------------------------------------------


class TestPipelineCrmSyncTaskEntryPoint:
    """pipeline_crm_sync_task() delegates to asyncio.run().

    pipeline_crm_sync_task.run is bound; signature is (email_id,).
    """

    @patch("src.tasks.pipeline.asyncio.run")
    def test_pipeline_crm_sync_task_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        pipeline_crm_sync_task.run(EMAIL_ID)

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 9. _run_crm_sync_with_chain — draft chaining based on email state
# ---------------------------------------------------------------------------


def _make_email_with_state(state: str) -> MagicMock:
    """Mock Email ORM object with a given state string."""
    from src.models.email import EmailState

    email = MagicMock()
    email.id = EMAIL_UUID
    email.state = EmailState(state)
    return email


def _make_crm_chain_sys_patches(
    email_state_after_sync: str,
) -> tuple[dict[str, MagicMock], MagicMock]:
    """Build sys.modules patches for _run_crm_sync_with_chain.

    _run_crm_sync_with_chain does two things:
      1. Calls ``_run_crm_sync(task, email_id_str)`` (delegated to crm_sync_task module)
      2. Queries DB for current email state to decide chain

    Returns (patches_dict, mock_run_crm_sync).
    """
    from src.models.email import Email, EmailState

    mock_run_crm_sync = AsyncMock(return_value=None)

    mock_crm_sync_task_mod = MagicMock()
    mock_crm_sync_task_mod._run_crm_sync = mock_run_crm_sync

    # Email after sync: state comes from the second DB query inside _run_crm_sync_with_chain
    mock_email = _make_email_with_state(email_state_after_sync)
    mock_db_ctx = _build_db_context(mock_email)

    mock_db_mod = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

    mock_email_mod = MagicMock()
    mock_email_mod.Email = Email
    mock_email_mod.EmailState = EmailState

    patches = {
        "src.tasks.crm_sync_task": mock_crm_sync_task_mod,
        "src.core.database": mock_db_mod,
        "src.models.email": mock_email_mod,
    }
    return patches, mock_run_crm_sync


class TestRunCrmSyncWithChain:
    """_run_crm_sync_with_chain chains to pipeline_draft_task on CRM_SYNCED state."""

    @pytest.mark.asyncio
    async def test_chains_to_draft_when_crm_synced(self) -> None:
        """Email in CRM_SYNCED state -> pipeline_draft_task.delay called."""
        patches, mock_run_crm_sync = _make_crm_chain_sys_patches("CRM_SYNCED")
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task:
                await _run_crm_sync_with_chain(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_draft_task.delay.assert_called_once_with(EMAIL_ID)

    @pytest.mark.asyncio
    async def test_no_draft_chain_when_crm_sync_failed(self) -> None:
        """Email in CRM_SYNC_FAILED state -> pipeline_draft_task.delay NOT called."""
        patches, _ = _make_crm_chain_sys_patches("CRM_SYNC_FAILED")
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task:
                await _run_crm_sync_with_chain(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_draft_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_draft_chain_when_email_not_found_after_sync(self) -> None:
        """Email disappears from DB after CRM sync -> no draft enqueued, no error."""
        from src.models.email import Email, EmailState

        mock_run_crm_sync = AsyncMock(return_value=None)
        mock_crm_sync_task_mod = MagicMock()
        mock_crm_sync_task_mod._run_crm_sync = mock_run_crm_sync

        # DB returns None (email deleted between sync and state check)
        mock_db_ctx = _build_db_context(None)
        mock_db_mod = MagicMock()
        mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

        mock_email_mod = MagicMock()
        mock_email_mod.Email = Email
        mock_email_mod.EmailState = EmailState

        patches = {
            "src.tasks.crm_sync_task": mock_crm_sync_task_mod,
            "src.core.database": mock_db_mod,
            "src.models.email": mock_email_mod,
        }
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task:
                await _run_crm_sync_with_chain(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_draft_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_crm_sync_is_awaited_before_state_check(self) -> None:
        """_run_crm_sync is always called regardless of chain decision."""
        patches, mock_run_crm_sync = _make_crm_chain_sys_patches("CRM_SYNCED")
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_draft_task"):
                await _run_crm_sync_with_chain(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        mock_run_crm_sync.assert_awaited_once_with(mock_task, EMAIL_ID)

    @pytest.mark.asyncio
    async def test_draft_delay_receives_correct_email_id_str(self) -> None:
        """pipeline_draft_task.delay receives the same email_id_str."""
        patches, _ = _make_crm_chain_sys_patches("CRM_SYNCED")
        mock_task = _make_mock_task()

        originals = _apply_patches(patches)
        try:
            with patch("src.tasks.pipeline.pipeline_draft_task") as mock_draft_task:
                await _run_crm_sync_with_chain(mock_task, EMAIL_ID)
        finally:
            _restore_patches(originals)

        call_arg = mock_draft_task.delay.call_args.args[0]
        assert call_arg == EMAIL_ID
        assert isinstance(call_arg, str)


# ---------------------------------------------------------------------------
# 10. pipeline_draft_task — thin sync wrapper delegates to _run_draft_generation
# ---------------------------------------------------------------------------


class TestPipelineDraftTaskEntryPoint:
    """pipeline_draft_task() delegates _run_draft_generation via asyncio.run().

    pipeline_draft_task.run is bound to the Celery task; signature is (email_id,).
    """

    @patch("src.tasks.pipeline.asyncio.run")
    def test_pipeline_draft_task_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        pipeline_draft_task.run(EMAIL_ID)

        mock_run.assert_called_once()

    @patch("src.tasks.pipeline.asyncio.run")
    def test_pipeline_draft_task_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = _close_coro_and_return

        result = pipeline_draft_task.run(EMAIL_ID)

        assert result is None

    @patch("src.tasks.pipeline.asyncio.run")
    def test_pipeline_draft_task_propagates_exception(self, mock_run: MagicMock) -> None:
        """If asyncio.run raises, pipeline_draft_task propagates the original exception.

        Celery propagates the original exception via ``raise self.retry(exc=exc) from exc``.
        """
        mock_run.side_effect = RuntimeError("upstream failure")

        with pytest.raises(RuntimeError, match="upstream failure"):
            pipeline_draft_task.run(EMAIL_ID)

    def test_pipeline_draft_task_invokes_correct_coroutine(self) -> None:
        """pipeline_draft_task passes _run_draft_generation coroutine to asyncio.run."""
        import inspect

        captured: list[object] = []

        def _capture_and_return(coro: object) -> None:
            captured.append(coro)
            # Close the coroutine to avoid ResourceWarning
            if inspect.iscoroutine(coro):
                coro.close()

        with patch("src.tasks.pipeline.asyncio.run", side_effect=_capture_and_return):
            pipeline_draft_task.run(EMAIL_ID)

        assert len(captured) == 1
        coro = captured[0]
        assert inspect.iscoroutine(coro)
        # Coroutine should be _run_draft_generation from draft_generation_task module
        assert coro.__qualname__ == "_run_draft_generation"
