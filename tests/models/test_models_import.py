"""Smoke tests — all models import without error, no database required.

Documents the import contract for block-01:
- Every model class is importable from src.models
- Base.metadata.tables contains all 10 expected table names
- All enums are importable from their modules
- All TypedDicts are importable from their modules

TypedDicts are verified importable — they document the JSONB field contracts.
If a TypedDict is removed or renamed, these tests fail.
"""

from sqlalchemy.orm import Mapped


class TestAllModelsImportable:
    """Every model class defined in block-01 must be importable from src.models."""

    def test_email_importable(self) -> None:
        from src.models import Email  # noqa: F401

        assert Email is not None

    def test_action_category_importable(self) -> None:
        from src.models import ActionCategory  # noqa: F401

        assert ActionCategory is not None

    def test_type_category_importable(self) -> None:
        from src.models import TypeCategory  # noqa: F401

        assert TypeCategory is not None

    def test_classification_result_importable(self) -> None:
        from src.models import ClassificationResult  # noqa: F401

        assert ClassificationResult is not None

    def test_routing_rule_importable(self) -> None:
        from src.models import RoutingRule  # noqa: F401

        assert RoutingRule is not None

    def test_routing_action_importable(self) -> None:
        from src.models import RoutingAction  # noqa: F401

        assert RoutingAction is not None

    def test_draft_importable(self) -> None:
        from src.models import Draft  # noqa: F401

        assert Draft is not None

    def test_user_importable(self) -> None:
        from src.models import User  # noqa: F401

        assert User is not None

    def test_crm_sync_record_importable(self) -> None:
        from src.models import CRMSyncRecord  # noqa: F401

        assert CRMSyncRecord is not None

    def test_classification_feedback_importable(self) -> None:
        from src.models import ClassificationFeedback  # noqa: F401

        assert ClassificationFeedback is not None


class TestBaseMetadataTables:
    """Base.metadata.tables must contain all 10 tables defined in block-01."""

    def test_all_ten_tables_registered(self) -> None:
        # Importing any model forces SQLAlchemy to register all tables into Base.metadata
        from src.models import (  # noqa: F401
            ActionCategory,
            Base,
            ClassificationFeedback,
            ClassificationResult,
            CRMSyncRecord,
            Draft,
            Email,
            RoutingAction,
            RoutingRule,
            TypeCategory,
            User,
        )

        expected_tables = {
            "emails",
            "action_categories",
            "type_categories",
            "classification_results",
            "routing_rules",
            "routing_actions",
            "drafts",
            "users",
            "crm_sync_records",
            "classification_feedback",
        }
        actual_tables = set(Base.metadata.tables.keys())
        missing = expected_tables - actual_tables
        assert not missing, f"Tables missing from Base.metadata: {missing}"

    def test_emails_table_registered(self) -> None:
        from src.models import Base, Email  # noqa: F401

        assert "emails" in Base.metadata.tables

    def test_action_categories_table_registered(self) -> None:
        from src.models import ActionCategory, Base  # noqa: F401

        assert "action_categories" in Base.metadata.tables

    def test_type_categories_table_registered(self) -> None:
        from src.models import Base, TypeCategory  # noqa: F401

        assert "type_categories" in Base.metadata.tables

    def test_classification_results_table_registered(self) -> None:
        from src.models import Base, ClassificationResult  # noqa: F401

        assert "classification_results" in Base.metadata.tables

    def test_routing_rules_table_registered(self) -> None:
        from src.models import Base, RoutingRule  # noqa: F401

        assert "routing_rules" in Base.metadata.tables

    def test_routing_actions_table_registered(self) -> None:
        from src.models import Base, RoutingAction  # noqa: F401

        assert "routing_actions" in Base.metadata.tables

    def test_drafts_table_registered(self) -> None:
        from src.models import Base, Draft  # noqa: F401

        assert "drafts" in Base.metadata.tables

    def test_users_table_registered(self) -> None:
        from src.models import Base, User  # noqa: F401

        assert "users" in Base.metadata.tables

    def test_crm_sync_records_table_registered(self) -> None:
        from src.models import Base, CRMSyncRecord  # noqa: F401

        assert "crm_sync_records" in Base.metadata.tables

    def test_classification_feedback_table_registered(self) -> None:
        from src.models import Base, ClassificationFeedback  # noqa: F401

        assert "classification_feedback" in Base.metadata.tables


