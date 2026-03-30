"""Tests for security-related config fields — WARNING-02.

Validates:
- draft_org_system_prompt max_length=4096 constraint.
- Settings construction succeeds at and below the limit.
- Settings construction raises ValidationError when the limit is exceeded.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: str) -> Settings:
    """Build a minimal Settings without reading .env.

    Uses snake_case field names (not UPPER_CASE env var names) because
    pydantic-settings constructor expects the field alias, not the env key.
    """
    base: dict[str, str] = {
        "database_url": "postgresql+asyncpg://u:p@host/db",
        "database_url_sync": "postgresql+psycopg2://u:p@host/db",
        "jwt_secret_key": "test-secret",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TestDraftOrgSystemPromptConstraint
# ---------------------------------------------------------------------------


class TestDraftOrgSystemPromptConstraint:
    """draft_org_system_prompt has max_length=4096 (WARNING-02 fix)."""

    def test_empty_prompt_is_valid(self) -> None:
        settings = _make_settings(draft_org_system_prompt="")
        assert settings.draft_org_system_prompt == ""

    def test_prompt_below_limit_is_valid(self) -> None:
        prompt = "A" * 2000
        settings = _make_settings(draft_org_system_prompt=prompt)
        assert len(settings.draft_org_system_prompt) == 2000

    def test_prompt_at_exact_limit_is_valid(self) -> None:
        """Exactly 4096 characters must pass validation."""
        prompt = "X" * 4096
        settings = _make_settings(draft_org_system_prompt=prompt)
        assert len(settings.draft_org_system_prompt) == 4096

    def test_prompt_exceeds_limit_raises_validation_error(self) -> None:
        """4097 characters must raise ValidationError."""
        prompt = "X" * 4097
        with pytest.raises(ValidationError):
            _make_settings(draft_org_system_prompt=prompt)

    def test_prompt_far_above_limit_raises_validation_error(self) -> None:
        """Prompt injections padded to 10K chars must also fail validation."""
        prompt = "A" * 10_000
        with pytest.raises(ValidationError):
            _make_settings(draft_org_system_prompt=prompt)
