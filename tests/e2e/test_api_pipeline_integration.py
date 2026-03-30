"""E2E API + pipeline integration tests — Block 18.

Verify API endpoints correctly read pipeline-produced data and that
API actions (draft approve/reject) correctly update DB state.

Architecture:
  - Async tests (pytest_asyncio) — API calls via httpx AsyncClient.
  - No Celery tasks — pipeline data pre-populated in DB.
  - get_async_db overridden for E2E test DB.
  - Real auth: users created in DB, logged in via POST /api/v1/auth/login.

Test invariants:
  - Verify response body fields, not just status code.
  - DB state verified directly after mutations.
  - Before/after state checked for mutation endpoints.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.api.main import app
from src.core.config import get_settings
from src.core.database import get_async_db
from src.core.security import hash_password
from src.models.category import ActionCategory, TypeCategory
from src.models.classification import ClassificationConfidence
from src.models.draft import Draft, DraftStatus
from src.models.email import Email, EmailState
from src.models.user import User, UserRole
from tests.factories import (
    ClassificationResultFactory,
    DraftFactory,
    EmailFactory,
)

# ---------------------------------------------------------------------------
# Module-scoped fixtures — DB session, ASGI client, auth
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def api_sf(
    migrated_db: None,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """NullPool async session factory for API integration tests."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    sf: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    yield sf
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def api_client(
    api_sf: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient with get_async_db overridden."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with api_sf() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)


@pytest_asyncio.fixture(scope="module")
async def admin_auth(
    api_sf: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> AsyncGenerator[tuple[User, str], None]:
    """Create admin user + login -> (user, access_token)."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"e2e_api_admin_{suffix}",
        password_hash=hash_password("admin_e2e_pass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    async with api_sf() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    resp = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "admin_e2e_pass"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    yield user, resp.json()["access_token"]

    async with api_sf() as session:
        db_user = await session.get(User, user.id)
        if db_user is not None:
            await session.delete(db_user)
            await session.commit()


@pytest_asyncio.fixture(scope="module")
async def reviewer_auth(
    api_sf: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> AsyncGenerator[tuple[User, str], None]:
    """Create reviewer user + login -> (user, access_token)."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"e2e_api_reviewer_{suffix}",
        password_hash=hash_password("reviewer_e2e_pass"),
        role=UserRole.REVIEWER,
        is_active=True,
    )
    async with api_sf() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    resp = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "reviewer_e2e_pass"},
    )
    assert resp.status_code == 200, f"Reviewer login failed: {resp.text}"
    yield user, resp.json()["access_token"]

    async with api_sf() as session:
        db_user = await session.get(User, user.id)
        if db_user is not None:
            await session.delete(db_user)
            await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_categories(
    sf: async_sessionmaker[AsyncSession],
    action_slug: str = "support",
    type_slug: str = "question",
) -> tuple[ActionCategory, TypeCategory]:
    """Idempotent category insert — returns existing or new."""
    async with sf() as session:
        ar = await session.execute(select(ActionCategory).where(ActionCategory.slug == action_slug))
        action_cat = ar.scalar_one_or_none()
        if action_cat is None:
            action_cat = ActionCategory(
                slug=action_slug,
                name=action_slug.title(),
                description="E2E",
                is_fallback=False,
                is_active=True,
                display_order=0,
            )
            session.add(action_cat)

        tr = await session.execute(select(TypeCategory).where(TypeCategory.slug == type_slug))
        type_cat = tr.scalar_one_or_none()
        if type_cat is None:
            type_cat = TypeCategory(
                slug=type_slug,
                name=type_slug.title(),
                description="E2E",
                is_fallback=False,
                is_active=True,
                display_order=0,
            )
            session.add(type_cat)

        await session.commit()
        if action_cat in session:
            await session.refresh(action_cat)
        if type_cat in session:
            await session.refresh(type_cat)
    return action_cat, type_cat


async def _cleanup_email(sf: async_sessionmaker[AsyncSession], email_id: uuid.UUID) -> None:
    """Delete email + cascaded children."""
    async with sf() as session:
        result = await session.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        if email is not None:
            await session.delete(email)
            await session.commit()


