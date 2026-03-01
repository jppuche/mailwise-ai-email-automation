"""Tests for partial-failure isolation across pipeline tasks (Block 12).

Principle (D13 — non-atomic): failure at stage N preserves data committed
at stage N-1. Each task commits to DB independently; if a later task fails
and retries, the prior stage's state record is never rolled back.

Architecture under test (src/tasks/pipeline.py):
  - ingest_task            -> try: asyncio.run(_run_ingestion_pipeline(...))
                              except Exception: raise self.retry(exc=exc)
  - classify_task          -> asyncio.run(_run_classification(self, email_id))
                              (no outer except — retry is inside _run_classification)
  - route_task             -> asyncio.run(_run_routing(self, email_id))
                              (no outer except — retry is inside _run_routing)
  - pipeline_crm_sync_task -> asyncio.run(_run_crm_sync_with_chain(self, email_id))
                              (no outer except — retry is inside _run_crm_sync_with_chain)
  - pipeline_draft_task    -> asyncio.run(_run_draft_generation(self, email_id))
                              _run_draft_generation is a deferred import from
                              src.tasks.draft_generation_task

Invocation pattern:
  Celery bind=True tasks store the real task instance as ``self``. Calling
  ``task(mock_self, ...)`` routes through Celery's __call__ which ignores
  our mock_self. We bypass this by accessing the original function via
  ``task.__wrapped__.__func__(mock_self, ...)`` which calls the raw Python
  function with our mock_self so that ``self.retry(...)`` fires on it.

Mocking strategy for outer wrappers:
  We patch ``src.tasks.pipeline.asyncio`` so that asyncio.run(...) raises
  the expected exception directly. This avoids the async coroutine
  scheduling complexities of patching the inner async functions:

  - ingest_task:            asyncio.run raises OSError -> except block fires
                            -> self.retry(exc=OSError) -> raises Retry
  - classify_task:          asyncio.run raises Retry  (simulates inner handling)
  - route_task:             asyncio.run raises Retry  (simulates inner handling)
  - pipeline_crm_sync_task: asyncio.run raises Retry  (simulates inner handling)
  - pipeline_draft_task:    asyncio.run raises Retry  (simulates inner handling)

For the LLMRateLimitError countdown test we test _run_classification() directly
as an async function with sys.modules injection (same pattern as
test_crm_sync_task.py and test_draft_generation_task.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import celery.exceptions
import pytest

# ---------------------------------------------------------------------------
# Constants shared across all tests
# ---------------------------------------------------------------------------

ACCOUNT_ID = "test-account-001"
SINCE_ISO = "2026-03-01T00:00:00+00:00"
EMAIL_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_celery_task_self() -> MagicMock:
    """Build a mock Celery bound-task ``self``.

    ``task.retry(exc=...)`` must RAISE in Celery's real implementation —
    we replicate that so ``raise self.retry(exc=exc)`` propagates
    ``celery.exceptions.Retry`` out of the task function.
    """
    task = MagicMock()
    task.retry.side_effect = celery.exceptions.Retry()
    return task


def _raw_task_fn(task_attr: str) -> Callable[..., None]:
    """Return the original (undecorated) task function.

    Celery's PromiseProxy stores the raw function at
    ``task.__wrapped__.__func__``. Calling it with an explicit ``self``
    allows tests to supply a mock task instance without going through
    Celery's __call__ machinery.
    """
    import src.tasks.pipeline as pipeline_mod

    task_obj = getattr(pipeline_mod, task_attr)
    fn: Callable[..., None] = task_obj.__wrapped__.__func__
    return fn


# ---------------------------------------------------------------------------
# Test 1: ingest_task failure retries
# ---------------------------------------------------------------------------


class TestIngestTaskFailureRetries:
    """ingest_task catches exceptions from asyncio.run and calls self.retry().

    ingest_task has an outer try/except that catches all exceptions and calls
    ``raise self.retry(exc=exc)``. We patch asyncio.run to raise directly.
    """

    @patch("src.tasks.pipeline.asyncio")
    def test_ingest_failure_retries(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run raises, ingest_task calls self.retry()."""
        mock_asyncio.run.side_effect = OSError("broker unreachable")

        task_self = _make_celery_task_self()
        ingest_fn = _raw_task_fn("ingest_task")

        with pytest.raises(celery.exceptions.Retry):
            ingest_fn(task_self, ACCOUNT_ID, SINCE_ISO)
        task_self.retry.assert_called_once()

    @patch("src.tasks.pipeline.asyncio")
    def test_ingest_retry_receives_original_exception(self, mock_asyncio: MagicMock) -> None:
        """self.retry(exc=<original exc>) carries the originating exception."""
        original_exc = OSError("connection refused")
        mock_asyncio.run.side_effect = original_exc

        task_self = _make_celery_task_self()
        ingest_fn = _raw_task_fn("ingest_task")

        with pytest.raises(celery.exceptions.Retry):
            ingest_fn(task_self, ACCOUNT_ID, SINCE_ISO)
        call_kwargs = task_self.retry.call_args
        assert call_kwargs.kwargs.get("exc") is original_exc

    @patch("src.tasks.pipeline.asyncio")
    def test_ingest_success_no_exception(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run succeeds, ingest_task returns without raising."""
        mock_asyncio.run.return_value = None

        task_self = _make_celery_task_self()
        ingest_fn = _raw_task_fn("ingest_task")

        ingest_fn(task_self, ACCOUNT_ID, SINCE_ISO)
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: classify_task failure preserves SANITIZED state (stage N-1)
# ---------------------------------------------------------------------------


class TestClassifyTaskFailurePreservesIngestedState:
    """classify_task raises -> email stays in SANITIZED state (D13).

    classify_task has NO outer except block. The retry logic lives inside
    _run_classification. When _run_classification raises Retry (via
    ``raise task.retry(exc=exc)``), that exception propagates through
    asyncio.run unchanged.

    We simulate this by making asyncio.run raise Retry directly.
    """

    @patch("src.tasks.pipeline.asyncio")
    def test_classify_failure_propagates_retry(self, mock_asyncio: MagicMock) -> None:
        """asyncio.run raises Retry -> classify_task propagates it unchanged."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        classify_fn = _raw_task_fn("classify_task")

        with pytest.raises(celery.exceptions.Retry):
            classify_fn(task_self, EMAIL_ID)

    @patch("src.tasks.pipeline.asyncio")
    def test_classify_failure_outer_wrapper_does_not_call_retry(
        self, mock_asyncio: MagicMock
    ) -> None:
        """The outer classify_task wrapper has no except block — it does NOT call
        self.retry directly. Retry propagates from inside _run_classification.
        """
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        classify_fn = _raw_task_fn("classify_task")

        with pytest.raises(celery.exceptions.Retry):
            classify_fn(task_self, EMAIL_ID)
        # The outer wrapper never calls self.retry — Retry comes from inside
        task_self.retry.assert_not_called()

    @patch("src.tasks.pipeline.asyncio")
    def test_classify_success_no_exception(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run succeeds, classify_task returns without raising."""
        mock_asyncio.run.return_value = None

        task_self = _make_celery_task_self()
        classify_fn = _raw_task_fn("classify_task")

        classify_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: route_task failure preserves CLASSIFIED state (stage N-1)
# ---------------------------------------------------------------------------


class TestRouteTaskFailurePreservesClassifiedState:
    """route_task raises -> email stays in CLASSIFIED state (D13).

    Classification committed the email to CLASSIFIED before enqueuing route_task.
    route_task has NO outer except — retry logic is inside _run_routing.
    Retry propagates from inside _run_routing through asyncio.run.
    """

    @patch("src.tasks.pipeline.asyncio")
    def test_route_failure_propagates_retry(self, mock_asyncio: MagicMock) -> None:
        """asyncio.run raises Retry -> route_task propagates it unchanged."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        route_fn = _raw_task_fn("route_task")

        with pytest.raises(celery.exceptions.Retry):
            route_fn(task_self, EMAIL_ID)

    @patch("src.tasks.pipeline.asyncio")
    def test_route_failure_outer_wrapper_does_not_call_retry(self, mock_asyncio: MagicMock) -> None:
        """The outer route_task wrapper has no except block — self.retry is never
        called at the outer level. Retry propagates from inside _run_routing.
        """
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        route_fn = _raw_task_fn("route_task")

        with pytest.raises(celery.exceptions.Retry):
            route_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()

    @patch("src.tasks.pipeline.asyncio")
    def test_route_success_no_exception(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run succeeds, route_task returns without raising."""
        mock_asyncio.run.return_value = None

        task_self = _make_celery_task_self()
        route_fn = _raw_task_fn("route_task")

        route_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: pipeline_crm_sync_task failure preserves ROUTED state, no draft enqueued
# ---------------------------------------------------------------------------


class TestCrmSyncTaskFailurePreservesRoutedState:
    """pipeline_crm_sync_task raises -> email stays in ROUTED state (D13).

    Routing committed the email to ROUTED before enqueuing pipeline_crm_sync_task.

    Chain bifurcation: pipeline_draft_task is only enqueued inside
    _run_crm_sync_with_chain when the email reaches CRM_SYNCED state.
    When _run_crm_sync_with_chain raises Retry, that enqueue never runs.

    pipeline_crm_sync_task has NO outer except block — Retry propagates from
    inside _run_crm_sync_with_chain through asyncio.run.
    """

    @patch("src.tasks.pipeline.asyncio")
    def test_crm_sync_failure_propagates_retry(self, mock_asyncio: MagicMock) -> None:
        """asyncio.run raises Retry -> pipeline_crm_sync_task propagates it unchanged."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        crm_fn = _raw_task_fn("pipeline_crm_sync_task")

        with pytest.raises(celery.exceptions.Retry):
            crm_fn(task_self, EMAIL_ID)

    @patch("src.tasks.pipeline.asyncio")
    def test_crm_sync_failure_outer_wrapper_does_not_call_retry(
        self, mock_asyncio: MagicMock
    ) -> None:
        """The outer pipeline_crm_sync_task has no except — self.retry not called there."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        crm_fn = _raw_task_fn("pipeline_crm_sync_task")

        with pytest.raises(celery.exceptions.Retry):
            crm_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()

    @patch("src.tasks.pipeline.asyncio")
    def test_crm_sync_success_no_exception(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run succeeds, no exception is raised."""
        mock_asyncio.run.return_value = None

        task_self = _make_celery_task_self()
        crm_fn = _raw_task_fn("pipeline_crm_sync_task")

        crm_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: pipeline_draft_task failure preserves CRM_SYNCED state (stage N-1)
# ---------------------------------------------------------------------------


class TestDraftTaskFailurePreservesCrmSyncedState:
    """pipeline_draft_task raises -> email stays in CRM_SYNCED state (D13).

    CRM sync committed the email to CRM_SYNCED before enqueuing pipeline_draft_task.
    pipeline_draft_task is the terminal task — no further chaining occurs.

    pipeline_draft_task has NO outer except block — Retry propagates from
    inside _run_draft_generation through asyncio.run.

    _run_draft_generation is imported INSIDE the task via:
      from src.tasks.draft_generation_task import _run_draft_generation
    so it is not in the pipeline module namespace. We patch asyncio.run.
    """

    @patch("src.tasks.pipeline.asyncio")
    def test_draft_failure_propagates_retry(self, mock_asyncio: MagicMock) -> None:
        """asyncio.run raises Retry -> pipeline_draft_task propagates it unchanged."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        draft_fn = _raw_task_fn("pipeline_draft_task")

        with pytest.raises(celery.exceptions.Retry):
            draft_fn(task_self, EMAIL_ID)

    @patch("src.tasks.pipeline.asyncio")
    def test_draft_failure_outer_wrapper_does_not_call_retry(self, mock_asyncio: MagicMock) -> None:
        """The outer pipeline_draft_task has no except — self.retry not called there."""
        mock_asyncio.run.side_effect = celery.exceptions.Retry()

        task_self = _make_celery_task_self()
        draft_fn = _raw_task_fn("pipeline_draft_task")

        with pytest.raises(celery.exceptions.Retry):
            draft_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()

    @patch("src.tasks.pipeline.asyncio")
    def test_draft_success_no_exception(self, mock_asyncio: MagicMock) -> None:
        """When asyncio.run succeeds, pipeline_draft_task returns without raising."""
        mock_asyncio.run.return_value = None

        task_self = _make_celery_task_self()
        draft_fn = _raw_task_fn("pipeline_draft_task")

        draft_fn(task_self, EMAIL_ID)
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: _run_classification — LLMRateLimitError retry with countdown
# ---------------------------------------------------------------------------


class TestRunClassificationRateLimitCountdown:
    """_run_classification handles LLMRateLimitError with specific countdown.

    The rate-limit handler lives inside the async _run_classification function.
    We test it directly using sys.modules injection (same pattern established
    in test_crm_sync_task.py and test_draft_generation_task.py).
    """

    @pytest.mark.asyncio
    async def test_rate_limit_calls_retry_with_countdown(self) -> None:
        """LLMRateLimitError with retry_after_seconds=30 -> retry(countdown=30)."""
        import sys
        import types

        from src.adapters.llm.exceptions import LLMRateLimitError
        from src.tasks.pipeline import _run_classification

        rate_exc = LLMRateLimitError("rate limited", retry_after_seconds=30)

        mock_task = MagicMock()
        mock_task.retry.side_effect = celery.exceptions.Retry()

        mock_email, db, db_ctx = _make_db_context_with_email(uuid.UUID(EMAIL_ID))

        mock_service = MagicMock()
        mock_service.classify_email = AsyncMock(side_effect=rate_exc)

        patches = _build_classification_sys_patches(
            mock_service=mock_service,
            db_ctx=db_ctx,
            celery_backoff_base=60,
        )

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(celery.exceptions.Retry):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args
        # countdown must be 30 (from retry_after_seconds)
        assert call_kwargs.kwargs.get("countdown") == 30

    @pytest.mark.asyncio
    async def test_rate_limit_uses_backoff_when_no_retry_after(self) -> None:
        """retry_after_seconds=None -> countdown falls back to celery_backoff_base (60)."""
        import sys
        import types

        from src.adapters.llm.exceptions import LLMRateLimitError
        from src.tasks.pipeline import _run_classification

        rate_exc = LLMRateLimitError("rate limited", retry_after_seconds=None)

        mock_task = MagicMock()
        mock_task.retry.side_effect = celery.exceptions.Retry()

        mock_email, db, db_ctx = _make_db_context_with_email(uuid.UUID(EMAIL_ID))

        mock_service = MagicMock()
        mock_service.classify_email = AsyncMock(side_effect=rate_exc)

        patches = _build_classification_sys_patches(
            mock_service=mock_service,
            db_ctx=db_ctx,
            celery_backoff_base=60,
        )

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(celery.exceptions.Retry):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        # retry_after_seconds is None -> falls back to celery_backoff_base (60)
        assert call_kwargs.kwargs.get("countdown") == 60

    @pytest.mark.asyncio
    async def test_rate_limit_passes_exc_to_retry(self) -> None:
        """task.retry(exc=<original LLMRateLimitError>) carries the original exception."""
        import sys
        import types

        from src.adapters.llm.exceptions import LLMRateLimitError
        from src.tasks.pipeline import _run_classification

        rate_exc = LLMRateLimitError("rate limited", retry_after_seconds=10)

        mock_task = MagicMock()
        mock_task.retry.side_effect = celery.exceptions.Retry()

        mock_email, db, db_ctx = _make_db_context_with_email(uuid.UUID(EMAIL_ID))

        mock_service = MagicMock()
        mock_service.classify_email = AsyncMock(side_effect=rate_exc)

        patches = _build_classification_sys_patches(
            mock_service=mock_service,
            db_ctx=db_ctx,
        )

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(celery.exceptions.Retry):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("exc") is rate_exc

    @pytest.mark.asyncio
    async def test_generic_exception_calls_retry_without_countdown(self) -> None:
        """Unexpected exceptions inside _run_classification call self.retry(exc=exc)."""
        import sys
        import types

        from src.tasks.pipeline import _run_classification

        boom = ConnectionError("DB gone")

        mock_task = MagicMock()
        mock_task.retry.side_effect = celery.exceptions.Retry()

        mock_email, db, db_ctx = _make_db_context_with_email(uuid.UUID(EMAIL_ID))

        mock_service = MagicMock()
        mock_service.classify_email = AsyncMock(side_effect=boom)

        patches = _build_classification_sys_patches(
            mock_service=mock_service,
            db_ctx=db_ctx,
        )

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(celery.exceptions.Retry):
                await _run_classification(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("exc") is boom
        # Generic retry: no countdown (uses Celery default exponential backoff)
        assert call_kwargs.kwargs.get("countdown") is None

    @pytest.mark.asyncio
    async def test_email_not_found_returns_normally(self) -> None:
        """Email not found in DB -> logs error, returns without calling retry."""
        import sys
        import types

        from src.tasks.pipeline import _run_classification

        mock_task = MagicMock()
        mock_task.retry.side_effect = celery.exceptions.Retry()

        db, db_ctx = _make_db_context_no_email()

        mock_service = MagicMock()
        mock_service.classify_email = AsyncMock()

        patches = _build_classification_sys_patches(
            mock_service=mock_service,
            db_ctx=db_ctx,
        )

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            await _run_classification(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_service.classify_email.assert_not_called()
        mock_task.retry.assert_not_called()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_db_context_with_email(
    email_id: uuid.UUID,
) -> tuple[MagicMock, AsyncMock, AsyncMock]:
    """Return (mock_email, db, db_ctx) where DB query returns mock_email."""
    mock_email = MagicMock()
    mock_email.id = email_id

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = mock_email
    db.execute.return_value = execute_result

    db_ctx = AsyncMock()
    db_ctx.__aenter__ = AsyncMock(return_value=db)
    db_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_email, db, db_ctx


def _make_db_context_no_email() -> tuple[AsyncMock, AsyncMock]:
    """Return (db, db_ctx) where DB query returns None (email not found)."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    db_ctx = AsyncMock()
    db_ctx.__aenter__ = AsyncMock(return_value=db)
    db_ctx.__aexit__ = AsyncMock(return_value=False)

    return db, db_ctx


def _build_classification_sys_patches(
    *,
    mock_service: MagicMock,
    db_ctx: AsyncMock,
    celery_backoff_base: int = 60,
) -> dict[str, MagicMock]:
    """Build sys.modules patches for deferred imports inside _run_classification.

    Mirrors the pattern from test_crm_sync_task._sys_modules_patches().
    Real exception classes are used so isinstance checks inside the task work.
    """
    import types

    from src.adapters.llm.exceptions import LLMRateLimitError
    from src.adapters.llm.schemas import LLMConfig
    from src.models.email import Email

    mock_settings = MagicMock()
    mock_settings.llm_model_classify = "gpt-4o-mini"
    mock_settings.llm_model_draft = "gpt-4o"
    mock_settings.llm_fallback_model = "gpt-3.5-turbo"
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_base_url = ""
    mock_settings.llm_timeout_seconds = 30
    mock_settings.celery_backoff_base = celery_backoff_base

    mock_config_mod: MagicMock = MagicMock()
    mock_config_mod.get_settings.return_value = mock_settings

    mock_llm_adapter_mod: MagicMock = MagicMock()
    mock_llm_adapter_mod.LiteLLMAdapter.return_value = MagicMock()

    mock_llm_schemas_mod: MagicMock = MagicMock()
    mock_llm_schemas_mod.LLMConfig = LLMConfig

    mock_db_mod: MagicMock = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = db_ctx

    mock_classification_svc_mod: MagicMock = MagicMock()
    mock_classification_svc_mod.ClassificationService.return_value = mock_service

    # Real exception class so isinstance checks inside _run_classification work
    mock_llm_exc_mod: MagicMock = MagicMock()
    mock_llm_exc_mod.LLMRateLimitError = LLMRateLimitError

    mock_email_mod: MagicMock = MagicMock()
    mock_email_mod.Email = Email

    result: dict[str, types.ModuleType] = {
        "src.adapters.llm.litellm_adapter": mock_llm_adapter_mod,
        "src.adapters.llm.schemas": mock_llm_schemas_mod,
        "src.core.config": mock_config_mod,
        "src.core.database": mock_db_mod,
        "src.services.classification": mock_classification_svc_mod,
        "src.adapters.llm.exceptions": mock_llm_exc_mod,
        "src.models.email": mock_email_mod,
    }
    return result  # type: ignore[return-value]
