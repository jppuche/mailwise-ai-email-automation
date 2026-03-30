"""Tests for the draft generation Celery task wrapper.

Strategy: test _run_draft_generation() directly as an async function (the real
logic). draft_generation_task() is a thin asyncio.run() wrapper tested separately.

All external dependencies are patched via the deferred-import path used
inside _run_draft_generation. The DraftGenerationService import is patched at
the module path so tests remain independent of the real service.

Scenarios:
  1. Email not found -> logs error, returns normally (no retry, no exception).
  2. LLMRateLimitError with retry_after_seconds -> task.retry raised with countdown.
  3. LLMRateLimitError with retry_after_seconds=None -> task.retry raised with 60s fallback.
  4. Generic exception -> task.retry raised with default backoff (no countdown).
  5. Success -> service.generate() called, no exception raised.
  6. Entry point (draft_generation_task) -> delegates to asyncio.run().
  7. Entry point propagates task.retry exception from asyncio.run().
  8. Body truncation -> body_snippet capped to max_body_length.
  9. email.body_plain is None -> body_snippet falls back to empty string.
"""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.draft_generation_task import _run_draft_generation, draft_generation_task

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMAIL_ID = str(uuid.uuid4())
EMAIL_UUID = uuid.UUID(EMAIL_ID)


def _make_mock_email(body_plain: str | None = "Hello, this is the email body.") -> MagicMock:
    """Build a mock Email ORM object with all fields _run_draft_generation accesses."""
    email = MagicMock()
    email.id = EMAIL_UUID
    email.sender_email = "sender@example.com"
    email.sender_name = "Test Sender"
    email.subject = "Test subject"
    email.body_plain = body_plain
    email.date = MagicMock()
    email.date.isoformat.return_value = "2026-02-28T10:00:00"
    return email


def _make_mock_settings(
    *,
    max_body_length: int = 4000,
    draft_push_to_gmail: bool = False,
    draft_generation_retry_max: int = 3,
    draft_org_prohibited_language: str = "",
) -> MagicMock:
    """Build a mock Settings object with all fields _run_draft_generation accesses."""
    settings = MagicMock()
    settings.draft_org_system_prompt = "You are a helpful assistant."
    settings.draft_org_tone = "professional"
    settings.draft_org_signature = "Best regards"
    settings.draft_org_prohibited_language = draft_org_prohibited_language
    settings.draft_push_to_gmail = draft_push_to_gmail
    settings.draft_generation_retry_max = draft_generation_retry_max
    settings.llm_model_classify = "gpt-4o-mini"
    settings.llm_model_draft = "gpt-4o"
    settings.llm_fallback_model = "gpt-3.5-turbo"
    settings.openai_api_key = "test-key"
    settings.llm_base_url = ""
    settings.llm_timeout_seconds = 30
    settings.max_body_length = max_body_length
    return settings


def _make_mock_task() -> MagicMock:
    """Build a mock Celery self (task instance).

    task.retry() raises RuntimeError in tests so that ``raise task.retry(...)``
    propagates a catchable exception. The side_effect captures kwargs for assertion.
    """
    task = MagicMock()
    task.retry.side_effect = RuntimeError("task.retry called")
    return task