# ---------------------------------------------------------------------------
# Test 1: GET /emails/{id} includes classification data
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_get_email_detail_includes_classification(
    api_client: AsyncClient,
    admin_auth: tuple[User, str],
    api_sf: async_sessionmaker[AsyncSession],
) -> None:
    """GET /emails/{id} returns email with classification after pipeline.

    Preconditions:
      - Email in CLASSIFIED state with ClassificationResult in DB.
      - Categories "support" / "question" exist.

    Postconditions (response body):
      - status 200
      - state == "CLASSIFIED"
      - classification.action == "support"
      - classification.type == "question"
      - classification.confidence == "high"
      - classification.is_fallback == false
    """
    _, token = admin_auth
    action_cat, type_cat = await _ensure_categories(api_sf)

    email = EmailFactory(state=EmailState.CLASSIFIED)
    cr = ClassificationResultFactory(
        email_id=email.id,
        action_category_id=action_cat.id,
        type_category_id=type_cat.id,
        confidence=ClassificationConfidence.HIGH,
        fallback_applied=False,
    )
    async with api_sf() as session:
        session.add(email)
        session.add(cr)
        await session.commit()

    try:
        resp = await api_client.get(
            f"/api/v1/emails/{email.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify email identity and state
        assert data["id"] == str(email.id)
        assert data["state"] == "CLASSIFIED", f"Expected state 'CLASSIFIED', got {data['state']}"

        # Verify classification object in response body
        cls = data.get("classification")
        assert cls is not None, "classification must be present in response"
        assert cls["action"] == "support"
        assert cls["type"] == "question"
        assert cls["confidence"] == "high"
        assert cls["is_fallback"] is False

    finally:
        await _cleanup_email(api_sf, email.id)


# ---------------------------------------------------------------------------
# Test 2: GET /emails/?state=CLASSIFIED filters correctly
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_get_email_list_filters_by_state(
    api_client: AsyncClient,
    admin_auth: tuple[User, str],
    api_sf: async_sessionmaker[AsyncSession],
) -> None:
    """GET /emails/?state=CLASSIFIED returns only CLASSIFIED emails.

    Preconditions:
      - Two emails inserted: one CLASSIFIED, one FETCHED.

    Postconditions (response body):
      - status 200
      - Only CLASSIFIED email appears in items
      - total >= 1 (may include other CLASSIFIED emails in DB)
      - All returned items have state == "CLASSIFIED"
    """
    _, token = admin_auth

    email_classified = EmailFactory(state=EmailState.CLASSIFIED)
    email_fetched = EmailFactory(state=EmailState.FETCHED)

    async with api_sf() as session:
        session.add(email_classified)
        session.add(email_fetched)
        await session.commit()

    try:
        resp = await api_client.get(
            "/api/v1/emails/",
            params={"state": "CLASSIFIED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert data["total"] >= 1, "Expected at least 1 CLASSIFIED email"

        # Our CLASSIFIED email must appear in the results
        item_ids = [item["id"] for item in data["items"]]
        assert str(email_classified.id) in item_ids, (
            f"CLASSIFIED email {email_classified.id} not found in response items"
        )

        # FETCHED email must NOT appear in the results
        assert str(email_fetched.id) not in item_ids, (
            f"FETCHED email {email_fetched.id} should not appear in CLASSIFIED filter"
        )

        # All returned items must have CLASSIFIED state
        for item in data["items"]:
            assert item["state"] == "CLASSIFIED", (
                f"Expected all items state='CLASSIFIED', got {item['state']}"
            )

    finally:
        await _cleanup_email(api_sf, email_classified.id)
        await _cleanup_email(api_sf, email_fetched.id)


# ---------------------------------------------------------------------------
# Test 3: POST /drafts/{id}/approve via API
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_approve_draft_via_api_endpoint(
    api_client: AsyncClient,
    admin_auth: tuple[User, str],
    api_sf: async_sessionmaker[AsyncSession],
) -> None:
    """POST /drafts/{id}/approve returns 200 and updates DB state.

    Preconditions:
      - Email in DRAFT_GENERATED state.
      - Draft with status PENDING linked to email.
      - Admin auth (can access any draft).

    Postconditions:
      - Response status 200 with approved=true.
      - DB: draft.status == APPROVED.
      - DB: draft.reviewer_id == admin user id.
      - DB: email state unchanged (still DRAFT_GENERATED).
    """
    admin_user, token = admin_auth

    email = EmailFactory(state=EmailState.DRAFT_GENERATED)
    draft = DraftFactory(
        email_id=email.id,
        content="Draft reply for approval test.",
        status=DraftStatus.PENDING,
        reviewer_id=None,
    )

    async with api_sf() as session:
        session.add(email)
        session.add(draft)
        await session.commit()

    try:
        # Pre-condition: verify draft is PENDING
        async with api_sf() as session:
            db_draft = await session.get(Draft, draft.id)
            assert db_draft is not None, "Draft not found in DB"
            assert db_draft.status == DraftStatus.PENDING

        # Act: approve the draft
        resp = await api_client.post(
            f"/api/v1/drafts/{draft.id}/approve",
            json={"push_to_gmail": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Assert: response body
        assert data["draft_id"] == str(draft.id)
        assert data["approved"] is True
        assert data["approved_at"] is not None

        # Assert: DB state — draft is APPROVED
        async with api_sf() as session:
            db_draft = await session.get(Draft, draft.id)
            assert db_draft is not None, "Draft not found after approval"
            assert db_draft.status == DraftStatus.APPROVED, (
                f"Expected draft status APPROVED, got {db_draft.status}"
            )
            assert db_draft.reviewer_id == admin_user.id, (
                f"Expected reviewer_id={admin_user.id}, got {db_draft.reviewer_id}"
            )
            assert db_draft.reviewed_at is not None

        # Assert: email state unchanged
        async with api_sf() as session:
            db_email = await session.get(Email, email.id)
            assert db_email is not None
            assert db_email.state == EmailState.DRAFT_GENERATED, (
                f"Email state must stay DRAFT_GENERATED, got {db_email.state}"
            )

    finally:
        await _cleanup_email(api_sf, email.id)


# ---------------------------------------------------------------------------
# Test 4: POST /drafts/{id}/reject via API (reviewer)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_reject_draft_via_api_endpoint(
    api_client: AsyncClient,
    reviewer_auth: tuple[User, str],
    api_sf: async_sessionmaker[AsyncSession],
) -> None:
    """POST /drafts/{id}/reject returns 204 and updates DB state.

    Preconditions:
      - Email in DRAFT_GENERATED state.
      - Draft with status PENDING, reviewer_id == reviewer (for access control).
      - Reviewer auth.

    Postconditions:
      - Response status 204 (No Content).
      - DB: draft.status == REJECTED.
      - DB: draft.reviewer_id == reviewer user id.
      - DB: email state unchanged (still DRAFT_GENERATED).
    """
    reviewer_user, token = reviewer_auth

    email = EmailFactory(state=EmailState.DRAFT_GENERATED)
    draft = DraftFactory(
        email_id=email.id,
        content="Draft reply for rejection test.",
        status=DraftStatus.PENDING,
        reviewer_id=reviewer_user.id,  # Reviewer must own the draft for access
    )

    async with api_sf() as session:
        session.add(email)
        session.add(draft)
        await session.commit()

    try:
        # Pre-condition: verify draft is PENDING
        async with api_sf() as session:
            db_draft = await session.get(Draft, draft.id)
            assert db_draft is not None, "Draft not found in DB"
            assert db_draft.status == DraftStatus.PENDING

        # Act: reject the draft
        resp = await api_client.post(
            f"/api/v1/drafts/{draft.id}/reject",
            json={"reason": "Not suitable for this recipient."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204, f"Expected 204, got {resp.status_code}: {resp.text}"

        # Assert: DB state — draft is REJECTED
        async with api_sf() as session:
            db_draft = await session.get(Draft, draft.id)
            assert db_draft is not None, "Draft not found after rejection"
            assert db_draft.status == DraftStatus.REJECTED, (
                f"Expected draft status REJECTED, got {db_draft.status}"
            )
            assert db_draft.reviewer_id == reviewer_user.id, (
                f"Expected reviewer_id={reviewer_user.id}, got {db_draft.reviewer_id}"
            )
            assert db_draft.reviewed_at is not None

        # Assert: email state unchanged
        async with api_sf() as session:
            db_email = await session.get(Email, email.id)
            assert db_email is not None
            assert db_email.state == EmailState.DRAFT_GENERATED, (
                f"Email state must stay DRAFT_GENERATED, got {db_email.state}"
            )

    finally:
        await _cleanup_email(api_sf, email.id)
