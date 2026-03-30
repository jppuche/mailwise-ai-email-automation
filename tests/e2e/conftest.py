"""E2E test fixtures: mock adapters, Celery eager mode, real DB.

Architecture:
  - Celery tasks use asyncio.run() internally, so E2E tests are SYNC functions.
  - Each task is called via task.run(), which bypasses Celery dispatch.
  - The NEXT task's .delay() is patched to prevent nested asyncio.run().
  - DB assertions use asyncio.run() from the sync test context.
  - Mock adapters implement real ABCs (mypy-verified via class inheritance).
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from src.adapters.channel.base import ChannelAdapter
from src.adapters.channel.schemas import (
    ChannelCredentials,
    DeliveryResult,
    Destination,
    RoutingPayload,
)
from src.adapters.channel.schemas import (
    ConnectionStatus as ChannelConnectionStatus,
)
from src.adapters.channel.schemas import (
    ConnectionTestResult as ChannelConnectionTestResult,
)
from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.schemas import (
    ActivityData,
    ActivityId,
    Contact,
    CreateContactData,
    CreateLeadData,
    CRMCredentials,
    LeadId,
)
from src.adapters.crm.schemas import (
    ConnectionStatus as CRMConnectionStatus,
)
from src.adapters.crm.schemas import (
    ConnectionTestResult as CRMConnectionTestResult,
)
from src.adapters.email.base import EmailAdapter
from src.adapters.email.schemas import (
    ConnectionStatus as EmailConnectionStatus,
)
from src.adapters.email.schemas import (
    ConnectionTestResult as EmailConnectionTestResult,
)
from src.adapters.email.schemas import (
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
)
from src.adapters.llm.base import LLMAdapter
from src.adapters.llm.schemas import (
    ClassificationResult as LLMClassificationResult,
)
from src.adapters.llm.schemas import (
    ClassifyOptions,
    DraftOptions,
    DraftText,
    LLMConfig,
)
from src.adapters.llm.schemas import (
    ConnectionTestResult as LLMConnectionTestResult,
)
from src.core.config import get_settings
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationResult as ClassificationResultModel
from src.models.crm_sync import CRMSyncRecord
from src.models.draft import Draft
from src.models.email import Email, EmailState
from src.models.routing import RoutingAction, RoutingRule
from src.tasks.celery_app import celery_app
from tests.factories import (
    ActionCategoryFactory,
    EmailFactory,
    RoutingRuleFactory,
    TypeCategoryFactory,
)

# ---------------------------------------------------------------------------
# Mock adapters implementing real ABCs
# ---------------------------------------------------------------------------


class MockEmailAdapter(EmailAdapter):
    """Mock email adapter implementing the real ABC."""

    def connect(self, credentials: EmailCredentials) -> EmailConnectionStatus:
        return EmailConnectionStatus(
            connected=True, account="test@test.com", scopes=["gmail.readonly"]
        )

    def fetch_new_messages(self, since: datetime, limit: int) -> list[EmailMessage]:
        return []

    def mark_as_processed(self, message_id: str) -> None:
        pass

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        return DraftId("mock_draft_id")

    def get_labels(self) -> list[Label]:
        return [Label(id="INBOX", name="INBOX", type="system")]

    def apply_label(self, message_id: str, label_id: str) -> None:
        pass

    def test_connection(self) -> EmailConnectionTestResult:
        return EmailConnectionTestResult(connected=True, account="test@test.com")


class MockLLMAdapter(LLMAdapter):
    """Mock LLM adapter implementing the real ABC.

    classify() returns a canned result matching DB categories.
    generate_draft() returns realistic draft content.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._action_slug = "support"
        self._type_slug = "question"

    async def classify(
        self,
        prompt: str,
        system_prompt: str,
        options: ClassifyOptions,
    ) -> LLMClassificationResult:
        return LLMClassificationResult(
            action=self._action_slug,
            type=self._type_slug,
            confidence="high",
            raw_llm_output='{"action": "support", "type": "question"}',
            fallback_applied=False,
        )

    async def generate_draft(
        self,
        prompt: str,
        system_prompt: str,
        options: DraftOptions,
    ) -> DraftText:
        return DraftText(
            content="Thank you for your email. We will address your concern shortly.",
            model_used="mock-model",
            fallback_applied=False,
        )

    async def test_connection(self) -> LLMConnectionTestResult:
        return LLMConnectionTestResult(success=True, model_used="mock-model", latency_ms=10)