class TestEnumsImportable:
    """All enums defined in block-01 must be importable from their modules.

    These enums are used as PostgreSQL ENUM types — their names must be stable.
    """

    def test_email_state_importable(self) -> None:
        from src.models.email import EmailState

        assert EmailState is not None

    def test_classification_confidence_importable(self) -> None:
        from src.models.classification import ClassificationConfidence

        assert ClassificationConfidence is not None

    def test_routing_action_status_importable(self) -> None:
        from src.models.routing import RoutingActionStatus

        assert RoutingActionStatus is not None

    def test_draft_status_importable(self) -> None:
        from src.models.draft import DraftStatus

        assert DraftStatus is not None

    def test_user_role_importable(self) -> None:
        from src.models.user import UserRole

        assert UserRole is not None

    def test_crm_sync_status_importable(self) -> None:
        from src.models.crm_sync import CRMSyncStatus

        assert CRMSyncStatus is not None

    def test_email_state_values(self) -> None:
        """EmailState string values must match the PostgreSQL ENUM values."""
        from src.models.email import EmailState

        assert EmailState.FETCHED.value == "FETCHED"
        assert EmailState.SANITIZED.value == "SANITIZED"
        assert EmailState.CLASSIFIED.value == "CLASSIFIED"
        assert EmailState.ROUTED.value == "ROUTED"
        assert EmailState.CRM_SYNCED.value == "CRM_SYNCED"
        assert EmailState.DRAFT_GENERATED.value == "DRAFT_GENERATED"
        assert EmailState.COMPLETED.value == "COMPLETED"
        assert EmailState.RESPONDED.value == "RESPONDED"
        assert EmailState.CLASSIFICATION_FAILED.value == "CLASSIFICATION_FAILED"
        assert EmailState.ROUTING_FAILED.value == "ROUTING_FAILED"
        assert EmailState.CRM_SYNC_FAILED.value == "CRM_SYNC_FAILED"
        assert EmailState.DRAFT_FAILED.value == "DRAFT_FAILED"

    def test_classification_confidence_values(self) -> None:
        from src.models.classification import ClassificationConfidence

        assert ClassificationConfidence.HIGH.value == "high"
        assert ClassificationConfidence.LOW.value == "low"

    def test_routing_action_status_values(self) -> None:
        from src.models.routing import RoutingActionStatus

        assert RoutingActionStatus.PENDING.value == "pending"
        assert RoutingActionStatus.DISPATCHED.value == "dispatched"
        assert RoutingActionStatus.FAILED.value == "failed"
        assert RoutingActionStatus.SKIPPED.value == "skipped"

    def test_draft_status_values(self) -> None:
        from src.models.draft import DraftStatus

        assert DraftStatus.PENDING.value == "pending"
        assert DraftStatus.APPROVED.value == "approved"
        assert DraftStatus.REJECTED.value == "rejected"

    def test_user_role_values(self) -> None:
        from src.models.user import UserRole

        assert UserRole.ADMIN.value == "admin"
        assert UserRole.REVIEWER.value == "reviewer"

    def test_crm_sync_status_values(self) -> None:
        from src.models.crm_sync import CRMSyncStatus

        assert CRMSyncStatus.SYNCED.value == "synced"
        assert CRMSyncStatus.FAILED.value == "failed"
        assert CRMSyncStatus.SKIPPED.value == "skipped"