def _build_db_context(email: MagicMock | None) -> AsyncMock:
    """Return an AsyncMock context manager for AsyncSessionLocal()."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = email
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _patch_all(
    mock_email: MagicMock | None,
    *,
    generate_side_effect: Exception | None = None,
    mock_settings: MagicMock | None = None,
) -> tuple[MagicMock, MagicMock, AsyncMock, MagicMock, MagicMock]:
    """Build mock dependencies for _run_draft_generation.

    Returns (mock_settings, mock_llm_adapter, mock_email_adapter, mock_db_ctx, mock_service).
    Pass results to _sys_modules_patches() for sys.modules injection.
    """
    settings = mock_settings if mock_settings is not None else _make_mock_settings()

    mock_llm_adapter = MagicMock()
    mock_email_adapter = MagicMock()

    mock_service = MagicMock()
    if generate_side_effect is not None:
        mock_service.generate = AsyncMock(side_effect=generate_side_effect)
    else:
        mock_service.generate = AsyncMock(return_value=None)

    mock_db_ctx = _build_db_context(mock_email)

    return settings, mock_llm_adapter, mock_email_adapter, mock_db_ctx, mock_service


# ---------------------------------------------------------------------------
# sys.modules injection helper
# ---------------------------------------------------------------------------


def _sys_modules_patches(
    mock_settings: MagicMock,
    mock_llm_adapter_instance: MagicMock,
    mock_email_adapter_instance: MagicMock,
    mock_db_ctx: AsyncMock,
    mock_service_instance: MagicMock,
) -> dict[str, MagicMock]:
    """Build sys.modules patches for deferred imports inside _run_draft_generation.

    Each key is the module path imported with ``from X import Y`` inside the function.
    We inject mocks so that when Python executes those imports, it gets our mocks.
    """
    from src.adapters.llm.exceptions import LLMRateLimitError
    from src.models.email import EmailState

    # Mock DraftGenerationService module
    mock_draft_svc_mod = MagicMock()
    mock_draft_svc_mod.DraftGenerationService.return_value = mock_service_instance

    # Mock draft schemas — use real classes so Pydantic validation inside the task works
    from src.services.schemas.draft import (
        ClassificationContext,
        DraftGenerationConfig,
        DraftRequest,
        EmailContent,
        OrgContext,
    )

    mock_draft_schemas_mod = MagicMock()
    mock_draft_schemas_mod.ClassificationContext = ClassificationContext
    mock_draft_schemas_mod.DraftGenerationConfig = DraftGenerationConfig
    mock_draft_schemas_mod.DraftRequest = DraftRequest
    mock_draft_schemas_mod.EmailContent = EmailContent
    mock_draft_schemas_mod.OrgContext = OrgContext

    # Mock config module
    mock_config_mod = MagicMock()
    mock_config_mod.get_settings.return_value = mock_settings

    # Mock LiteLLM adapter module
    mock_llm_mod = MagicMock()
    mock_llm_mod.LiteLLMAdapter.return_value = mock_llm_adapter_instance

    # Mock LLM schemas (LLMConfig) — use real class so construction works
    from src.adapters.llm.schemas import LLMConfig

    mock_llm_schemas_mod = MagicMock()
    mock_llm_schemas_mod.LLMConfig = LLMConfig

    # Mock Gmail adapter module
    mock_gmail_mod = MagicMock()
    mock_gmail_mod.GmailAdapter.return_value = mock_email_adapter_instance

    # Mock database module
    mock_db_mod = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

    # Mock LLM exceptions (real class so isinstance checks work)
    mock_llm_exc_mod = MagicMock()
    mock_llm_exc_mod.LLMRateLimitError = LLMRateLimitError

    # Mock email model (real EmailState for transition completeness)
    from src.models.email import Email

    mock_email_mod = MagicMock()
    mock_email_mod.Email = Email
    mock_email_mod.EmailState = EmailState

    return {
        "src.services.draft_generation": mock_draft_svc_mod,
        "src.services.schemas.draft": mock_draft_schemas_mod,
        "src.core.config": mock_config_mod,
        "src.adapters.llm.litellm_adapter": mock_llm_mod,
        "src.adapters.llm.schemas": mock_llm_schemas_mod,
        "src.adapters.email.gmail": mock_gmail_mod,
        "src.core.database": mock_db_mod,
        "src.adapters.llm.exceptions": mock_llm_exc_mod,
        "src.models.email": mock_email_mod,
    }


# ---------------------------------------------------------------------------
# Helper to run _run_draft_generation with full sys.modules injection
# ---------------------------------------------------------------------------


async def _run_with_patches(
    mock_email: MagicMock | None,
    task: MagicMock,
    *,
    generate_side_effect: Exception | None = None,
    mock_settings: MagicMock | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Run _run_draft_generation with all dependencies mocked.

    Returns (mock_service, mock_db_ctx, settings) for assertions.
    """
    settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
        mock_email,
        generate_side_effect=generate_side_effect,
        mock_settings=mock_settings,
    )
    patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

    originals: dict[str, types.ModuleType | None] = {}
    for key, val in patches.items():
        originals[key] = sys.modules.get(key)
        sys.modules[key] = val
    try:
        await _run_draft_generation(task, EMAIL_ID)
    finally:
        for key, original in originals.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original

    return mock_service, mock_db_ctx, settings


# ---------------------------------------------------------------------------
# Tests: draft_generation_task entry point (sync wrapper)
# ---------------------------------------------------------------------------


class TestDraftGenerationTaskEntryPoint:
    """Tests for the thin draft_generation_task() wrapper."""

    @patch("src.tasks.draft_generation_task.asyncio.run")
    def test_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.return_value = None
        mock_task = _make_mock_task()

        draft_generation_task(mock_task, EMAIL_ID)

        mock_run.assert_called_once()

    @patch("src.tasks.draft_generation_task.asyncio.run")
    def test_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = None
        mock_task = _make_mock_task()

        draft_generation_task(mock_task, EMAIL_ID)
        # draft_generation_task always returns None — assert no exception raised

    @patch("src.tasks.draft_generation_task.asyncio.run")
    def test_propagates_retry_exception(self, mock_run: MagicMock) -> None:
        """If _run_draft_generation raises (task.retry), asyncio.run propagates it."""
        mock_run.side_effect = RuntimeError("task.retry called")
        mock_task = _make_mock_task()

        with pytest.raises(RuntimeError, match="task.retry called"):
            draft_generation_task(mock_task, EMAIL_ID)