class MockChannelAdapter(ChannelAdapter):
    """Mock channel adapter implementing the real ABC."""

    def __init__(self) -> None:
        self._connected = True

    async def connect(self, credentials: ChannelCredentials) -> ChannelConnectionStatus:
        self._connected = True
        return ChannelConnectionStatus(
            connected=True, workspace_name="test-workspace", bot_user_id="U_MOCK"
        )

    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,
    ) -> DeliveryResult:
        return DeliveryResult(
            success=True, message_ts="1234567890.123456", channel_id=destination_id
        )

    async def test_connection(self) -> ChannelConnectionTestResult:
        return ChannelConnectionTestResult(
            success=True, workspace_name="test-workspace", latency_ms=5
        )

    async def get_available_destinations(self) -> list[Destination]:
        return [Destination(id="C_TEST_CHANNEL", name="#test-channel", type="channel")]


class MockCRMAdapter(CRMAdapter):
    """Mock CRM adapter implementing the real ABC."""

    def __init__(self) -> None:
        self._connected = True

    async def connect(self, credentials: CRMCredentials) -> CRMConnectionStatus:
        self._connected = True
        return CRMConnectionStatus(connected=True, portal_id="12345", account_name="Test Portal")

    async def lookup_contact(self, email: str) -> Contact | None:
        return Contact(id="contact_001", email=email, first_name="Test", last_name="User")

    async def create_contact(self, data: CreateContactData) -> Contact:
        return Contact(id="contact_new", email=data.email, first_name=data.first_name)

    async def log_activity(self, contact_id: str, activity: ActivityData) -> ActivityId:
        return ActivityId("activity_001")

    async def create_lead(self, data: CreateLeadData) -> LeadId:
        return LeadId("lead_001")

    async def update_field(self, contact_id: str, field: str, value: str) -> None:
        pass

    async def test_connection(self) -> CRMConnectionTestResult:
        return CRMConnectionTestResult(success=True, portal_id="12345", latency_ms=8)


