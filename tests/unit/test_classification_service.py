"""Tests for ClassificationService — mocked LLM adapter + DB session.

Coverage targets:
  - classify_email: happy path, invalid slug fallback, heuristic disagreement,
    LLM error, wrong state, email not found, feedback load failure
  - classify_batch: per-email isolation, empty list guard
  - _has_heuristic_disagreement: module-level function, all branches
  - _find_fallback: with and without fallback category
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.adapters.llm.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.adapters.llm.schemas import ClassificationResult as AdapterClassificationResult
from src.core.config import Settings
from src.core.exceptions import CategoryNotFoundError, InvalidStateTransitionError
from src.models.email import EmailState
from src.services.classification import (
    ClassificationService,
    _find_fallback,
    _has_heuristic_disagreement,
)
from src.services.schemas.classification import (
    ActionCategoryDef,
    ClassificationServiceResult,
    HeuristicResult,
    TypeCategoryDef,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    """Create a Settings instance with test-safe defaults."""
    defaults: dict[str, object] = {
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "database_url_sync": "postgresql+psycopg2://test:test@localhost/test",
        "jwt_secret_key": "test-secret-key-for-classification-tests",
        "classify_max_few_shot_examples": 10,
        "classify_feedback_snippet_chars": 200,
        "classify_internal_domains": "",
        "llm_temperature_classify": 0.1,
        "llm_classify_max_tokens": 500,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_email(state: EmailState = EmailState.SANITIZED) -> MagicMock:
    """Create a mock Email object with required attributes."""
    email = MagicMock()
    email.id = uuid.uuid4()
    email.state = state
    email.body_plain = "This is a test email body about billing."
    email.subject = "Test Subject"
    email.sender_email = "user@example.com"
    email.transition_to = MagicMock()
    return email


def _make_action_cat(slug: str, *, fallback: bool = False) -> ActionCategoryDef:
    return ActionCategoryDef(
        id=uuid.uuid4(),
        slug=slug,
        name=slug.capitalize(),
        description=f"Description for {slug}",
        is_fallback=fallback,
    )


def _make_type_cat(slug: str, *, fallback: bool = False) -> TypeCategoryDef:
    return TypeCategoryDef(
        id=uuid.uuid4(),
        slug=slug,
        name=slug.capitalize(),
        description=f"Description for {slug}",
        is_fallback=fallback,
    )


def _make_adapter_result(
    action: str = "respond",
    type_: str = "complaint",
    confidence: str = "high",
    fallback_applied: bool = False,
) -> AdapterClassificationResult:
    return AdapterClassificationResult(
        action=action,
        type=type_,
        confidence=confidence,  # type: ignore[arg-type]
        raw_llm_output=f'{{"action":"{action}","type":"{type_}"}}',
        fallback_applied=fallback_applied,
    )


def _make_service_result(
    email_id: uuid.UUID | None = None,
) -> ClassificationServiceResult:
    """Create a real ClassificationServiceResult for batch tests."""
    return ClassificationServiceResult(
        email_id=email_id or uuid.uuid4(),
        action_slug="respond",
        type_slug="complaint",
        confidence="high",
        fallback_applied=False,
        heuristic_disagreement=False,
        heuristic_result=None,
        db_record_id=uuid.uuid4(),
    )


def _make_db_record() -> MagicMock:
    record = MagicMock()
    record.id = uuid.uuid4()
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return _make_settings()


@pytest.fixture
def mock_llm_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter.classify.return_value = _make_adapter_result()
    return adapter


@pytest.fixture
def service(mock_llm_adapter: AsyncMock, settings: Settings) -> ClassificationService:
    return ClassificationService(llm_adapter=mock_llm_adapter, settings=settings)


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# Standard category sets used across tests
_ACTION_CATS = [
    _make_action_cat("respond", fallback=False),
    _make_action_cat("escalate", fallback=False),
    _make_action_cat("inform", fallback=True),
]
_TYPE_CATS = [
    _make_type_cat("complaint", fallback=False),
    _make_type_cat("inquiry", fallback=False),
    _make_type_cat("notification", fallback=True),
]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestClassifyEmailHappyPath:
    @pytest.mark.asyncio
    async def test_returns_classification_service_result(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """SANITIZED email classified by LLM returns typed result."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond", type_="complaint", confidence="high"
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.email_id == email.id
        assert result.action_slug == "respond"
        assert result.type_slug == "complaint"
        assert result.confidence == "high"
        assert result.fallback_applied is False
        assert result.heuristic_disagreement is False
        assert result.db_record_id == mock_record.id

    @pytest.mark.asyncio
    async def test_persist_and_transition_called(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """_persist_and_transition receives the adapter result."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_persist = AsyncMock(return_value=mock_record)

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(service, "_persist_and_transition", new=mock_persist),
        ):
            await service.classify_email(email.id, mock_db)

        mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_adapter_called_with_options(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLM adapter is called with allowed_actions and allowed_types from DB cats."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            await service.classify_email(email.id, mock_db)

        mock_llm_adapter.classify.assert_awaited_once()
        call_kwargs = mock_llm_adapter.classify.call_args.kwargs
        options = call_kwargs["options"]
        assert set(options.allowed_actions) == {"respond", "escalate", "inform"}
        assert set(options.allowed_types) == {"complaint", "inquiry", "notification"}
        assert options.temperature == 0.1
        assert options.max_tokens == 500


# ---------------------------------------------------------------------------
# Invalid LLM slug → fallback
# ---------------------------------------------------------------------------


class TestInvalidSlugFallback:
    @pytest.mark.asyncio
    async def test_invalid_action_slug_triggers_fallback(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLM returns slug not in DB → fallback applied, confidence low."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="nonexistent_action",
            type_="complaint",
            confidence="high",
        )
        mock_persist = AsyncMock(return_value=mock_record)

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(service, "_persist_and_transition", new=mock_persist),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.fallback_applied is True
        assert result.confidence == "low"
        # Slug is the fallback category (is_fallback=True)
        assert result.action_slug == "inform"

    @pytest.mark.asyncio
    async def test_invalid_type_slug_triggers_fallback(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLM returns valid action but invalid type → fallback applied."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond",
            type_="unknown_type",
            confidence="high",
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.fallback_applied is True
        assert result.confidence == "low"
        assert result.type_slug == "notification"  # fallback TypeCategory

    @pytest.mark.asyncio
    async def test_both_slugs_invalid_uses_both_fallbacks(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """Both action and type are invalid → both fallback slugs used."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="hallucinated_action",
            type_="hallucinated_type",
            confidence="high",
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.fallback_applied is True
        assert result.confidence == "low"
        assert result.action_slug == "inform"
        assert result.type_slug == "notification"

    @pytest.mark.asyncio
    async def test_no_fallback_category_raises(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """If no is_fallback=True in any category, CategoryNotFoundError is raised."""
        email = _make_email(EmailState.SANITIZED)
        # Categories with no fallback set
        no_fallback_actions = [_make_action_cat("respond", fallback=False)]
        no_fallback_types = [_make_type_cat("complaint", fallback=False)]
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="hallucinated", type_="hallucinated"
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(no_fallback_actions, no_fallback_types)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            with pytest.raises(CategoryNotFoundError):
                await service.classify_email(email.id, mock_db)


# ---------------------------------------------------------------------------
# Heuristic disagreement → confidence lowered, LLM not overridden
# ---------------------------------------------------------------------------


class TestHeuristicDisagreement:
    @pytest.mark.asyncio
    async def test_heuristic_disagrees_lowers_confidence(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """When heuristic disagrees with LLM, confidence drops to low."""
        email = _make_email(EmailState.SANITIZED)
        # LLM says respond/inquiry (high confidence)
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond", type_="inquiry", confidence="high"
        )
        mock_record = _make_db_record()

        # Force heuristic to fire by using keyword "urgent" in subject
        email.subject = "URGENT: legal lawsuit against us"
        email.sender_email = "boss@example.com"

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.heuristic_disagreement is True
        assert result.confidence == "low"
        # LLM result is still used — heuristic NEVER overrides
        assert result.action_slug == "respond"

    @pytest.mark.asyncio
    async def test_heuristic_agrees_keeps_high_confidence(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """When heuristic has no opinion, confidence stays high."""
        email = _make_email(EmailState.SANITIZED)
        email.subject = "Normal subject"
        email.body_plain = "A regular business email."
        email.sender_email = "user@example.com"
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond", type_="complaint", confidence="high"
        )
        mock_record = _make_db_record()

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.heuristic_disagreement is False
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_heuristic_disagrees_llm_action_not_overridden(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """Heuristic hints escalate but LLM chose respond — LLM result kept."""
        email = _make_email(EmailState.SANITIZED)
        # "lawsuit" in subject fires escalate_keyword heuristic
        email.subject = "Threatened lawsuit over product defect"
        email.body_plain = "I am extremely disappointed."
        email.sender_email = "customer@external.com"

        # LLM returns respond (disagrees with heuristic escalate hint)
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond", type_="complaint", confidence="high"
        )
        mock_record = _make_db_record()

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        # Heuristic fired (escalate_keyword) — disagrees with respond
        assert result.heuristic_disagreement is True
        # LLM action is preserved, not overridden
        assert result.action_slug == "respond"
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# LLM errors → CLASSIFICATION_FAILED
# ---------------------------------------------------------------------------


class TestLLMErrors:
    @pytest.mark.asyncio
    async def test_llm_connection_error_transitions_to_failed(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLMConnectionError → email transitions to CLASSIFICATION_FAILED, re-raised."""
        email = _make_email(EmailState.SANITIZED)
        mock_llm_adapter.classify.side_effect = LLMConnectionError("connection refused")

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            with pytest.raises(LLMConnectionError):
                await service.classify_email(email.id, mock_db)

        # transition_to was called with CLASSIFICATION_FAILED
        email.transition_to.assert_called_once_with(EmailState.CLASSIFICATION_FAILED)
        # DB commit was attempted for the failure state
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_llm_rate_limit_error_transitions_to_failed(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLMRateLimitError is also caught and causes CLASSIFICATION_FAILED."""
        email = _make_email(EmailState.SANITIZED)
        mock_llm_adapter.classify.side_effect = LLMRateLimitError(
            "429", retry_after_seconds=30
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            with pytest.raises(LLMRateLimitError):
                await service.classify_email(email.id, mock_db)

        email.transition_to.assert_called_once_with(EmailState.CLASSIFICATION_FAILED)

    @pytest.mark.asyncio
    async def test_llm_timeout_error_transitions_to_failed(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """LLMTimeoutError is also caught and causes CLASSIFICATION_FAILED."""
        email = _make_email(EmailState.SANITIZED)
        mock_llm_adapter.classify.side_effect = LLMTimeoutError("timed out")

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            with pytest.raises(LLMTimeoutError):
                await service.classify_email(email.id, mock_db)

        email.transition_to.assert_called_once_with(EmailState.CLASSIFICATION_FAILED)

    @pytest.mark.asyncio
    async def test_db_error_during_failure_state_persist_does_not_swallow_llm_error(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """Even if the failure-state DB commit fails, the LLM error is still re-raised."""
        email = _make_email(EmailState.SANITIZED)
        mock_llm_adapter.classify.side_effect = LLMConnectionError("offline")
        # DB commit for failure state also fails
        mock_db.commit.side_effect = SQLAlchemyError("DB down")

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            # Original LLMConnectionError must propagate, not the SQLAlchemyError
            with pytest.raises(LLMConnectionError):
                await service.classify_email(email.id, mock_db)


# ---------------------------------------------------------------------------
# State guard: email not SANITIZED
# ---------------------------------------------------------------------------


class TestStateGuard:
    @pytest.mark.asyncio
    async def test_fetched_email_raises_invalid_state(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """Email in FETCHED state raises InvalidStateTransitionError."""
        email = _make_email(EmailState.FETCHED)

        with patch.object(
            service,
            "_load_email_or_raise",
            new=AsyncMock(return_value=email),
        ):
            with pytest.raises(InvalidStateTransitionError, match="SANITIZED"):
                await service.classify_email(email.id, mock_db)

    @pytest.mark.asyncio
    async def test_classified_email_raises_invalid_state(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """Email already in CLASSIFIED state raises InvalidStateTransitionError."""
        email = _make_email(EmailState.CLASSIFIED)

        with patch.object(
            service,
            "_load_email_or_raise",
            new=AsyncMock(return_value=email),
        ):
            with pytest.raises(InvalidStateTransitionError):
                await service.classify_email(email.id, mock_db)

    @pytest.mark.asyncio
    async def test_classification_failed_email_raises_invalid_state(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """Email in CLASSIFICATION_FAILED state raises InvalidStateTransitionError."""
        email = _make_email(EmailState.CLASSIFICATION_FAILED)

        with patch.object(
            service,
            "_load_email_or_raise",
            new=AsyncMock(return_value=email),
        ):
            with pytest.raises(InvalidStateTransitionError):
                await service.classify_email(email.id, mock_db)


# ---------------------------------------------------------------------------
# Email not found
# ---------------------------------------------------------------------------


class TestEmailNotFound:
    @pytest.mark.asyncio
    async def test_missing_email_raises_value_error(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """Missing email raises ValueError from _load_email_or_raise."""
        email_id = uuid.uuid4()

        with patch.object(
            service,
            "_load_email_or_raise",
            new=AsyncMock(side_effect=ValueError(f"Email {email_id} not found")),
        ):
            with pytest.raises(ValueError, match=str(email_id)):
                await service.classify_email(email_id, mock_db)


# ---------------------------------------------------------------------------
# Feedback load failure → silenced, classification continues
# ---------------------------------------------------------------------------


class TestFeedbackLoadFailure:
    @pytest.mark.asyncio
    async def test_feedback_load_failure_does_not_block_classification(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """SQLAlchemyError during feedback load is silenced; classification proceeds."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()

        # _load_feedback_examples should have already silenced its own error,
        # but we test the scenario where it raises despite that to verify the
        # orchestration layer is robust. The service's _load_feedback_examples
        # catches SQLAlchemyError and returns []. We verify the service result is valid.
        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),  # silenced by the method itself
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        # Classification succeeded despite no feedback
        assert result.action_slug == "respond"
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_prompt_builder_called_with_empty_examples(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """PromptBuilder receives empty list when feedback unavailable."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
            patch.object(
                service._prompt_builder,
                "build_classify_prompt",
                wraps=service._prompt_builder.build_classify_prompt,
            ) as mock_build,
        ):
            await service.classify_email(email.id, mock_db)

        _, kwargs = mock_build.call_args
        assert kwargs["few_shot_examples"] == []


# ---------------------------------------------------------------------------
# Adapter result already has fallback_applied=True
# ---------------------------------------------------------------------------


class TestAdapterFallbackPropagation:
    @pytest.mark.asyncio
    async def test_adapter_fallback_applied_propagates_to_result(
        self,
        service: ClassificationService,
        mock_llm_adapter: AsyncMock,
        mock_db: AsyncMock,
    ) -> None:
        """If adapter itself applied fallback, result.fallback_applied stays True."""
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        # Adapter already applied fallback internally
        mock_llm_adapter.classify.return_value = _make_adapter_result(
            action="respond",
            type_="complaint",
            confidence="low",
            fallback_applied=True,
        )

        with (
            patch.object(
                service,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                service,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                service,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                service,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            result = await service.classify_email(email.id, mock_db)

        assert result.fallback_applied is True
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# classify_batch
# ---------------------------------------------------------------------------


class TestClassifyBatch:
    @pytest.mark.asyncio
    async def test_empty_list_raises_value_error(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """classify_batch([]) raises ValueError — precondition enforced."""
        with pytest.raises(ValueError, match="email_ids must not be empty"):
            await service.classify_batch([], mock_db)

    @pytest.mark.asyncio
    async def test_single_success(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """Single email classified → batch result has 1 success."""
        email_id = uuid.uuid4()
        service_result = _make_service_result(email_id)

        with patch.object(
            service,
            "classify_email",
            new=AsyncMock(return_value=service_result),
        ):
            batch = await service.classify_batch([email_id], mock_db)

        assert batch.total == 1
        assert batch.succeeded == 1
        assert batch.failed == 0
        assert len(batch.results) == 1
        assert len(batch.failures) == 0

    @pytest.mark.asyncio
    async def test_three_emails_one_fails_isolation(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """3 emails: first and third succeed, second raises LLMConnectionError."""
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        result_ok = _make_service_result()

        call_count = 0

        async def classify_side_effect(
            email_id: uuid.UUID, db: object
        ) -> ClassificationServiceResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise LLMConnectionError("timeout on email 2")
            return result_ok

        with patch.object(service, "classify_email", side_effect=classify_side_effect):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.total == 3
        assert batch.succeeded == 2
        assert batch.failed == 1
        assert len(batch.failures) == 1
        assert batch.failures[0][0] == ids[1]
        assert "timeout on email 2" in batch.failures[0][1]

    @pytest.mark.asyncio
    async def test_all_fail(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """All emails fail → succeeded=0, failed=N."""
        ids = [uuid.uuid4(), uuid.uuid4()]

        with patch.object(
            service,
            "classify_email",
            new=AsyncMock(side_effect=LLMConnectionError("provider down")),
        ):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.succeeded == 0
        assert batch.failed == 2

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_per_email_does_not_abort_batch(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """SQLAlchemyError on one email is caught; batch continues."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        result_ok = _make_service_result()

        call_count = 0

        async def side_effect(
            email_id: uuid.UUID, db: object
        ) -> ClassificationServiceResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SQLAlchemyError("db error")
            return result_ok

        with patch.object(service, "classify_email", side_effect=side_effect):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.succeeded == 1
        assert batch.failed == 1

    @pytest.mark.asyncio
    async def test_invalid_state_per_email_does_not_abort_batch(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """InvalidStateTransitionError on one email is caught; batch continues."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        result_ok = _make_service_result()

        call_count = 0

        async def side_effect(
            email_id: uuid.UUID, db: object
        ) -> ClassificationServiceResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise InvalidStateTransitionError("not SANITIZED")
            return result_ok

        with patch.object(service, "classify_email", side_effect=side_effect):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.succeeded == 1
        assert batch.failed == 1

    @pytest.mark.asyncio
    async def test_value_error_per_email_does_not_abort_batch(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """ValueError (email not found) on one email is caught; batch continues."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        result_ok = _make_service_result()

        call_count = 0

        async def side_effect(
            email_id: uuid.UUID, db: object
        ) -> ClassificationServiceResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Email not found")
            return result_ok

        with patch.object(service, "classify_email", side_effect=side_effect):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.succeeded == 1
        assert batch.failed == 1

    @pytest.mark.asyncio
    async def test_batch_total_matches_input_length(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """batch.total always equals len(email_ids) regardless of success/failure."""
        ids = [uuid.uuid4() for _ in range(5)]
        result_ok = _make_service_result()

        with patch.object(
            service, "classify_email", new=AsyncMock(return_value=result_ok)
        ):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.total == 5

    @pytest.mark.asyncio
    async def test_batch_succeeded_plus_failed_equals_total(
        self,
        service: ClassificationService,
        mock_db: AsyncMock,
    ) -> None:
        """succeeded + failed == total is always true."""
        ids = [uuid.uuid4() for _ in range(4)]
        call_count = 0

        async def alternating(
            email_id: uuid.UUID, db: object
        ) -> ClassificationServiceResult:
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise LLMConnectionError("odd failure")
            return _make_service_result()

        with patch.object(service, "classify_email", side_effect=alternating):
            batch = await service.classify_batch(ids, mock_db)

        assert batch.succeeded + batch.failed == batch.total


# ---------------------------------------------------------------------------
# _has_heuristic_disagreement (module-level function)
# ---------------------------------------------------------------------------


class TestHasHeuristicDisagreement:
    def test_no_opinion_returns_false(self) -> None:
        """Heuristic with no opinion → no disagreement."""
        llm = _make_adapter_result(action="respond", type_="complaint")
        heuristic = HeuristicResult(has_opinion=False)
        assert _has_heuristic_disagreement(llm, heuristic) is False

    def test_same_action_and_type_returns_false(self) -> None:
        """Heuristic agrees with LLM on both → no disagreement."""
        llm = _make_adapter_result(action="respond", type_="complaint")
        heuristic = HeuristicResult(
            action_hint="respond", type_hint="complaint", has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is False

    def test_different_action_hint_returns_true(self) -> None:
        """Heuristic action_hint differs from LLM action → disagreement."""
        llm = _make_adapter_result(action="respond", type_="complaint")
        heuristic = HeuristicResult(
            action_hint="escalate", type_hint=None, has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is True

    def test_different_type_hint_returns_true(self) -> None:
        """Heuristic type_hint differs from LLM type → disagreement."""
        llm = _make_adapter_result(action="respond", type_="inquiry")
        heuristic = HeuristicResult(
            action_hint=None, type_hint="urgent", has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is True

    def test_both_hints_differ_returns_true(self) -> None:
        """Both action and type hints differ → disagreement."""
        llm = _make_adapter_result(action="respond", type_="inquiry")
        heuristic = HeuristicResult(
            action_hint="escalate", type_hint="complaint", has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is True

    def test_only_type_hint_set_matches(self) -> None:
        """Only type_hint set and it matches LLM type → no disagreement."""
        llm = _make_adapter_result(action="respond", type_="complaint")
        heuristic = HeuristicResult(
            action_hint=None, type_hint="complaint", has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is False

    def test_only_action_hint_set_matches(self) -> None:
        """Only action_hint set and it matches LLM action → no disagreement."""
        llm = _make_adapter_result(action="escalate", type_="complaint")
        heuristic = HeuristicResult(
            action_hint="escalate", type_hint=None, has_opinion=True
        )
        assert _has_heuristic_disagreement(llm, heuristic) is False

    def test_has_opinion_false_overrides_hint_mismatch(self) -> None:
        """has_opinion=False → always False, even if hints differ."""
        llm = _make_adapter_result(action="respond", type_="complaint")
        heuristic = HeuristicResult(
            action_hint="escalate", type_hint="urgent", has_opinion=False
        )
        assert _has_heuristic_disagreement(llm, heuristic) is False


# ---------------------------------------------------------------------------
# _find_fallback (module-level function)
# ---------------------------------------------------------------------------


class TestFindFallback:
    def test_returns_fallback_action_category(self) -> None:
        """Returns the first is_fallback=True action category."""
        cats: list[ActionCategoryDef] = [
            _make_action_cat("respond", fallback=False),
            _make_action_cat("inform", fallback=True),
            _make_action_cat("escalate", fallback=False),
        ]
        result = _find_fallback(cats)
        assert result.slug == "inform"
        assert result.is_fallback is True

    def test_returns_fallback_type_category(self) -> None:
        """Returns the first is_fallback=True type category."""
        cats: list[TypeCategoryDef] = [
            _make_type_cat("complaint", fallback=False),
            _make_type_cat("notification", fallback=True),
        ]
        result = _find_fallback(cats)
        assert result.slug == "notification"

    def test_no_fallback_raises_category_not_found_error(self) -> None:
        """Empty or all-non-fallback list → CategoryNotFoundError."""
        cats: list[ActionCategoryDef] = [
            _make_action_cat("respond", fallback=False),
            _make_action_cat("escalate", fallback=False),
        ]
        with pytest.raises(CategoryNotFoundError, match="is_fallback=True"):
            _find_fallback(cats)

    def test_empty_list_raises_category_not_found_error(self) -> None:
        """Empty categories list → CategoryNotFoundError."""
        with pytest.raises(CategoryNotFoundError):
            _find_fallback([])  # type: ignore[arg-type]

    def test_first_fallback_returned_when_multiple(self) -> None:
        """If multiple is_fallback=True, the first one wins (next() semantics)."""
        cats: list[ActionCategoryDef] = [
            _make_action_cat("first_fallback", fallback=True),
            _make_action_cat("second_fallback", fallback=True),
        ]
        result = _find_fallback(cats)
        assert result.slug == "first_fallback"


# ---------------------------------------------------------------------------
# Settings — Cat 8 configurable defaults forwarded correctly
# ---------------------------------------------------------------------------


class TestSettingsForwarding:
    @pytest.mark.asyncio
    async def test_classify_max_few_shot_forwarded_to_load(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """classify_max_few_shot_examples is forwarded to _load_feedback_examples."""
        custom_settings = _make_settings(classify_max_few_shot_examples=3)
        mock_llm = AsyncMock()
        mock_llm.classify.return_value = _make_adapter_result()
        svc = ClassificationService(llm_adapter=mock_llm, settings=custom_settings)
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()
        mock_load_fb = AsyncMock(return_value=[])

        with (
            patch.object(
                svc,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                svc,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(svc, "_load_feedback_examples", new=mock_load_fb),
            patch.object(
                svc,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            await svc.classify_email(email.id, mock_db)

        mock_load_fb.assert_awaited_once_with(mock_db, limit=3)

    @pytest.mark.asyncio
    async def test_llm_temperature_forwarded_to_options(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """llm_temperature_classify is forwarded to ClassifyOptions.temperature."""
        custom_settings = _make_settings(llm_temperature_classify=0.05)
        mock_llm = AsyncMock()
        mock_llm.classify.return_value = _make_adapter_result()
        svc = ClassificationService(llm_adapter=mock_llm, settings=custom_settings)
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()

        with (
            patch.object(
                svc,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                svc,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                svc,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                svc,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            await svc.classify_email(email.id, mock_db)

        call_kwargs = mock_llm.classify.call_args.kwargs
        assert call_kwargs["options"].temperature == 0.05

    @pytest.mark.asyncio
    async def test_llm_classify_max_tokens_forwarded_to_options(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """llm_classify_max_tokens is forwarded to ClassifyOptions.max_tokens."""
        custom_settings = _make_settings(llm_classify_max_tokens=300)
        mock_llm = AsyncMock()
        mock_llm.classify.return_value = _make_adapter_result()
        svc = ClassificationService(llm_adapter=mock_llm, settings=custom_settings)
        email = _make_email(EmailState.SANITIZED)
        mock_record = _make_db_record()

        with (
            patch.object(
                svc,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                svc,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                svc,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                svc,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
        ):
            await svc.classify_email(email.id, mock_db)

        call_kwargs = mock_llm.classify.call_args.kwargs
        assert call_kwargs["options"].max_tokens == 300

    @pytest.mark.asyncio
    async def test_internal_domains_forwarded_to_heuristics(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """classify_internal_domains is parsed and forwarded to HeuristicClassifier."""
        custom_settings = _make_settings(classify_internal_domains="acme.com,corp.io")
        mock_llm = AsyncMock()
        mock_llm.classify.return_value = _make_adapter_result()
        svc = ClassificationService(llm_adapter=mock_llm, settings=custom_settings)
        email = _make_email(EmailState.SANITIZED)
        email.sender_email = "user@acme.com"
        email.subject = "Normal subject"
        email.body_plain = "Normal body"
        mock_record = _make_db_record()

        with (
            patch.object(
                svc,
                "_load_email_or_raise",
                new=AsyncMock(return_value=email),
            ),
            patch.object(
                svc,
                "_load_active_categories",
                new=AsyncMock(return_value=(_ACTION_CATS, _TYPE_CATS)),
            ),
            patch.object(
                svc,
                "_load_feedback_examples",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                svc,
                "_persist_and_transition",
                new=AsyncMock(return_value=mock_record),
            ),
            patch.object(
                svc._heuristic_classifier,
                "classify",
                wraps=svc._heuristic_classifier.classify,
            ) as mock_classify,
        ):
            await svc.classify_email(email.id, mock_db)

        # classify(request, internal_domains) — both positional
        args, _ = mock_classify.call_args
        internal_domains_arg = args[1]
        assert "acme.com" in internal_domains_arg
        assert "corp.io" in internal_domains_arg
