"""Tests for the CRM sync Celery task wrapper.

Strategy: test _run_crm_sync() directly as an async function (the real
logic). crm_sync_task() is a thin asyncio.run() wrapper tested separately.

All external dependencies are patched via the deferred-import path used
inside _run_crm_sync. The CRMSyncService does not exist yet (built by
another module) -- its import is patched at the module path.

Scenarios:
  1. CRMAuthError -> CRM_SYNC_FAILED, no retry raised.
  2. CRMRateLimitError -> task.retry raised with countdown.
  3. Generic exception -> task.retry raised with default backoff.
  4. Email not found -> logs error, returns normally.
  5. Success (overall_success=True) -> email transitions to CRM_SYNCED.
  6. Service returns overall_success=False -> email transitions to CRM_SYNC_FAILED.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.crm_sync_task import _run_crm_sync, crm_sync_task

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMAIL_ID = str(uuid.uuid4())
EMAIL_UUID = uuid.UUID(EMAIL_ID)


def _make_mock_email(state: str = "ROUTED") -> MagicMock:
    """Build a mock Email ORM object."""
    email = MagicMock()
    email.id = EMAIL_UUID
    email.sender_email = "sender@example.com"
    email.sender_name = "Test Sender"
    email.subject = "Test subject"
    email.snippet = "Short snippet"
    email.date = MagicMock()
    email.state = state
    return email


def _make_mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.hubspot_access_token = "test-token"
    settings.hubspot_auto_create_contacts = False
    settings.hubspot_activity_snippet_length = 200
    settings.crm_sync_retry_max = 3
    settings.crm_sync_backoff_base_seconds = 60
    return settings


def _make_mock_task() -> MagicMock:
    """Build a mock Celery self (task instance).

    task.retry() raises a RuntimeError in tests so that `raise task.retry(...)`
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


# ---------------------------------------------------------------------------
# Approach: patch all deferred imports so they resolve cleanly.
# Since the function does `from src.X import Y` internally, we patch the
# modules before they are imported with sys.modules patching.
# ---------------------------------------------------------------------------


def _patch_all(
    mock_email: MagicMock | None,
    mock_sync_result: MagicMock | None = None,
    sync_side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock, AsyncMock, MagicMock]:
    """Build mock dependencies for _run_crm_sync.

    Returns (mock_settings, mock_adapter, mock_db_ctx, mock_service).
    Pass results to _sys_modules_patches() for sys.modules injection.
    """
    mock_settings = _make_mock_settings()
    mock_adapter = AsyncMock()
    mock_adapter.connect = AsyncMock()

    mock_service = MagicMock()
    if sync_side_effect is not None:
        mock_service.sync = AsyncMock(side_effect=sync_side_effect)
    else:
        mock_service.sync = AsyncMock(return_value=mock_sync_result)

    mock_db_ctx = _build_db_context(mock_email)

    return mock_settings, mock_adapter, mock_db_ctx, mock_service


# ---------------------------------------------------------------------------
# Tests for crm_sync_task (sync entry point)
# ---------------------------------------------------------------------------


class TestCrmSyncTaskEntryPoint:
    """Tests for the thin crm_sync_task() wrapper."""

    @patch("src.tasks.crm_sync_task.asyncio.run")
    def test_calls_asyncio_run(self, mock_run: MagicMock) -> None:
        mock_run.return_value = None
        mock_task = _make_mock_task()

        crm_sync_task(mock_task, EMAIL_ID)

        mock_run.assert_called_once()

    @patch("src.tasks.crm_sync_task.asyncio.run")
    def test_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = None
        mock_task = _make_mock_task()

        result = crm_sync_task(mock_task, EMAIL_ID)

        assert result is None

    @patch("src.tasks.crm_sync_task.asyncio.run")
    def test_propagates_retry_error(self, mock_run: MagicMock) -> None:
        """If _run_crm_sync raises (task.retry), asyncio.run propagates it."""
        mock_run.side_effect = RuntimeError("task.retry called")
        mock_task = _make_mock_task()

        with pytest.raises(RuntimeError, match="task.retry called"):
            crm_sync_task(mock_task, EMAIL_ID)


# ---------------------------------------------------------------------------
# Tests for _run_crm_sync (the real async logic)
# ---------------------------------------------------------------------------