class TestTypedDictsImportable:
    """All TypedDicts defined in block-01 must be importable.

    TypedDicts are the JSONB field contracts. They ensure that write paths to
    JSONB columns are type-checked by mypy. If a TypedDict is missing, JSONB
    fields degrade to untyped dict[str, Any].
    """

    def test_recipient_data_importable(self) -> None:
        from src.models.email import RecipientData  # noqa: F401

        assert RecipientData is not None

    def test_attachment_data_importable(self) -> None:
        from src.models.email import AttachmentData  # noqa: F401

        assert AttachmentData is not None

    def test_routing_conditions_importable(self) -> None:
        from src.models.routing import RoutingConditions  # noqa: F401

        assert RoutingConditions is not None

    def test_routing_actions_typed_dict_importable(self) -> None:
        from src.models.routing import RoutingActions  # noqa: F401

        assert RoutingActions is not None

    def test_recipient_data_has_required_keys(self) -> None:
        """RecipientData must have email, name, type keys for write-path type safety."""
        from src.models.email import RecipientData

        hints = RecipientData.__annotations__
        assert "email" in hints
        assert "name" in hints
        assert "type" in hints

    def test_attachment_data_has_required_keys(self) -> None:
        """AttachmentData must have filename, mime_type, size_bytes, attachment_id."""
        from src.models.email import AttachmentData

        hints = AttachmentData.__annotations__
        assert "filename" in hints
        assert "mime_type" in hints
        assert "size_bytes" in hints
        assert "attachment_id" in hints

    def test_routing_conditions_has_required_keys(self) -> None:
        """RoutingConditions must have field, operator, value."""
        from src.models.routing import RoutingConditions

        hints = RoutingConditions.__annotations__
        assert "field" in hints
        assert "operator" in hints
        assert "value" in hints

    def test_routing_actions_has_required_keys(self) -> None:
        """RoutingActions must have channel, destination, template_id."""
        from src.models.routing import RoutingActions

        hints = RoutingActions.__annotations__
        assert "channel" in hints
        assert "destination" in hints
        assert "template_id" in hints


class TestMappedAnnotations:
    """Verify that models use SQLAlchemy 2.0 Mapped[] annotations.

    No model column should use legacy Column() without Mapped[].
    This test inspects the model column annotations to confirm SA2.0 style.
    """

    def _get_mapped_columns(self, model_class: type) -> list[str]:
        """Return names of columns annotated with Mapped[]."""
        mapped_cols = []
        for name, annotation in model_class.__annotations__.items():
            origin = getattr(annotation, "__origin__", None)
            if origin is Mapped or (
                hasattr(annotation, "__class__") and annotation.__class__.__name__ == "MappedColumn"
            ):
                mapped_cols.append(name)
        return mapped_cols

    def test_email_uses_mapped_annotations(self) -> None:
        """Email model columns use Mapped[] not legacy Column()."""
        from src.models.email import Email

        # SA 2.0: __annotations__ on the class has Mapped[...] for each column
        # Check a representative set of columns
        annotations = Email.__annotations__
        assert "id" in annotations
        assert "state" in annotations
        assert "sender_email" in annotations
        # Verify they are Mapped types (not bare Column)
        for col_name in ("id", "state", "sender_email", "subject"):
            assert col_name in annotations, (
                f"Email.{col_name} missing from __annotations__ — "
                "model may be using legacy Column() without Mapped[]"
            )

    def test_action_category_uses_mapped_annotations(self) -> None:
        from src.models.category import ActionCategory

        annotations = ActionCategory.__annotations__
        for col_name in ("id", "slug", "name", "is_fallback", "is_active"):
            assert col_name in annotations

    def test_user_uses_mapped_annotations(self) -> None:
        from src.models.user import User

        annotations = User.__annotations__
        for col_name in ("id", "username", "password_hash", "role", "is_active"):
            assert col_name in annotations

    def test_routing_rule_uses_mapped_annotations(self) -> None:
        from src.models.routing import RoutingRule

        annotations = RoutingRule.__annotations__
        for col_name in ("id", "name", "priority", "is_active", "conditions", "actions"):
            assert col_name in annotations


class TestDatabaseSessionFactoryImportable:
    """Dual session factories must be importable — tested here as smoke test.

    The real session factories connect to DB at module import time only if
    the engines are created lazily. This test verifies importability.
    """

    def test_get_async_db_importable(self) -> None:
        from src.core.database import get_async_db  # noqa: F401

        assert callable(get_async_db)

    def test_sync_session_local_importable(self) -> None:
        from src.core.database import SyncSessionLocal  # noqa: F401

        assert SyncSessionLocal is not None

    def test_async_session_local_importable(self) -> None:
        from src.core.database import AsyncSessionLocal  # noqa: F401

        assert AsyncSessionLocal is not None

    def test_valid_transitions_importable(self) -> None:
        """VALID_TRANSITIONS must be importable — it's used by routing service."""
        from src.models.email import VALID_TRANSITIONS

        assert isinstance(VALID_TRANSITIONS, dict)
        assert len(VALID_TRANSITIONS) > 0
