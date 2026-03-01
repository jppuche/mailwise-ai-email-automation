"""Tests for classification service schemas.

Covers: ActionCategoryDef, TypeCategoryDef, FeedbackExample, HeuristicResult,
ClassificationRequest, ClassificationServiceResult, ClassificationBatchResult.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from pydantic import ValidationError

from src.services.schemas.classification import (
    ActionCategoryDef,
    ClassificationBatchResult,
    ClassificationRequest,
    ClassificationServiceResult,
    FeedbackExample,
    HeuristicResult,
    TypeCategoryDef,
)


# ---------------------------------------------------------------------------
# ActionCategoryDef — frozen dataclass
# ---------------------------------------------------------------------------


class TestActionCategoryDef:
    def test_creation_with_all_fields(self) -> None:
        cat_id = uuid.uuid4()
        cat = ActionCategoryDef(
            id=cat_id,
            slug="reply",
            name="Reply Required",
            description="Customer is waiting for a response.",
            is_fallback=False,
        )
        assert cat.id == cat_id
        assert cat.slug == "reply"
        assert cat.name == "Reply Required"
        assert cat.description == "Customer is waiting for a response."
        assert cat.is_fallback is False

    def test_creation_as_fallback(self) -> None:
        cat = ActionCategoryDef(
            id=uuid.uuid4(),
            slug="no-action",
            name="No Action",
            description="Informational only.",
            is_fallback=True,
        )
        assert cat.is_fallback is True

    def test_frozen_assignment_raises(self) -> None:
        cat = ActionCategoryDef(
            id=uuid.uuid4(),
            slug="reply",
            name="Reply Required",
            description="Customer is waiting for a response.",
            is_fallback=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cat.slug = "changed"  # type: ignore[misc]

    def test_frozen_id_immutable(self) -> None:
        cat = ActionCategoryDef(
            id=uuid.uuid4(),
            slug="forward",
            name="Forward",
            description="Route to specialist team.",
            is_fallback=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cat.id = uuid.uuid4()  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        cat_id = uuid.uuid4()
        a = ActionCategoryDef(
            id=cat_id,
            slug="reply",
            name="Reply Required",
            description="Desc.",
            is_fallback=False,
        )
        b = ActionCategoryDef(
            id=cat_id,
            slug="reply",
            name="Reply Required",
            description="Desc.",
            is_fallback=False,
        )
        assert a == b


# ---------------------------------------------------------------------------
# TypeCategoryDef — frozen dataclass
# ---------------------------------------------------------------------------


class TestTypeCategoryDef:
    def test_creation_with_all_fields(self) -> None:
        cat_id = uuid.uuid4()
        cat = TypeCategoryDef(
            id=cat_id,
            slug="complaint",
            name="Complaint",
            description="Customer complaint requiring urgent attention.",
            is_fallback=False,
        )
        assert cat.id == cat_id
        assert cat.slug == "complaint"
        assert cat.name == "Complaint"
        assert cat.description == "Customer complaint requiring urgent attention."
        assert cat.is_fallback is False

    def test_creation_as_fallback(self) -> None:
        cat = TypeCategoryDef(
            id=uuid.uuid4(),
            slug="other",
            name="Other",
            description="Uncategorised email type.",
            is_fallback=True,
        )
        assert cat.is_fallback is True

    def test_frozen_assignment_raises(self) -> None:
        cat = TypeCategoryDef(
            id=uuid.uuid4(),
            slug="complaint",
            name="Complaint",
            description="Desc.",
            is_fallback=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cat.slug = "changed"  # type: ignore[misc]

    def test_frozen_is_fallback_immutable(self) -> None:
        cat = TypeCategoryDef(
            id=uuid.uuid4(),
            slug="inquiry",
            name="Inquiry",
            description="General inquiry.",
            is_fallback=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cat.is_fallback = True  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        cat_id = uuid.uuid4()
        a = TypeCategoryDef(
            id=cat_id,
            slug="inquiry",
            name="Inquiry",
            description="General inquiry.",
            is_fallback=False,
        )
        b = TypeCategoryDef(
            id=cat_id,
            slug="inquiry",
            name="Inquiry",
            description="General inquiry.",
            is_fallback=False,
        )
        assert a == b


# ---------------------------------------------------------------------------
# FeedbackExample — Pydantic BaseModel
# ---------------------------------------------------------------------------


class TestFeedbackExample:
    def test_valid_creation(self) -> None:
        example = FeedbackExample(
            email_snippet="Please cancel my subscription immediately.",
            correct_action="reply",
            correct_type="complaint",
        )
        assert example.email_snippet == "Please cancel my subscription immediately."
        assert example.correct_action == "reply"
        assert example.correct_type == "complaint"

    def test_email_snippet_empty_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FeedbackExample(
                email_snippet="",
                correct_action="reply",
                correct_type="complaint",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("email_snippet",) for e in errors)

    def test_correct_action_empty_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FeedbackExample(
                email_snippet="Some email text.",
                correct_action="",
                correct_type="complaint",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("correct_action",) for e in errors)

    def test_correct_type_empty_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FeedbackExample(
                email_snippet="Some email text.",
                correct_action="reply",
                correct_type="",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("correct_type",) for e in errors)

    def test_single_char_fields_valid(self) -> None:
        example = FeedbackExample(
            email_snippet="?",
            correct_action="a",
            correct_type="b",
        )
        assert example.email_snippet == "?"

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackExample(  # type: ignore[call-arg]
                email_snippet="Some text.",
                correct_action="reply",
            )


# ---------------------------------------------------------------------------
# HeuristicResult — Pydantic BaseModel
# ---------------------------------------------------------------------------


class TestHeuristicResult:
    def test_defaults(self) -> None:
        result = HeuristicResult()
        assert result.action_hint is None
        assert result.type_hint is None
        assert result.rules_fired == []
        assert result.has_opinion is False

    def test_with_hints_set(self) -> None:
        result = HeuristicResult(
            action_hint="reply",
            type_hint="complaint",
            rules_fired=["vip_sender", "urgent_keyword"],
            has_opinion=True,
        )
        assert result.action_hint == "reply"
        assert result.type_hint == "complaint"
        assert result.rules_fired == ["vip_sender", "urgent_keyword"]
        assert result.has_opinion is True

    def test_partial_hints(self) -> None:
        result = HeuristicResult(action_hint="forward")
        assert result.action_hint == "forward"
        assert result.type_hint is None
        assert result.has_opinion is False

    def test_rules_fired_default_is_empty_list(self) -> None:
        a = HeuristicResult()
        b = HeuristicResult()
        # Each instance gets its own list (default_factory — not shared)
        a.rules_fired.append("rule_x")
        assert b.rules_fired == []

    def test_rules_fired_accepts_multiple_entries(self) -> None:
        result = HeuristicResult(
            rules_fired=["rule_a", "rule_b", "rule_c"],
            has_opinion=True,
        )
        assert len(result.rules_fired) == 3

    def test_has_opinion_explicit_false(self) -> None:
        result = HeuristicResult(has_opinion=False)
        assert result.has_opinion is False


# ---------------------------------------------------------------------------
# ClassificationRequest — Pydantic BaseModel
# ---------------------------------------------------------------------------


class TestClassificationRequest:
    def _valid_payload(self) -> dict:  # type: ignore[type-arg]
        return {
            "email_id": uuid.uuid4(),
            "sanitized_body": "Hello, I need help with my invoice.",
            "subject": "Invoice query",
            "sender_email": "customer@example.com",
            "sender_domain": "example.com",
        }

    def test_valid_creation(self) -> None:
        payload = self._valid_payload()
        req = ClassificationRequest(**payload)
        assert req.email_id == payload["email_id"]
        assert req.sanitized_body == "Hello, I need help with my invoice."
        assert req.subject == "Invoice query"
        assert req.sender_email == "customer@example.com"
        assert req.sender_domain == "example.com"

    def test_sanitized_body_empty_raises(self) -> None:
        payload = self._valid_payload()
        payload["sanitized_body"] = ""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationRequest(**payload)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("sanitized_body",) for e in errors)

    def test_sender_email_empty_raises(self) -> None:
        payload = self._valid_payload()
        payload["sender_email"] = ""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationRequest(**payload)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("sender_email",) for e in errors)

    def test_sender_domain_empty_raises(self) -> None:
        payload = self._valid_payload()
        payload["sender_domain"] = ""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationRequest(**payload)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("sender_domain",) for e in errors)

    def test_subject_can_be_empty_string(self) -> None:
        payload = self._valid_payload()
        payload["subject"] = ""
        req = ClassificationRequest(**payload)
        assert req.subject == ""

    def test_email_id_is_uuid(self) -> None:
        payload = self._valid_payload()
        req = ClassificationRequest(**payload)
        assert isinstance(req.email_id, uuid.UUID)

    def test_missing_email_id_raises(self) -> None:
        payload = self._valid_payload()
        del payload["email_id"]
        with pytest.raises(ValidationError):
            ClassificationRequest(**payload)


# ---------------------------------------------------------------------------
# ClassificationServiceResult — Pydantic BaseModel
# ---------------------------------------------------------------------------


class TestClassificationServiceResult:
    def _valid_result(self, **overrides: object) -> ClassificationServiceResult:
        defaults: dict[str, object] = {
            "email_id": uuid.uuid4(),
            "action_slug": "reply",
            "type_slug": "complaint",
            "confidence": "high",
            "fallback_applied": False,
            "heuristic_disagreement": False,
            "heuristic_result": None,
            "db_record_id": uuid.uuid4(),
        }
        defaults.update(overrides)
        return ClassificationServiceResult(**defaults)  # type: ignore[arg-type]

    def test_valid_creation_high_confidence(self) -> None:
        result = self._valid_result(confidence="high")
        assert result.confidence == "high"
        assert result.heuristic_result is None

    def test_valid_creation_low_confidence(self) -> None:
        result = self._valid_result(confidence="low")
        assert result.confidence == "low"

    def test_confidence_invalid_literal_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            self._valid_result(confidence="medium")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("confidence",) for e in errors)

    def test_confidence_invalid_uppercase_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            self._valid_result(confidence="HIGH")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("confidence",) for e in errors)

    def test_heuristic_result_none_allowed(self) -> None:
        result = self._valid_result(heuristic_result=None)
        assert result.heuristic_result is None

    def test_heuristic_result_populated(self) -> None:
        heuristic = HeuristicResult(
            action_hint="reply",
            type_hint="complaint",
            rules_fired=["urgent_keyword"],
            has_opinion=True,
        )
        result = self._valid_result(
            confidence="low",
            heuristic_disagreement=True,
            heuristic_result=heuristic,
        )
        assert result.heuristic_result is not None
        assert result.heuristic_result.action_hint == "reply"
        assert result.heuristic_disagreement is True

    def test_fallback_applied_true(self) -> None:
        result = self._valid_result(fallback_applied=True, action_slug="no-action")
        assert result.fallback_applied is True

    def test_email_id_and_db_record_id_are_uuids(self) -> None:
        email_id = uuid.uuid4()
        db_id = uuid.uuid4()
        result = self._valid_result(email_id=email_id, db_record_id=db_id)
        assert result.email_id == email_id
        assert result.db_record_id == db_id

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationServiceResult(  # type: ignore[call-arg]
                email_id=uuid.uuid4(),
                action_slug="reply",
                # type_slug omitted
                confidence="high",
                fallback_applied=False,
                heuristic_disagreement=False,
                heuristic_result=None,
                db_record_id=uuid.uuid4(),
            )


# ---------------------------------------------------------------------------
# ClassificationBatchResult — Pydantic BaseModel
# ---------------------------------------------------------------------------


class TestClassificationBatchResult:
    def _make_service_result(self) -> ClassificationServiceResult:
        return ClassificationServiceResult(
            email_id=uuid.uuid4(),
            action_slug="reply",
            type_slug="complaint",
            confidence="high",
            fallback_applied=False,
            heuristic_disagreement=False,
            heuristic_result=None,
            db_record_id=uuid.uuid4(),
        )

    def test_valid_creation(self) -> None:
        batch = ClassificationBatchResult(total=3, succeeded=2, failed=1)
        assert batch.total == 3
        assert batch.succeeded == 2
        assert batch.failed == 1
        assert batch.results == []
        assert batch.failures == []

    def test_default_empty_lists(self) -> None:
        batch = ClassificationBatchResult(total=0, succeeded=0, failed=0)
        assert batch.results == []
        assert batch.failures == []

    def test_default_lists_not_shared(self) -> None:
        a = ClassificationBatchResult(total=0, succeeded=0, failed=0)
        b = ClassificationBatchResult(total=0, succeeded=0, failed=0)
        a.results.append(self._make_service_result())
        assert b.results == []

    def test_with_results_populated(self) -> None:
        r1 = self._make_service_result()
        r2 = self._make_service_result()
        batch = ClassificationBatchResult(
            total=2,
            succeeded=2,
            failed=0,
            results=[r1, r2],
        )
        assert len(batch.results) == 2
        assert batch.results[0].action_slug == "reply"

    def test_with_failures_as_uuid_str_tuples(self) -> None:
        eid1 = uuid.uuid4()
        eid2 = uuid.uuid4()
        batch = ClassificationBatchResult(
            total=2,
            succeeded=0,
            failed=2,
            failures=[
                (eid1, "LLM timeout after 3 retries"),
                (eid2, "No action categories found"),
            ],
        )
        assert len(batch.failures) == 2
        assert batch.failures[0][0] == eid1
        assert batch.failures[0][1] == "LLM timeout after 3 retries"
        assert batch.failures[1][0] == eid2

    def test_mixed_results_and_failures(self) -> None:
        r1 = self._make_service_result()
        eid_failed = uuid.uuid4()
        batch = ClassificationBatchResult(
            total=2,
            succeeded=1,
            failed=1,
            results=[r1],
            failures=[(eid_failed, "DB write error")],
        )
        assert len(batch.results) == 1
        assert len(batch.failures) == 1

    def test_zero_total(self) -> None:
        batch = ClassificationBatchResult(total=0, succeeded=0, failed=0)
        assert batch.total == 0

    def test_missing_total_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClassificationBatchResult(succeeded=0, failed=0)  # type: ignore[call-arg]