# We patch the modules that _run_crm_sync imports from using sys.modules
# injection. This is the most reliable way to intercept deferred imports.


def _sys_modules_patches(
    mock_settings: MagicMock,
    mock_adapter_instance: AsyncMock,
    mock_db_ctx: AsyncMock,
    mock_service_instance: MagicMock,
) -> dict[str, MagicMock]:
    """Build sys.modules patches for deferred imports inside _run_crm_sync."""
    from src.adapters.crm.exceptions import CRMAuthError, CRMRateLimitError
    from src.models.email import EmailState

    # Mock CRMSyncService module
    mock_crm_sync_mod = MagicMock()
    mock_crm_sync_mod.CRMSyncService.return_value = mock_service_instance

    # Mock CRMSyncRequest / CRMSyncConfig — pass-through, use real schemas
    from src.services.schemas.crm_sync import CRMSyncConfig, CRMSyncRequest

    mock_crm_sync_schemas_mod = MagicMock()
    mock_crm_sync_schemas_mod.CRMSyncConfig = CRMSyncConfig
    mock_crm_sync_schemas_mod.CRMSyncRequest = CRMSyncRequest

    # Mock config module
    mock_config_mod = MagicMock()
    mock_config_mod.get_settings.return_value = mock_settings

    # Mock HubSpot adapter module
    mock_hubspot_mod = MagicMock()
    mock_hubspot_mod.HubSpotAdapter.return_value = mock_adapter_instance

    # Mock CRM schemas (CRMCredentials)
    from src.adapters.crm.schemas import CRMCredentials

    mock_crm_schemas_mod = MagicMock()
    mock_crm_schemas_mod.CRMCredentials = CRMCredentials

    # Mock database module
    mock_db_mod = MagicMock()
    mock_db_mod.AsyncSessionLocal.return_value = mock_db_ctx

    # Mock exceptions (real classes so isinstance checks work)
    mock_exceptions_mod = MagicMock()
    mock_exceptions_mod.CRMAuthError = CRMAuthError
    mock_exceptions_mod.CRMRateLimitError = CRMRateLimitError

    # Mock email model module (real EmailState for transitions)
    from src.models.email import Email

    mock_email_mod = MagicMock()
    mock_email_mod.Email = Email
    mock_email_mod.EmailState = EmailState

    return {
        "src.services.crm_sync": mock_crm_sync_mod,
        "src.services.schemas.crm_sync": mock_crm_sync_schemas_mod,
        "src.core.config": mock_config_mod,
        "src.adapters.crm.hubspot": mock_hubspot_mod,
        "src.adapters.crm.schemas": mock_crm_schemas_mod,
        "src.core.database": mock_db_mod,
        "src.adapters.crm.exceptions": mock_exceptions_mod,
        "src.models.email": mock_email_mod,
    }


# ---------------------------------------------------------------------------
# Parametrized test class using sys.modules patching
# ---------------------------------------------------------------------------


class TestRunCrmSyncAuthError:
    """CRMAuthError -> email=CRM_SYNC_FAILED, no task.retry raised."""

    @pytest.mark.asyncio
    async def test_auth_error_transitions_to_failed_no_retry(self) -> None:
        from src.adapters.crm.exceptions import CRMAuthError
        from src.models.email import EmailState

        mock_email = _make_mock_email()
        auth_exc = CRMAuthError("token revoked")

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            sync_side_effect=auth_exc,
        )

        # Capture what transition_to is called with
        transitions: list[EmailState] = []
        mock_email.transition_to = lambda state: transitions.append(state)

        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)
        mock_task = _make_mock_task()

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        # State must be CRM_SYNC_FAILED
        assert EmailState.CRM_SYNC_FAILED in transitions
        # DB committed (to persist the failed state)
        mock_db_ctx.__aenter__.return_value.commit.assert_awaited()
        # task.retry must NOT have been called
        mock_task.retry.assert_not_called()