# ---------------------------------------------------------------------------
# Tests: _run_draft_generation — email not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunDraftGenerationEmailNotFound:
    """Email not found -> logs error, returns normally (no retry, no exception)."""

    async def test_email_not_found_returns_normally(self) -> None:
        mock_task = _make_mock_task()

        mock_service, mock_db_ctx, _ = await _run_with_patches(None, mock_task)

        mock_service.generate.assert_not_called()
        mock_task.retry.assert_not_called()

    async def test_email_not_found_return_value_is_none(self) -> None:
        mock_task = _make_mock_task()
        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(None)
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        # _run_draft_generation returns None implicitly — no exception means success
        mock_service.generate.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _run_draft_generation — LLMRateLimitError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunDraftGenerationRateLimitError:
    """LLMRateLimitError -> task.retry raised with countdown derived from exception."""

    async def test_rate_limit_with_retry_after_seconds_raises_retry(self) -> None:
        from src.adapters.llm.exceptions import LLMRateLimitError

        mock_email = _make_mock_email()
        exc = LLMRateLimitError("rate limited", retry_after_seconds=45)
        mock_task = _make_mock_task()
        retry_exc = RuntimeError("task.retry called: countdown=45")
        mock_task.retry.side_effect = retry_exc

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, generate_side_effect=exc
        )
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(RuntimeError, match="task.retry called"):
                await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("countdown") == 45

    async def test_rate_limit_without_retry_after_uses_fallback_60s(self) -> None:
        """retry_after_seconds=None -> countdown defaults to 60."""
        from src.adapters.llm.exceptions import LLMRateLimitError

        mock_email = _make_mock_email()
        exc = LLMRateLimitError("rate limited", retry_after_seconds=None)
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry called")

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, generate_side_effect=exc
        )
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(RuntimeError):
                await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        # countdown=60 is the hardcoded fallback in the task (``exc.retry_after_seconds or 60``)
        assert call_kwargs.kwargs.get("countdown") == 60

    async def test_rate_limit_passes_exc_kwarg_to_retry(self) -> None:
        """task.retry receives exc=<original LLMRateLimitError>."""
        from src.adapters.llm.exceptions import LLMRateLimitError

        mock_email = _make_mock_email()
        exc = LLMRateLimitError("rate limited", retry_after_seconds=10)
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("retry")

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, generate_side_effect=exc
        )
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(RuntimeError):
                await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("exc") is exc


# ---------------------------------------------------------------------------
# Tests: _run_draft_generation — generic exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunDraftGenerationGenericException:
    """Unexpected exceptions -> task.retry raised with no countdown (Celery default)."""

    async def test_generic_exception_raises_retry(self) -> None:
        mock_email = _make_mock_email()
        boom = ConnectionError("DB gone")
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry generic")

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, generate_side_effect=boom
        )
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(RuntimeError, match="task.retry generic"):
                await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args
        # Generic retry: no countdown kwarg (uses Celery exponential default)
        assert call_kwargs.kwargs.get("countdown") is None

    async def test_generic_exception_passes_exc_to_retry(self) -> None:
        """task.retry receives exc=<original exception>."""
        mock_email = _make_mock_email()
        boom = ValueError("unexpected payload")
        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("retry")

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, generate_side_effect=boom
        )
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            with pytest.raises(RuntimeError):
                await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("exc") is boom


# ---------------------------------------------------------------------------
# Tests: _run_draft_generation — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunDraftGenerationSuccess:
    """Successful generation -> service.generate() called, no exception raised."""

    async def test_success_calls_generate(self) -> None:
        mock_email = _make_mock_email()
        mock_task = _make_mock_task()

        mock_service, _, _ = await _run_with_patches(mock_email, mock_task)

        mock_service.generate.assert_awaited_once()
        mock_task.retry.assert_not_called()

    async def test_success_passes_correct_email_id(self) -> None:
        """DraftRequest.email_id must match the email loaded from DB."""
        mock_email = _make_mock_email()
        mock_task = _make_mock_task()

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(mock_email)
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_args = mock_service.generate.call_args
        draft_request = call_args.args[0]
        assert draft_request.email_id == EMAIL_UUID

    async def test_body_plain_none_uses_empty_string(self) -> None:
        """email.body_plain is None -> body_snippet falls back to empty string."""
        mock_email = _make_mock_email(body_plain=None)
        mock_task = _make_mock_task()

        settings, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(mock_email)
        patches = _sys_modules_patches(settings, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_args = mock_service.generate.call_args
        draft_request = call_args.args[0]
        assert draft_request.email_content.body_snippet == ""
        mock_task.retry.assert_not_called()

    async def test_body_truncated_to_max_body_length(self) -> None:
        """body_plain longer than max_body_length is truncated before DraftRequest."""
        long_body = "x" * 5000
        mock_email = _make_mock_email(body_plain=long_body)
        mock_task = _make_mock_task()
        settings = _make_mock_settings(max_body_length=100)

        settings2, mock_llm, mock_gmail, mock_db_ctx, mock_service = _patch_all(
            mock_email, mock_settings=settings
        )
        patches = _sys_modules_patches(settings2, mock_llm, mock_gmail, mock_db_ctx, mock_service)

        originals: dict[str, types.ModuleType | None] = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val
        try:
            await _run_draft_generation(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_args = mock_service.generate.call_args
        draft_request = call_args.args[0]
        assert len(draft_request.email_content.body_snippet) == 100
        assert draft_request.email_content.body_snippet == "x" * 100
