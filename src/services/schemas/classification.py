"""Classification service data contracts.

These types are the boundary between the classification service and its callers.
ORM models (src.models.*) are converted to frozen dataclasses before being passed
to PromptBuilder or HeuristicClassifier — those modules never import ORM models.

No ``dict[str, Any]`` at boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ActionCategoryDef:
    """Action category definition — decoupled from ORM model.

    Constructed from ActionCategory ORM model in ClassificationService.
    Passed to PromptBuilder for prompt construction.
    """

    id: uuid.UUID
    slug: str
    name: str
    description: str
    is_fallback: bool


@dataclass(frozen=True)
class TypeCategoryDef:
    """Type category definition — decoupled from ORM model.

    Constructed from TypeCategory ORM model in ClassificationService.
    Passed to PromptBuilder for prompt construction.
    """

    id: uuid.UUID
    slug: str
    name: str
    description: str
    is_fallback: bool


class FeedbackExample(BaseModel):
    """A few-shot example for the classification prompt.

    Constructed from ClassificationFeedback ORM model + Email body snippet.
    """

    email_snippet: str = Field(min_length=1)
    correct_action: str = Field(min_length=1)
    correct_type: str = Field(min_length=1)


class HeuristicResult(BaseModel):
    """Result from the rule-based heuristic classifier.

    Heuristics provide a second opinion — they NEVER override the LLM result.
    When heuristics disagree with the LLM, confidence is lowered to LOW.
    """

    action_hint: str | None = None
    type_hint: str | None = None
    rules_fired: list[str] = Field(default_factory=list)
    has_opinion: bool = False


class ClassificationRequest(BaseModel):
    """Input to the classification service."""

    email_id: uuid.UUID
    sanitized_body: str = Field(min_length=1)
    subject: str
    sender_email: str = Field(min_length=1)
    sender_domain: str = Field(min_length=1)


class ClassificationServiceResult(BaseModel):
    """Result of classifying a single email.

    Distinct from the adapter-layer and ORM-layer ClassificationResult models.
    This is the business-level result that includes heuristic context.
    """

    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: Literal["high", "low"]
    fallback_applied: bool
    heuristic_disagreement: bool
    heuristic_result: HeuristicResult | None
    db_record_id: uuid.UUID


class ClassificationBatchResult(BaseModel):
    """Aggregate result of a batch classification run."""

    total: int
    succeeded: int
    failed: int
    results: list[ClassificationServiceResult] = Field(default_factory=list)
    failures: list[tuple[uuid.UUID, str]] = Field(default_factory=list)