class TestRunCrmSyncRateLimitError:
    """CRMRateLimitError -> task.retry raised with countdown."""

    @pytest.mark.asyncio
    async def test_rate_limit_raises_retry(self) -> None:
        from src.adapters.crm.exceptions import CRMRateLimitError

        mock_email = _make_mock_email()
        rate_exc = CRMRateLimitError("rate limited", retry_after_seconds=30)

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            sync_side_effect=rate_exc,
        )

        # task.retry should raise -- simulate Celery Retry exception
        mock_task = _make_mock_task()
        retry_exc = RuntimeError("task.retry called: countdown=30")
        mock_task.retry.side_effect = retry_exc

        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="task.retry called"):
                await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args
        # countdown should be 30 (from retry_after_seconds)
        assert call_kwargs.kwargs.get("countdown") == 30

    @pytest.mark.asyncio
    async def test_rate_limit_uses_backoff_when_no_retry_after(self) -> None:
        from src.adapters.crm.exceptions import CRMRateLimitError

        mock_email = _make_mock_email()
        # retry_after_seconds=None -> falls back to backoff_base_seconds (60)
        rate_exc = CRMRateLimitError("rate limited", retry_after_seconds=None)

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            sync_side_effect=rate_exc,
        )

        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("retry")

        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError):
                await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        call_kwargs = mock_task.retry.call_args
        # countdown must be backoff_base_seconds (60)
        assert call_kwargs.kwargs.get("countdown") == 60


class TestRunCrmSyncGenericException:
    """Unexpected exceptions -> task.retry with default backoff."""

    @pytest.mark.asyncio
    async def test_generic_exception_raises_retry(self) -> None:
        mock_email = _make_mock_email()
        boom = ConnectionError("DB unavailable")

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            sync_side_effect=boom,
        )

        mock_task = _make_mock_task()
        mock_task.retry.side_effect = RuntimeError("task.retry generic")

        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="task.retry generic"):
                await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        mock_task.retry.assert_called_once()
        # Generic retry: no countdown kwarg (uses Celery default)
        call_kwargs = mock_task.retry.call_args
        assert call_kwargs.kwargs.get("countdown") is None


class TestRunCrmSyncEmailNotFound:
    """Email not found -> log error, return normally (no retry, no exception)."""

    @pytest.mark.asyncio
    async def test_email_not_found_returns_normally(self) -> None:
        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=None,  # scalar_one_or_none returns None
        )

        mock_task = _make_mock_task()
        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            result = await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        assert result is None
        # Service should NOT be called if email is missing
        mock_service.sync.assert_not_called()
        mock_task.retry.assert_not_called()


class TestRunCrmSyncSuccess:
    """Successful sync -> email transitions to CRM_SYNCED."""

    @pytest.mark.asyncio
    async def test_success_transitions_to_crm_synced(self) -> None:
        from src.models.email import EmailState

        mock_email = _make_mock_email()
        transitions: list[EmailState] = []
        mock_email.transition_to = lambda state: transitions.append(state)

        mock_sync_result = MagicMock()
        mock_sync_result.overall_success = True
        mock_sync_result.contact_id = "hs-contact-123"

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            mock_sync_result=mock_sync_result,
        )

        mock_task = _make_mock_task()
        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        assert EmailState.CRM_SYNCED in transitions
        mock_db_ctx.__aenter__.return_value.commit.assert_awaited()
        mock_task.retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_failure_transitions_to_crm_sync_failed(self) -> None:
        """overall_success=False -> email transitions to CRM_SYNC_FAILED."""
        from src.models.email import EmailState

        mock_email = _make_mock_email()
        transitions: list[EmailState] = []
        mock_email.transition_to = lambda state: transitions.append(state)

        mock_sync_result = MagicMock()
        mock_sync_result.overall_success = False
        mock_sync_result.contact_id = None

        mock_settings, mock_adapter, mock_db_ctx, mock_service = _patch_all(
            mock_email=mock_email,
            mock_sync_result=mock_sync_result,
        )

        mock_task = _make_mock_task()
        patches = _sys_modules_patches(mock_settings, mock_adapter, mock_db_ctx, mock_service)

        import sys

        originals = {}
        for key, val in patches.items():
            originals[key] = sys.modules.get(key)
            sys.modules[key] = val  # type: ignore[assignment]
        try:
            await _run_crm_sync(mock_task, EMAIL_ID)
        finally:
            for key, original in originals.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

        assert EmailState.CRM_SYNC_FAILED in transitions
        mock_task.retry.assert_not_called()
