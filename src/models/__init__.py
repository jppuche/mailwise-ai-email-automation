"""mailwise ORM models.

Import all models here so that:
1. Alembic's env.py only needs to import Base from this module to discover all tables.
2. Application code can use `from src.models import Email, EmailState, ...`.

Import order matters for FK resolution — parent tables must be imported before
child tables, but SQLAlchemy resolves string-based FK references lazily so order
is not strictly required. We preserve logical order for readability.
"""

from src.models.base import Base, TimestampMixin
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationConfidence, ClassificationResult
from src.models.crm_sync import CRMSyncRecord, CRMSyncStatus
from src.models.draft import Draft, DraftStatus
from src.models.email import (
    VALID_TRANSITIONS,
    AttachmentData,
    Email,
    EmailState,
    RecipientData,
)
from src.models.feedback import ClassificationFeedback
from src.models.few_shot import FewShotExample
from src.models.routing import (
    RoutingAction,
    RoutingActions,
    RoutingActionStatus,
    RoutingConditions,
    RoutingRule,
)
from src.models.system_log import SystemLog
from src.models.user import User, UserRole

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    # Email
    "Email",
    "EmailState",
    "VALID_TRANSITIONS",
    "RecipientData",
    "AttachmentData",
    # Categories
    "ActionCategory",
    "TypeCategory",
    # Classification
    "ClassificationResult",
    "ClassificationConfidence",
    # Routing
    "RoutingRule",
    "RoutingAction",
    "RoutingActionStatus",
    "RoutingConditions",
    "RoutingActions",
    # Draft
    "Draft",
    "DraftStatus",
    # User
    "User",
    "UserRole",
    # CRM Sync
    "CRMSyncRecord",
    "CRMSyncStatus",
    # Feedback
    "ClassificationFeedback",
    # Few-shot examples
    "FewShotExample",
    # System logs
    "SystemLog",
]
