"""Classification service — orchestrates LLM classification with heuristics.

Loads categories from DB, builds prompts with 5-layer defense, calls LLM adapter,
validates output against DB slugs, runs heuristic second-opinion, and persists
the result with email state transition.

Invariants: Email must be in SANITIZED state to classify.
  Categories loaded from DB on each call (never cached indefinitely).
Guarantees: classify_email transitions email to CLASSIFIED or CLASSIFICATION_FAILED.
  classify_batch provides per-email isolation — one failure does not block others.
Errors raised: LLMAdapterError subclasses (re-raised after state transition),
  ValueError (email not found), InvalidStateTransitionError (wrong state),
  CategoryNotFoundError (no fallback category).
Errors silenced: Feedback loading failure (continues without few-shot).
External state: PostgreSQL (categories, feedback, results), LLM provider (via adapter).

External-state ops (DB, LLM): structured try/except with specific types.
Local computation (prompt build, heuristics, validation): conditionals, no try/except.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.exceptions import LLMAdapterError
from src.adapters.llm.schemas import ClassificationResult as AdapterClassificationResult
from src.adapters.llm.schemas import ClassifyOptions
from src.core.config import Settings
from src.core.exceptions import CategoryNotFoundError, InvalidStateTransitionError
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import (
    ClassificationConfidence,
    ClassificationResult,
)
from src.models.email import Email, EmailState
from src.models.feedback import ClassificationFeedback
from src.services.heuristics import HeuristicClassifier
from src.services.prompt_builder import PromptBuilder
from src.services.schemas.classification import (
    ActionCategoryDef,
    ClassificationBatchResult,
    ClassificationRequest,
    ClassificationServiceResult,
    FeedbackExample,
    HeuristicResult,
    TypeCategoryDef,
)

logger = structlog.get_logger(__name__)


class ClassificationService:
    """Orchestrates email classification: categories → prompt → LLM → validate → persist.

    Invariants:
      - ``llm_adapter`` must be a connected LLM adapter.
      - ``settings`` provides all configurable defaults.

    Guarantees:
      - ``classify_email`` transitions email to CLASSIFIED or CLASSIFICATION_FAILED.
      - ``classify_batch`` provides per-email isolation.
      - Categories loaded fresh from DB each call (never cached).

    Errors raised:
      - ValueError: email not found in DB.
      - InvalidStateTransitionError: email not in SANITIZED state.
      - LLMAdapterError subclasses: re-raised after state transition to CLASSIFICATION_FAILED.
      - CategoryNotFoundError: no fallback category in DB.
      - SQLAlchemyError: DB failures during category load or result persistence.

    Errors silenced:
      - Feedback loading failure: continues without few-shot examples.
    """

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        settings: Settings,
    ) -> None:
        self._llm_adapter = llm_adapter
        self._settings = settings
        self._prompt_builder = PromptBuilder()
        self._heuristic_classifier = HeuristicClassifier()

    async def classify_email(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> ClassificationServiceResult:
        """Classify a single email.

        Preconditions:
          - email with email_id exists in DB with state=SANITIZED.
          - email.body_plain is not None (the sanitization step enforces this).
          - At least one active ActionCategory and TypeCategory exist.

        Guarantees:
          - Returns ClassificationServiceResult on success.
          - Email transitions to CLASSIFIED on success, CLASSIFICATION_FAILED on LLM error.
          - DB record created for the classification result.

        Errors raised:
          - ValueError: email not found.
          - InvalidStateTransitionError: email not SANITIZED.
          - LLMAdapterError: LLM call failure (after CLASSIFICATION_FAILED transition).
          - CategoryNotFoundError: no fallback category.
          - SQLAlchemyError: DB failure.

        Errors silenced:
          - Feedback loading: continues without few-shot on failure.
        """
        # Load email
        email = await self._load_email_or_raise(email_id, db)

        # State check
        if email.state != EmailState.SANITIZED:
            raise InvalidStateTransitionError(
                f"Email {email_id} must be SANITIZED to classify, got {email.state}"
            )

        # Build classification request
        sender_domain = email.sender_email.split("@")[-1]
        request = ClassificationRequest(
            email_id=email_id,
            sanitized_body=email.body_plain or "",
            subject=email.subject,
            sender_email=email.sender_email,
            sender_domain=sender_domain,
        )

        # Load categories
        action_cats, type_cats = await self._load_active_categories(db)

        # Load feedback examples (silenced on failure)
        few_shot_examples = await self._load_feedback_examples(
            db, limit=self._settings.classify_max_few_shot_examples
        )

        # Build prompt
        system_prompt, user_prompt = self._prompt_builder.build_classify_prompt(
            email_content=request.sanitized_body,
            action_categories=action_cats,
            type_categories=type_cats,
            few_shot_examples=few_shot_examples,
            max_examples=self._settings.classify_max_few_shot_examples,
        )

        # Run heuristics
        internal_domains = _parse_internal_domains(self._settings.classify_internal_domains)
        heuristic_result = self._heuristic_classifier.classify(request, internal_domains)

        # Call LLM adapter
        options = ClassifyOptions(
            allowed_actions=[c.slug for c in action_cats],
            allowed_types=[c.slug for c in type_cats],
            temperature=self._settings.llm_temperature_classify,
            max_tokens=self._settings.llm_classify_max_tokens,
        )
        adapter_result = await self._call_llm_or_fail(
            email, db, user_prompt, system_prompt, options
        )

        # Validate slugs against DB categories
        valid_actions = {c.slug for c in action_cats}
        valid_types = {c.slug for c in type_cats}
        fallback_applied = False

        if adapter_result.action not in valid_actions or adapter_result.type not in valid_types:
            fallback_action = _find_fallback(action_cats)
            fallback_type = _find_fallback(type_cats)
            adapter_result = AdapterClassificationResult(
                action=fallback_action.slug,
                type=fallback_type.slug,
                confidence="low",
                raw_llm_output=adapter_result.raw_llm_output,
                fallback_applied=True,
            )
            fallback_applied = True

        # Determine final confidence
        heuristic_disagrees = _has_heuristic_disagreement(adapter_result, heuristic_result)
        final_confidence: Literal["high", "low"] = (
            "low"
            if adapter_result.confidence == "low"
            or fallback_applied
            or adapter_result.fallback_applied
            or heuristic_disagrees
            else "high"
        )

        if heuristic_disagrees:
            logger.info(
                "classification_heuristic_disagreement",
                email_id=str(email_id),
                llm_action=adapter_result.action,
                llm_type=adapter_result.type,
                heuristic_action_hint=heuristic_result.action_hint,
                heuristic_type_hint=heuristic_result.type_hint,
            )

        # Persist result and transition
        db_record = await self._persist_and_transition(
            db=db,
            email=email,
            adapter_result=adapter_result,
            action_cats=action_cats,
            type_cats=type_cats,
            final_confidence=final_confidence,
        )

        logger.info(
            "classification_complete",
            email_id=str(email_id),
            action=adapter_result.action,
            type=adapter_result.type,
            confidence=final_confidence,
            fallback=fallback_applied or adapter_result.fallback_applied,
        )

        return ClassificationServiceResult(
            email_id=email_id,
            action_slug=adapter_result.action,
            type_slug=adapter_result.type,
            confidence=final_confidence,
            fallback_applied=fallback_applied or adapter_result.fallback_applied,
            heuristic_disagreement=heuristic_disagrees,
            heuristic_result=heuristic_result,
            db_record_id=db_record.id,
        )

    async def classify_batch(
        self,
        email_ids: list[uuid.UUID],
        db: AsyncSession,
    ) -> ClassificationBatchResult:
        """Classify a batch of emails with per-email isolation.

        Preconditions:
          - email_ids is non-empty.

        Guarantees:
          - Per-email isolation: failure of email N does not block N+1.
          - Returns aggregate result with succeeded/failed counts.

        Errors raised:
          - ValueError: email_ids is empty.

        Errors silenced:
          - Per-email LLMAdapterError / SQLAlchemyError: recorded as failure.
        """
        if not email_ids:
            raise ValueError("email_ids must not be empty")

        results: list[ClassificationServiceResult] = []
        failures: list[tuple[uuid.UUID, str]] = []

        for eid in email_ids:
            try:
                result = await self.classify_email(eid, db)
                results.append(result)
            except (
                LLMAdapterError,
                SQLAlchemyError,
                ValueError,
                InvalidStateTransitionError,
            ) as exc:
                logger.error(
                    "classification_batch_item_failed",
                    email_id=str(eid),
                    error=str(exc),
                )
                failures.append((eid, str(exc)))

        return ClassificationBatchResult(
            total=len(email_ids),
            succeeded=len(results),
            failed=len(failures),
            results=results,
            failures=failures,
        )

    async def _load_email_or_raise(
        self,
        email_id: uuid.UUID,
        db: AsyncSession,
    ) -> Email:
        """Load email from DB or raise ValueError."""
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        if email is None:
            raise ValueError(f"Email {email_id} not found")
        return email

    async def _load_active_categories(
        self,
        db: AsyncSession,
    ) -> tuple[list[ActionCategoryDef], list[TypeCategoryDef]]:
        """Load active categories from DB, converted to frozen dataclasses.

        Raises SQLAlchemyError on DB failure (not silenced).
        """
        action_result = await db.execute(
            select(ActionCategory)
            .where(ActionCategory.is_active.is_(True))
            .order_by(ActionCategory.display_order)
        )
        action_cats = [
            ActionCategoryDef(
                id=c.id,
                slug=c.slug,
                name=c.name,
                description=c.description,
                is_fallback=c.is_fallback,
            )
            for c in action_result.scalars().all()
        ]

        type_result = await db.execute(
            select(TypeCategory)
            .where(TypeCategory.is_active.is_(True))
            .order_by(TypeCategory.display_order)
        )
        type_cats = [
            TypeCategoryDef(
                id=c.id,
                slug=c.slug,
                name=c.name,
                description=c.description,
                is_fallback=c.is_fallback,
            )
            for c in type_result.scalars().all()
        ]

        if not action_cats:
            raise ValueError("No active action categories found")
        if not type_cats:
            raise ValueError("No active type categories found")

        return action_cats, type_cats

    async def _load_feedback_examples(
        self,
        db: AsyncSession,
        limit: int,
    ) -> list[FeedbackExample]:
        """Load recent feedback corrections as few-shot examples.

        External state — silenced on failure: returns empty list.
        """
        try:
            # Single JOIN query replaces N+1 individual lookups (F-03 fix)
            fb_result = await db.execute(
                select(
                    Email.body_plain,
                    ActionCategory.slug.label("action_slug"),
                    TypeCategory.slug.label("type_slug"),
                )
                .join(Email, ClassificationFeedback.email_id == Email.id)
                .join(
                    ActionCategory,
                    ClassificationFeedback.corrected_action_id == ActionCategory.id,
                )
                .join(
                    TypeCategory,
                    ClassificationFeedback.corrected_type_id == TypeCategory.id,
                )
                .order_by(ClassificationFeedback.corrected_at.desc())
                .limit(limit)
            )
            rows = fb_result.all()
            if not rows:
                return []

            examples: list[FeedbackExample] = []
            for row in rows:
                if row.body_plain is None:
                    continue
                snippet = row.body_plain[: self._settings.classify_feedback_snippet_chars]
                examples.append(
                    FeedbackExample(
                        email_snippet=snippet,
                        correct_action=row.action_slug,
                        correct_type=row.type_slug,
                    )
                )

            return examples

        except SQLAlchemyError as exc:
            logger.warning(
                "classification_feedback_load_failed",
                error=str(exc),
            )
            return []

    async def _call_llm_or_fail(
        self,
        email: Email,
        db: AsyncSession,
        user_prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> AdapterClassificationResult:
        """Call LLM adapter. On failure, transition to CLASSIFICATION_FAILED and re-raise."""
        try:
            return await self._llm_adapter.classify(
                prompt=user_prompt,
                system_prompt=system_prompt,
                options=options,
            )
        except LLMAdapterError:
            # Transition to error state
            try:
                email.transition_to(EmailState.CLASSIFICATION_FAILED)
                await db.commit()
            except SQLAlchemyError as db_exc:
                logger.error(
                    "classification_failed_state_persist_error",
                    email_id=str(email.id),
                    error=str(db_exc),
                )
            raise

    async def _persist_and_transition(
        self,
        db: AsyncSession,
        email: Email,
        adapter_result: AdapterClassificationResult,
        action_cats: list[ActionCategoryDef],
        type_cats: list[TypeCategoryDef],
        final_confidence: Literal["high", "low"],
    ) -> ClassificationResult:
        """Persist classification result and transition email to CLASSIFIED.

        External state — raises SQLAlchemyError on failure.
        """
        # Resolve slugs to category IDs
        action_id = next(c.id for c in action_cats if c.slug == adapter_result.action)
        type_id = next(c.id for c in type_cats if c.slug == adapter_result.type)

        # Parse raw_llm_output for JSONB storage
        raw_output = _parse_raw_llm_output(adapter_result.raw_llm_output)

        confidence_enum = (
            ClassificationConfidence.HIGH
            if final_confidence == "high"
            else ClassificationConfidence.LOW
        )

        db_record = ClassificationResult(
            id=uuid.uuid4(),
            email_id=email.id,
            action_category_id=action_id,
            type_category_id=type_id,
            confidence=confidence_enum,
            raw_llm_output=raw_output,
            fallback_applied=adapter_result.fallback_applied,
        )

        try:
            db.add(db_record)
            email.transition_to(EmailState.CLASSIFIED)
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            raise SQLAlchemyError(
                f"Failed to persist classification for email {email.id}: {exc}"
            ) from exc

        return db_record


def _has_heuristic_disagreement(
    llm_result: AdapterClassificationResult,
    heuristic_result: HeuristicResult,
) -> bool:
    """Check if heuristic disagrees with LLM result.

    Local computation — conditionals, no try/except.
    """
    if not heuristic_result.has_opinion:
        return False

    action_disagrees = (
        heuristic_result.action_hint is not None
        and heuristic_result.action_hint != llm_result.action
    )
    type_disagrees = (
        heuristic_result.type_hint is not None and heuristic_result.type_hint != llm_result.type
    )
    return action_disagrees or type_disagrees


def _find_fallback(
    categories: list[ActionCategoryDef] | list[TypeCategoryDef],
) -> ActionCategoryDef | TypeCategoryDef:
    """Find the fallback category. Raises CategoryNotFoundError if none.

    WARNING-03: Uses next(..., None) with explicit None check.
    """
    fallback = next((c for c in categories if c.is_fallback), None)
    if fallback is None:
        raise CategoryNotFoundError(
            "No fallback category found — ensure DB seed has is_fallback=True"
        )
    return fallback


def _parse_internal_domains(domains_str: str) -> list[str]:
    """Parse comma-separated internal domains string to list."""
    if not domains_str:
        return []
    return [d.strip() for d in domains_str.split(",") if d.strip()]


def _parse_raw_llm_output(raw: str) -> dict[str, str]:
    """Convert adapter raw_llm_output (str) to JSONB-compatible dict."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return {"raw_response": raw}
