"""Tests for pipeline result dataclasses (src/tasks/result_types.py).

Validates that all 5 frozen dataclasses are fully typed:
  - No ``Any`` fields — all annotations are fully typed.
  - Results stored in DB/typed dataclasses, NOT via Celery result backend
    (verified by absence of ``AsyncResult`` in src/tasks/).

Each dataclass is also verified for:
  - Importability
  - Correct field names and count
  - Frozen immutability (FrozenInstanceError on assignment)
  - Correct default values for optional fields
  - UUID field types preserved at runtime
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import sys
import typing
import uuid

import pytest

from src.tasks.result_types import (
    ClassifyResult,
    CRMSyncTaskResult,
    DraftTaskResult,
    IngestResult,
    RouteResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASKS_SRC = pathlib.Path(__file__).parent.parent.parent / "src" / "tasks"


def _get_hints(cls: type) -> dict[str, typing.Any]:
    """Resolve type hints for a dataclass, handling ``from __future__ import annotations``."""
    module = sys.modules[cls.__module__]
    globalns = vars(module)
    return typing.get_type_hints(cls, globalns=globalns)


def _has_any(hints: dict[str, typing.Any]) -> list[str]:
    """Return field names whose annotation is or contains ``typing.Any``."""
    offenders: list[str] = []
    for name, hint in hints.items():
        if hint is typing.Any:
            offenders.append(name)
            continue
        # Check Union / Optional args for Any leakage
        args = getattr(hint, "__args__", None)
        if args and any(a is typing.Any for a in args):
            offenders.append(name)
    return offenders


# ---------------------------------------------------------------------------
# Importability — all 5 classes must be accessible
# ---------------------------------------------------------------------------


class TestImportability:
    """All 5 result dataclasses are importable from src.tasks.result_types."""

    def test_ingest_result_importable(self) -> None:
        assert IngestResult is not None

    def test_classify_result_importable(self) -> None:
        assert ClassifyResult is not None

    def test_route_result_importable(self) -> None:
        assert RouteResult is not None

    def test_crm_sync_task_result_importable(self) -> None:
        assert CRMSyncTaskResult is not None

    def test_draft_task_result_importable(self) -> None:
        assert DraftTaskResult is not None

    def test_all_are_dataclasses(self) -> None:
        for cls in (IngestResult, ClassifyResult, RouteResult, CRMSyncTaskResult, DraftTaskResult):
            assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"


# ---------------------------------------------------------------------------
# IngestResult
# ---------------------------------------------------------------------------


class TestIngestResult:
    """IngestResult(account_id, emails_fetched, emails_skipped, emails_failed)."""

    def test_construction_required_fields(self) -> None:
        result = IngestResult(
            account_id="acc-001",
            emails_fetched=10,
            emails_skipped=2,
            emails_failed=0,
        )
        assert result.account_id == "acc-001"
        assert result.emails_fetched == 10
        assert result.emails_skipped == 2
        assert result.emails_failed == 0

    def test_frozen_account_id(self) -> None:
        result = IngestResult(
            account_id="acc-001",
            emails_fetched=5,
            emails_skipped=0,
            emails_failed=0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.account_id = "changed"  # type: ignore[misc]

    def test_frozen_emails_fetched(self) -> None:
        result = IngestResult(
            account_id="acc-001",
            emails_fetched=5,
            emails_skipped=0,
            emails_failed=0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.emails_fetched = 99  # type: ignore[misc]

    def test_field_names(self) -> None:
        field_names = {f.name for f in dataclasses.fields(IngestResult)}
        assert field_names == {"account_id", "emails_fetched", "emails_skipped", "emails_failed"}

    def test_field_count(self) -> None:
        assert len(dataclasses.fields(IngestResult)) == 4

    def test_no_any_annotations(self) -> None:
        hints = _get_hints(IngestResult)
        offenders = _has_any(hints)
        assert offenders == [], f"Fields with Any annotation: {offenders}"

    def test_account_id_type_is_str(self) -> None:
        hints = _get_hints(IngestResult)
        assert hints["account_id"] is str

    def test_counter_fields_type_is_int(self) -> None:
        hints = _get_hints(IngestResult)
        assert hints["emails_fetched"] is int
        assert hints["emails_skipped"] is int
        assert hints["emails_failed"] is int

    def test_zero_counts_allowed(self) -> None:
        result = IngestResult(
            account_id="acc-002",
            emails_fetched=0,
            emails_skipped=0,
            emails_failed=0,
        )
        assert result.emails_fetched == 0
        assert result.emails_skipped == 0
        assert result.emails_failed == 0

    def test_equality_by_value(self) -> None:
        a = IngestResult(account_id="x", emails_fetched=1, emails_skipped=0, emails_failed=0)
        b = IngestResult(account_id="x", emails_fetched=1, emails_skipped=0, emails_failed=0)
        assert a == b

    def test_inequality_on_different_account(self) -> None:
        a = IngestResult(account_id="x", emails_fetched=1, emails_skipped=0, emails_failed=0)
        b = IngestResult(account_id="y", emails_fetched=1, emails_skipped=0, emails_failed=0)
        assert a != b


# ---------------------------------------------------------------------------
# ClassifyResult
# ---------------------------------------------------------------------------


class TestClassifyResult:
    """ClassifyResult(email_id, success, action=None, type=None, confidence=None)."""

    def test_construction_required_only(self) -> None:
        eid = uuid.uuid4()
        result = ClassifyResult(email_id=eid, success=True)
        assert result.email_id == eid
        assert result.success is True
        assert result.action is None
        assert result.type is None
        assert result.confidence is None

    def test_construction_all_fields(self) -> None:
        eid = uuid.uuid4()
        result = ClassifyResult(
            email_id=eid,
            success=True,
            action="reply",
            type="support",
            confidence="high",
        )
        assert result.action == "reply"
        assert result.type == "support"
        assert result.confidence == "high"

    def test_construction_low_confidence(self) -> None:
        result = ClassifyResult(
            email_id=uuid.uuid4(),
            success=True,
            action="archive",
            type="notification",
            confidence="low",
        )
        assert result.confidence == "low"

    def test_construction_failed_classification(self) -> None:
        result = ClassifyResult(email_id=uuid.uuid4(), success=False)
        assert result.success is False
        assert result.action is None
        assert result.type is None
        assert result.confidence is None

    def test_frozen_email_id(self) -> None:
        result = ClassifyResult(email_id=uuid.uuid4(), success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.email_id = uuid.uuid4()  # type: ignore[misc]

    def test_frozen_success(self) -> None:
        result = ClassifyResult(email_id=uuid.uuid4(), success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.success = False  # type: ignore[misc]

    def test_frozen_action(self) -> None:
        result = ClassifyResult(email_id=uuid.uuid4(), success=True, action="reply")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.action = "archive"  # type: ignore[misc]

    def test_field_names(self) -> None:
        field_names = {f.name for f in dataclasses.fields(ClassifyResult)}
        assert field_names == {"email_id", "success", "action", "type", "confidence"}

    def test_field_count(self) -> None:
        assert len(dataclasses.fields(ClassifyResult)) == 5

    def test_no_any_annotations(self) -> None:
        hints = _get_hints(ClassifyResult)
        offenders = _has_any(hints)
        assert offenders == [], f"Fields with Any annotation: {offenders}"

    def test_email_id_type_is_uuid(self) -> None:
        hints = _get_hints(ClassifyResult)
        assert hints["email_id"] is uuid.UUID

    def test_success_type_is_bool(self) -> None:
        hints = _get_hints(ClassifyResult)
        assert hints["success"] is bool

    def test_optional_fields_have_none_default(self) -> None:
        for field in dataclasses.fields(ClassifyResult):
            if field.name in ("action", "type", "confidence"):
                assert field.default is None, f"{field.name} default should be None"

    def test_email_id_is_uuid_instance(self) -> None:
        eid = uuid.uuid4()
        result = ClassifyResult(email_id=eid, success=True)
        assert isinstance(result.email_id, uuid.UUID)

    def test_equality_same_values(self) -> None:
        eid = uuid.uuid4()
        a = ClassifyResult(email_id=eid, success=True, action="reply")
        b = ClassifyResult(email_id=eid, success=True, action="reply")
        assert a == b


# ---------------------------------------------------------------------------
# RouteResult
# ---------------------------------------------------------------------------


class TestRouteResult:
    """RouteResult(email_id, actions_dispatched, actions_failed)."""

    def test_construction(self) -> None:
        eid = uuid.uuid4()
        result = RouteResult(email_id=eid, actions_dispatched=3, actions_failed=0)
        assert result.email_id == eid
        assert result.actions_dispatched == 3
        assert result.actions_failed == 0

    def test_partial_failure(self) -> None:
        result = RouteResult(email_id=uuid.uuid4(), actions_dispatched=2, actions_failed=1)
        assert result.actions_dispatched == 2
        assert result.actions_failed == 1

    def test_no_actions_dispatched(self) -> None:
        result = RouteResult(email_id=uuid.uuid4(), actions_dispatched=0, actions_failed=0)
        assert result.actions_dispatched == 0

    def test_frozen_email_id(self) -> None:
        result = RouteResult(email_id=uuid.uuid4(), actions_dispatched=1, actions_failed=0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.email_id = uuid.uuid4()  # type: ignore[misc]

    def test_frozen_actions_dispatched(self) -> None:
        result = RouteResult(email_id=uuid.uuid4(), actions_dispatched=1, actions_failed=0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.actions_dispatched = 99  # type: ignore[misc]

    def test_frozen_actions_failed(self) -> None:
        result = RouteResult(email_id=uuid.uuid4(), actions_dispatched=1, actions_failed=0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.actions_failed = 99  # type: ignore[misc]

    def test_field_names(self) -> None:
        field_names = {f.name for f in dataclasses.fields(RouteResult)}
        assert field_names == {"email_id", "actions_dispatched", "actions_failed"}

    def test_field_count(self) -> None:
        assert len(dataclasses.fields(RouteResult)) == 3

    def test_no_any_annotations(self) -> None:
        hints = _get_hints(RouteResult)
        offenders = _has_any(hints)
        assert offenders == [], f"Fields with Any annotation: {offenders}"

    def test_email_id_type_is_uuid(self) -> None:
        hints = _get_hints(RouteResult)
        assert hints["email_id"] is uuid.UUID

    def test_counter_fields_type_is_int(self) -> None:
        hints = _get_hints(RouteResult)
        assert hints["actions_dispatched"] is int
        assert hints["actions_failed"] is int

    def test_email_id_is_uuid_instance(self) -> None:
        eid = uuid.uuid4()
        result = RouteResult(email_id=eid, actions_dispatched=1, actions_failed=0)
        assert isinstance(result.email_id, uuid.UUID)


# ---------------------------------------------------------------------------
# CRMSyncTaskResult
# ---------------------------------------------------------------------------


class TestCRMSyncTaskResult:
    """CRMSyncTaskResult(email_id, contact_id=None, activity_id=None, overall_success=False)."""

    def test_construction_required_only(self) -> None:
        eid = uuid.uuid4()
        result = CRMSyncTaskResult(email_id=eid)
        assert result.email_id == eid
        assert result.contact_id is None
        assert result.activity_id is None
        assert result.overall_success is False

    def test_construction_full_success(self) -> None:
        eid = uuid.uuid4()
        result = CRMSyncTaskResult(
            email_id=eid,
            contact_id="hs-001",
            activity_id="act-999",
            overall_success=True,
        )
        assert result.contact_id == "hs-001"
        assert result.activity_id == "act-999"
        assert result.overall_success is True

    def test_construction_contact_only(self) -> None:
        result = CRMSyncTaskResult(
            email_id=uuid.uuid4(),
            contact_id="hs-002",
            overall_success=True,
        )
        assert result.contact_id == "hs-002"
        assert result.activity_id is None

    def test_default_overall_success_is_false(self) -> None:
        result = CRMSyncTaskResult(email_id=uuid.uuid4())
        assert result.overall_success is False

    def test_frozen_email_id(self) -> None:
        result = CRMSyncTaskResult(email_id=uuid.uuid4())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.email_id = uuid.uuid4()  # type: ignore[misc]

    def test_frozen_contact_id(self) -> None:
        result = CRMSyncTaskResult(email_id=uuid.uuid4(), contact_id="hs-001")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.contact_id = "changed"  # type: ignore[misc]

    def test_frozen_overall_success(self) -> None:
        result = CRMSyncTaskResult(email_id=uuid.uuid4(), overall_success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.overall_success = False  # type: ignore[misc]

    def test_field_names(self) -> None:
        field_names = {f.name for f in dataclasses.fields(CRMSyncTaskResult)}
        assert field_names == {"email_id", "contact_id", "activity_id", "overall_success"}

    def test_field_count(self) -> None:
        assert len(dataclasses.fields(CRMSyncTaskResult)) == 4

    def test_no_any_annotations(self) -> None:
        hints = _get_hints(CRMSyncTaskResult)
        offenders = _has_any(hints)
        assert offenders == [], f"Fields with Any annotation: {offenders}"

    def test_email_id_type_is_uuid(self) -> None:
        hints = _get_hints(CRMSyncTaskResult)
        assert hints["email_id"] is uuid.UUID

    def test_overall_success_type_is_bool(self) -> None:
        hints = _get_hints(CRMSyncTaskResult)
        assert hints["overall_success"] is bool

    def test_optional_str_fields_default_none(self) -> None:
        for field in dataclasses.fields(CRMSyncTaskResult):
            if field.name in ("contact_id", "activity_id"):
                assert field.default is None, f"{field.name} default should be None"

    def test_email_id_is_uuid_instance(self) -> None:
        eid = uuid.uuid4()
        result = CRMSyncTaskResult(email_id=eid)
        assert isinstance(result.email_id, uuid.UUID)

    def test_equality_same_values(self) -> None:
        eid = uuid.uuid4()
        a = CRMSyncTaskResult(email_id=eid, contact_id="c1", overall_success=True)
        b = CRMSyncTaskResult(email_id=eid, contact_id="c1", overall_success=True)
        assert a == b


# ---------------------------------------------------------------------------
# DraftTaskResult
# ---------------------------------------------------------------------------


class TestDraftTaskResult:
    """DraftTaskResult(email_id, draft_id=None, status="pending")."""

    def test_construction_required_only(self) -> None:
        eid = uuid.uuid4()
        result = DraftTaskResult(email_id=eid)
        assert result.email_id == eid
        assert result.draft_id is None
        assert result.status == "pending"

    def test_construction_full(self) -> None:
        eid = uuid.uuid4()
        did = uuid.uuid4()
        result = DraftTaskResult(email_id=eid, draft_id=did, status="generated")
        assert result.email_id == eid
        assert result.draft_id == did
        assert result.status == "generated"

    def test_default_status_is_pending(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4())
        assert result.status == "pending"

    def test_status_generated(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4(), status="generated")
        assert result.status == "generated"

    def test_status_failed(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4(), status="failed")
        assert result.status == "failed"

    def test_status_push_failed(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4(), status="generated_push_failed")
        assert result.status == "generated_push_failed"

    def test_frozen_email_id(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.email_id = uuid.uuid4()  # type: ignore[misc]

    def test_frozen_draft_id(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4(), draft_id=uuid.uuid4())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.draft_id = uuid.uuid4()  # type: ignore[misc]

    def test_frozen_status(self) -> None:
        result = DraftTaskResult(email_id=uuid.uuid4(), status="generated")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.status = "failed"  # type: ignore[misc]

    def test_field_names(self) -> None:
        field_names = {f.name for f in dataclasses.fields(DraftTaskResult)}
        assert field_names == {"email_id", "draft_id", "status"}

    def test_field_count(self) -> None:
        assert len(dataclasses.fields(DraftTaskResult)) == 3

    def test_no_any_annotations(self) -> None:
        hints = _get_hints(DraftTaskResult)
        offenders = _has_any(hints)
        assert offenders == [], f"Fields with Any annotation: {offenders}"

    def test_email_id_type_is_uuid(self) -> None:
        hints = _get_hints(DraftTaskResult)
        assert hints["email_id"] is uuid.UUID

    def test_status_type_is_str(self) -> None:
        hints = _get_hints(DraftTaskResult)
        assert hints["status"] is str

    def test_draft_id_default_is_none(self) -> None:
        for field in dataclasses.fields(DraftTaskResult):
            if field.name == "draft_id":
                assert field.default is None

    def test_status_field_default_is_pending(self) -> None:
        for field in dataclasses.fields(DraftTaskResult):
            if field.name == "status":
                assert field.default == "pending"

    def test_email_id_is_uuid_instance(self) -> None:
        eid = uuid.uuid4()
        result = DraftTaskResult(email_id=eid)
        assert isinstance(result.email_id, uuid.UUID)

    def test_draft_id_is_uuid_instance_when_provided(self) -> None:
        did = uuid.uuid4()
        result = DraftTaskResult(email_id=uuid.uuid4(), draft_id=did)
        assert isinstance(result.draft_id, uuid.UUID)

    def test_equality_same_values(self) -> None:
        eid = uuid.uuid4()
        did = uuid.uuid4()
        a = DraftTaskResult(email_id=eid, draft_id=did, status="generated")
        b = DraftTaskResult(email_id=eid, draft_id=did, status="generated")
        assert a == b


# ---------------------------------------------------------------------------
# AsyncResult must NOT appear in src/tasks/
# ---------------------------------------------------------------------------


class TestAsyncResultAbsence:
    """Task results stored in DB/typed dataclasses — not via AsyncResult.get().

    Verifies that ``AsyncResult`` does not appear in any .py file under
    ``src/tasks/``. This guards against accidental re-introduction of the
    ``Any``-typed Celery result backend pattern.
    """

    def test_async_result_absent_from_tasks_package(self) -> None:
        """No .py file in src/tasks/ contains AsyncResult as a code identifier.

        Docstring prose references (e.g. ``AsyncResult.get()``) are excluded
        because they document the prohibition, not violate it. The check catches
        lines where AsyncResult is used as an identifier: imports, assignments,
        function calls, or type annotations.
        """
        task_files = list(_TASKS_SRC.glob("*.py"))
        assert task_files, f"No .py files found under {_TASKS_SRC}"

        # Match AsyncResult only when NOT surrounded by RST double-backtick pairs.
        # ``AsyncResult`` in a docstring is documentation, not code.
        _rst_backtick = re.compile(r"``AsyncResult[^`]*``")
        _code_identifier = re.compile(r"(?<!`)AsyncResult(?!`)")

        violations: list[str] = []
        for py_file in task_files:
            source = py_file.read_text(encoding="utf-8")
            for lineno, line in enumerate(source.splitlines(), start=1):
                if "AsyncResult" not in line:
                    continue
                # Strip RST backtick references from the line before checking.
                stripped = _rst_backtick.sub("", line)
                if _code_identifier.search(stripped):
                    violations.append(f"{py_file.name}:{lineno}: {line.rstrip()}")

        assert violations == [], (
            "AsyncResult found as a code identifier in src/tasks/ -- use typed "
            "dataclasses stored in DB. Violations:\n" + "\n".join(violations)
        )

    def test_result_types_module_has_no_async_result_import(self) -> None:
        """result_types.py must not import AsyncResult."""
        result_types_file = _TASKS_SRC / "result_types.py"
        assert result_types_file.exists()
        source = result_types_file.read_text(encoding="utf-8")
        import_lines = [
            line
            for line in source.splitlines()
            if line.startswith(("import", "from")) and "AsyncResult" in line
        ]
        assert import_lines == [], f"AsyncResult imported in result_types.py: {import_lines}"
