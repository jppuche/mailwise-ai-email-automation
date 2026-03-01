"""Heuristic classifier for email classification — pure local computation.

Rule-based classification hints that provide a second opinion alongside the LLM.
Heuristics NEVER override the LLM result — they only lower confidence when
there is disagreement (ClassificationService handles this comparison).

contract-docstrings:
  Invariants: All rules are independent and evaluated in order.
    Keyword sets are module-level frozensets (Cat 3: no magic strings).
  Guarantees: Returns a valid HeuristicResult for any input — never raises.
    rules_fired contains the names of all rules that matched.
  Errors: None — pure local computation, no try/except.
  State transitions: None — stateless.

ENFORCEMENT: 0 try/except blocks, 0 ORM imports (verified by grep).
"""

from __future__ import annotations

from src.services.schemas.classification import (
    ClassificationRequest,
    HeuristicResult,
)

# Cat 3: keyword sets as module-level frozensets (no magic strings scattered)
_URGENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "urgent",
        "asap",
        "immediately",
        "critical",
    }
)

_COMPLAINT_KEYWORDS: frozenset[str] = frozenset(
    {
        "dissatisfied",
        "unacceptable",
        "refund",
        "terrible",
        "worst",
        "disgusted",
    }
)

_ESCALATE_KEYWORDS: frozenset[str] = frozenset(
    {
        "ceo",
        "legal",
        "lawsuit",
        "attorney",
        "compliance",
        "gdpr",
    }
)

_SPAM_KEYWORDS_PAIR: tuple[frozenset[str], frozenset[str]] = (
    frozenset({"unsubscribe"}),
    frozenset({"click here", "opt out", "opt-out"}),
)

_NOREPLY_PREFIXES: tuple[str, ...] = ("noreply@", "no-reply@")


class HeuristicClassifier:
    """Rule-based classification hints. NEVER overrides LLM result.

    Heuristic DISAGREES with LLM: log the disagreement, use LLM result,
    but set heuristic_disagreement=True in the service result.
    """

    def classify(
        self,
        request: ClassificationRequest,
        internal_domains: list[str],
    ) -> HeuristicResult:
        """Evaluate all heuristic rules against the email.

        Invariants:
          - request fields are non-empty (validated by Pydantic).

        Guarantees:
          - Returns a valid HeuristicResult for any input.
          - rules_fired lists all rules that matched (may be empty).

        Errors: None — pure local computation.
        State transitions: None.
        """
        action_hint: str | None = None
        type_hint: str | None = None
        rules_fired: list[str] = []

        subject_lower = request.subject.lower()
        body_lower = request.sanitized_body.lower()
        sender_lower = request.sender_email.lower()
        domain_lower = request.sender_domain.lower()

        # Rule 1: urgent keywords in subject
        if any(kw in subject_lower for kw in _URGENT_KEYWORDS):
            type_hint = "urgent"
            rules_fired.append("urgent_keyword")

        # Rule 2: complaint keywords in body
        if any(kw in body_lower for kw in _COMPLAINT_KEYWORDS):
            type_hint = "complaint"
            rules_fired.append("complaint_keyword")

        # Rule 3: internal domain
        if internal_domains and domain_lower in {d.strip().lower() for d in internal_domains}:
            type_hint = "internal"
            rules_fired.append("internal_domain")

        # Rule 4: spam indicators (both keyword groups must match)
        spam_group_a = any(kw in body_lower for kw in _SPAM_KEYWORDS_PAIR[0])
        spam_group_b = any(kw in body_lower for kw in _SPAM_KEYWORDS_PAIR[1])
        if spam_group_a and spam_group_b:
            type_hint = "spam"
            rules_fired.append("spam_keyword")

        # Rule 5: escalation keywords in subject
        if any(kw in subject_lower for kw in _ESCALATE_KEYWORDS):
            action_hint = "escalate"
            rules_fired.append("escalate_keyword")

        # Rule 6: noreply sender
        if any(sender_lower.startswith(prefix) for prefix in _NOREPLY_PREFIXES):
            type_hint = "notification"
            rules_fired.append("noreply_sender")

        has_opinion = action_hint is not None or type_hint is not None

        return HeuristicResult(
            action_hint=action_hint,
            type_hint=type_hint,
            rules_fired=rules_fired,
            has_opinion=has_opinion,
        )
