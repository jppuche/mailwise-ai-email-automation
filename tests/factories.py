"""Factory-boy factories for all domain models.

Field names match the actual codebase.
These are plain factory.Factory (not SQLAlchemyModelFactory) — E2E tests insert
via real DB sessions, not factory sessions.

Usage:
    email = EmailFactory()  # Returns an Email ORM object with realistic defaults
    email = EmailFactory(state=EmailState.CLASSIFIED)  # Override specific fields
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import bcrypt
import factory

from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationConfidence, ClassificationResult
from src.models.crm_sync import CRMSyncRecord, CRMSyncStatus
from src.models.draft import Draft, DraftStatus
from src.models.email import Email, EmailState
from src.models.routing import RoutingAction, RoutingActionStatus, RoutingRule
from src.models.user import User, UserRole


class EmailFactory(factory.Factory):
    """Factory for Email ORM model.

    Uses corrected field names: sender_email (not from_address),
    date (not received_at), provider_message_id (not gmail_message_id),
    account as str (not uuid).
    """

    class Meta:
        model = Email

    id = factory.LazyFunction(uuid.uuid4)
    provider_message_id = factory.Sequence(lambda n: f"msg_{n:06d}")
    thread_id = factory.LazyFunction(lambda: f"thread_{uuid.uuid4().hex[:8]}")
    account = factory.Sequence(lambda n: f"account_{n}")
    sender_email = factory.Faker("email")
    sender_name = factory.Faker("name")
    recipients = factory.LazyFunction(
        lambda: [{"email": "recipient@test.com", "name": "Recipient", "type": "to"}]
    )
    subject = factory.Faker("sentence", nb_words=6)
    body_plain = factory.Faker("paragraph", nb_sentences=3)
    body_html = None
    snippet = factory.LazyFunction(lambda: "Email snippet for testing...")
    date = factory.LazyFunction(lambda: datetime.now(UTC))
    attachments = factory.LazyFunction(list)
    provider_labels = factory.LazyFunction(lambda: ["INBOX"])
    state = EmailState.FETCHED
    processed_at = None


class ActionCategoryFactory(factory.Factory):
    """Factory for ActionCategory ORM model."""

    class Meta:
        model = ActionCategory

    id = factory.LazyFunction(uuid.uuid4)
    slug = factory.Sequence(lambda n: f"action_{n}")
    name = factory.Sequence(lambda n: f"Action Category {n}")
    description = factory.LazyFunction(lambda: "Test action category")
    is_fallback = False
    is_active = True
    display_order = factory.Sequence(lambda n: n)


class TypeCategoryFactory(factory.Factory):
    """Factory for TypeCategory ORM model."""

    class Meta:
        model = TypeCategory

    id = factory.LazyFunction(uuid.uuid4)
    slug = factory.Sequence(lambda n: f"type_{n}")
    name = factory.Sequence(lambda n: f"Type Category {n}")
    description = factory.LazyFunction(lambda: "Test type category")
    is_fallback = False
    is_active = True
    display_order = factory.Sequence(lambda n: n)


class ClassificationResultFactory(factory.Factory):
    """Factory for ClassificationResult ORM model.

    confidence is ClassificationConfidence enum (not float).
    category IDs are uuid.UUID (not int).
    """

    class Meta:
        model = ClassificationResult

    id = factory.LazyFunction(uuid.uuid4)
    email_id = factory.LazyFunction(uuid.uuid4)
    action_category_id = factory.LazyFunction(uuid.uuid4)
    type_category_id = factory.LazyFunction(uuid.uuid4)
    confidence = ClassificationConfidence.HIGH
    raw_llm_output = factory.LazyFunction(lambda: {"action": "support", "type": "question"})
    fallback_applied = False
    classified_at = factory.LazyFunction(lambda: datetime.now(UTC))


class RoutingRuleFactory(factory.Factory):
    """Factory for RoutingRule ORM model.

    conditions and actions are JSONB arrays (not separate model fields).
    """

    class Meta:
        model = RoutingRule

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Rule {n}")
    priority = factory.Sequence(lambda n: n * 10)
    is_active = True
    conditions = factory.LazyFunction(
        lambda: [{"field": "action_category", "operator": "eq", "value": "support"}]
    )
    actions = factory.LazyFunction(
        lambda: [{"channel": "slack", "destination": "C_TEST_CHANNEL", "template_id": None}]
    )


class RoutingActionFactory(factory.Factory):
    """Factory for RoutingAction ORM model.

    NO generate_draft/crm_sync fields (don't exist on model).
    """

    class Meta:
        model = RoutingAction

    id = factory.LazyFunction(uuid.uuid4)
    email_id = factory.LazyFunction(uuid.uuid4)
    rule_id = factory.LazyFunction(uuid.uuid4)
    channel = "slack"
    destination = "C_TEST_CHANNEL"
    priority = 0
    status = RoutingActionStatus.PENDING
    dispatch_id = None
    dispatched_at = None
    attempts = 0


class DraftFactory(factory.Factory):
    """Factory for Draft ORM model.

    Uses content (not body) per amendment #10.
    """

    class Meta:
        model = Draft

    id = factory.LazyFunction(uuid.uuid4)
    email_id = factory.LazyFunction(uuid.uuid4)
    content = factory.Faker("paragraphs", nb=2, ext_word_list=None)
    status = DraftStatus.PENDING
    reviewer_id = None
    reviewed_at = None
    pushed_to_provider = False


class UserFactory(factory.Factory):
    """Factory for User ORM model.

    Uses username (not email) per amendment #11.
    Uses bcrypt.hashpw() directly (not passlib) per amendment #12.
    """

    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    username = factory.Sequence(lambda n: f"testuser_{n}_{uuid.uuid4().hex[:6]}")
    password_hash = factory.LazyFunction(
        lambda: bcrypt.hashpw(b"test_password", bcrypt.gensalt()).decode()
    )
    role = UserRole.REVIEWER
    is_active = True


class CRMSyncRecordFactory(factory.Factory):
    """Factory for CRMSyncRecord ORM model."""

    class Meta:
        model = CRMSyncRecord

    id = factory.LazyFunction(uuid.uuid4)
    email_id = factory.LazyFunction(uuid.uuid4)
    contact_id = factory.LazyFunction(lambda: f"contact_{uuid.uuid4().hex[:8]}")
    activity_id = factory.LazyFunction(lambda: f"activity_{uuid.uuid4().hex[:8]}")
    lead_id = None
    status = CRMSyncStatus.SYNCED
    synced_at = factory.LazyFunction(lambda: datetime.now(UTC))