# ---------------------------------------------------------------------------
# Celery eager mode
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def celery_eager_mode() -> Generator[None, None, None]:
    """Enable Celery eager mode for synchronous E2E task execution."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


# ---------------------------------------------------------------------------
# Redis singleton reset
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_redis_singleton() -> Generator[None, None, None]:
    """Reset Redis singleton to avoid event loop mismatch between tests."""
    import src.adapters.redis_client as _redis_mod

    _redis_mod._redis_client = None
    yield
    _redis_mod._redis_client = None


# ---------------------------------------------------------------------------
# DB fixtures — real database, module-scoped migration
# ---------------------------------------------------------------------------


def _get_alembic_config() -> AlembicConfig:
    settings = get_settings()
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url_sync)
    return cfg


@pytest.fixture(scope="module")
def migrated_db() -> Generator[None, None, None]:
    """Apply alembic migrations once per module (upgrade-only)."""
    cfg = _get_alembic_config()
    alembic_command.upgrade(cfg, "head")
    yield


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a NullPool async session factory for E2E tests."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Mock adapter fixtures (with spy capabilities via wrapping)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_email_adapter() -> MockEmailAdapter:
    adapter = MockEmailAdapter()
    adapter.create_draft = MagicMock(wraps=adapter.create_draft)  # type: ignore[method-assign]
    adapter.fetch_new_messages = MagicMock(wraps=adapter.fetch_new_messages)  # type: ignore[method-assign]
    return adapter


@pytest.fixture
def mock_llm_adapter() -> MockLLMAdapter:
    adapter = MockLLMAdapter()
    adapter.classify = AsyncMock(wraps=adapter.classify)  # type: ignore[method-assign]
    adapter.generate_draft = AsyncMock(wraps=adapter.generate_draft)  # type: ignore[method-assign]
    return adapter


@pytest.fixture
def mock_channel_adapter() -> MockChannelAdapter:
    adapter = MockChannelAdapter()
    adapter.send_notification = AsyncMock(wraps=adapter.send_notification)  # type: ignore[method-assign]
    return adapter


@pytest.fixture
def mock_crm_adapter() -> MockCRMAdapter:
    adapter = MockCRMAdapter()
    adapter.lookup_contact = AsyncMock(wraps=adapter.lookup_contact)  # type: ignore[method-assign]
    adapter.log_activity = AsyncMock(wraps=adapter.log_activity)  # type: ignore[method-assign]
    adapter.create_lead = AsyncMock(wraps=adapter.create_lead)  # type: ignore[method-assign]
    return adapter


# ---------------------------------------------------------------------------
# DB helper functions (used from sync test context via asyncio.run())
# ---------------------------------------------------------------------------


async def insert_email(
    session_factory: async_sessionmaker[AsyncSession],
    **overrides: object,
) -> Email:
    """Insert a test email into the DB and return it."""
    email = EmailFactory(**overrides)
    async with session_factory() as session:
        session.add(email)
        await session.commit()
        await session.refresh(email)
    return email


async def insert_categories(
    session_factory: async_sessionmaker[AsyncSession],
    action_slug: str = "support",
    type_slug: str = "question",
) -> tuple[ActionCategory, TypeCategory]:
    """Insert test categories and return them."""
    action_cat = ActionCategoryFactory(slug=action_slug, name=action_slug.title())
    type_cat = TypeCategoryFactory(slug=type_slug, name=type_slug.title())
    async with session_factory() as session:
        # Check if they already exist (idempotent)
        existing_action = await session.execute(
            select(ActionCategory).where(ActionCategory.slug == action_slug)
        )
        if existing_action.scalar_one_or_none() is None:
            session.add(action_cat)
        else:
            action_cat = existing_action.scalar_one_or_none()  # type: ignore[assignment]

        existing_type = await session.execute(
            select(TypeCategory).where(TypeCategory.slug == type_slug)
        )
        if existing_type.scalar_one_or_none() is None:
            session.add(type_cat)
        else:
            type_cat = existing_type.scalar_one_or_none()  # type: ignore[assignment]

        await session.commit()
        if action_cat in session:
            await session.refresh(action_cat)
        if type_cat in session:
            await session.refresh(type_cat)
    return action_cat, type_cat


async def insert_routing_rule(
    session_factory: async_sessionmaker[AsyncSession],
    action_slug: str = "support",
    channel: str = "slack",
    destination: str = "C_TEST_CHANNEL",
) -> RoutingRule:
    """Insert a routing rule that matches the given action category."""
    rule = RoutingRuleFactory(
        conditions=[{"field": "action_category", "operator": "eq", "value": action_slug}],
        actions=[{"channel": channel, "destination": destination, "template_id": None}],
    )
    async with session_factory() as session:
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
    return rule


async def get_email_state(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> EmailState | None:
    """Query current email state from DB."""
    async with session_factory() as session:
        result = await session.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        return email.state if email is not None else None


async def get_classification(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> ClassificationResultModel | None:
    """Query classification result for an email."""
    async with session_factory() as session:
        result = await session.execute(
            select(ClassificationResultModel).where(ClassificationResultModel.email_id == email_id)
        )
        return result.scalar_one_or_none()


async def get_routing_actions(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> list[RoutingAction]:
    """Query routing actions for an email."""
    async with session_factory() as session:
        result = await session.execute(
            select(RoutingAction).where(RoutingAction.email_id == email_id)
        )
        return list(result.scalars().all())


async def get_crm_sync_record(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> CRMSyncRecord | None:
    """Query CRM sync record for an email."""
    async with session_factory() as session:
        result = await session.execute(
            select(CRMSyncRecord).where(CRMSyncRecord.email_id == email_id)
        )
        return result.scalar_one_or_none()


async def get_draft(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> Draft | None:
    """Query draft for an email."""
    async with session_factory() as session:
        result = await session.execute(select(Draft).where(Draft.email_id == email_id))
        return result.scalar_one_or_none()


async def cleanup_email(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> None:
    """Delete test email and all related records (CASCADE handles children)."""
    async with session_factory() as session:
        result = await session.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        if email is not None:
            await session.delete(email)
            await session.commit()
