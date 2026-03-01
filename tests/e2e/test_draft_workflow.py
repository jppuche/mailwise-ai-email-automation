"""E2E tests for draft approve/reject lifecycle.

Architecture:
  - Tests are SYNC functions (not async def) — consistent with E2E suite pattern.
  - DB operations use asyncio.run() from sync context.
  - Draft approve/reject are direct DB-layer tests: mutate Draft.status, commit,
    reload, and assert — mirrors what the API router does without the HTTP layer.
  - Email state is NOT changed by draft approve/reject; only Draft.status changes.

Per B13 spec and draft model:
  - PENDING -> APPROVED: draft.status = DraftStatus.APPROVED
  - PENDING -> REJECTED: draft.status = DraftStatus.REJECTED
  - Email stays in DRAFT_GENERATED state regardless of draft review outcome
    (no DRAFT_REJECTED EmailState exists on the state machine).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.draft import Draft, DraftStatus
from src.models.email import Email, EmailState
from src.models.user import User, UserRole
from tests.e2e.conftest import (
    _make_session_factory,
    cleanup_email,
    get_draft,
    insert_email,
)
from tests.factories import DraftFactory, UserFactory

# ---------------------------------------------------------------------------
# Async helpers for draft-specific DB operations
# ---------------------------------------------------------------------------


async def insert_user(
    session_factory: async_sessionmaker[AsyncSession],
    **overrides: object,
) -> User:
    """Insert a test user into the DB and return it."""
    user = UserFactory(**overrides)
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def insert_draft(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
    **overrides: object,
) -> Draft:
    """Insert a test draft linked to the given email_id."""
    draft = DraftFactory(email_id=email_id, **overrides)
    async with session_factory() as session:
        session.add(draft)
        await session.commit()
        await session.refresh(draft)
    return draft


async def approve_draft_in_db(
    session_factory: async_sessionmaker[AsyncSession],
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> None:
    """Approve a PENDING draft — mirrors the API approve endpoint logic."""
    async with session_factory() as session:
        result = await session.execute(select(Draft).where(Draft.id == draft_id))
        draft = result.scalar_one_or_none()
        if draft is None:
            raise ValueError(f"Draft {draft_id} not found")
        if draft.status != DraftStatus.PENDING:
            raise ValueError(f"Draft {draft_id} cannot be approved from status {draft.status}")
        draft.status = DraftStatus.APPROVED
        draft.reviewer_id = reviewer_id
        draft.reviewed_at = datetime.now(UTC)
        draft.pushed_to_provider = False
        await session.commit()


async def reject_draft_in_db(
    session_factory: async_sessionmaker[AsyncSession],
    draft_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> None:
    """Reject a PENDING draft — mirrors the API reject endpoint logic."""
    async with session_factory() as session:
        result = await session.execute(select(Draft).where(Draft.id == draft_id))
        draft = result.scalar_one_or_none()
        if draft is None:
            raise ValueError(f"Draft {draft_id} not found")
        if draft.status != DraftStatus.PENDING:
            raise ValueError(f"Draft {draft_id} cannot be rejected from status {draft.status}")
        draft.status = DraftStatus.REJECTED
        draft.reviewer_id = reviewer_id
        draft.reviewed_at = datetime.now(UTC)
        await session.commit()


async def cleanup_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Delete a test user by ID."""
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            await session.delete(user)
            await session.commit()


# ---------------------------------------------------------------------------
# Test: approve_draft changes draft.status to APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_approve_draft_changes_status(migrated_db: None) -> None:
    """Approving a PENDING draft sets draft.status = APPROVED.

    Email state remains DRAFT_GENERATED — the review decision does not
    advance the email state machine. That transition (DRAFT_GENERATED ->
    COMPLETED) is a separate pipeline step.

    Alignment: Lawful Good — verifies exact DB state, not just absence of error.
    """
    session_factory = _make_session_factory()

    email = asyncio.run(insert_email(session_factory, state=EmailState.DRAFT_GENERATED))
    reviewer = asyncio.run(insert_user(session_factory, role=UserRole.REVIEWER))
    draft = asyncio.run(
        insert_draft(session_factory, email_id=email.id, status=DraftStatus.PENDING)
    )

    try:
        # Pre-conditions: draft is PENDING, email is DRAFT_GENERATED
        assert draft.status == DraftStatus.PENDING, (
            f"Pre-condition failed: draft status should be PENDING, got {draft.status}"
        )
        assert email.state == EmailState.DRAFT_GENERATED, (
            f"Pre-condition failed: email state should be DRAFT_GENERATED, got {email.state}"
        )

        # Act: approve the draft
        asyncio.run(approve_draft_in_db(session_factory, draft.id, reviewer.id))

        # Assert: draft status is now APPROVED
        refreshed_draft = asyncio.run(get_draft(session_factory, email.id))
        assert refreshed_draft is not None, "Draft not found after approval"
        assert refreshed_draft.status == DraftStatus.APPROVED, (
            f"Expected draft.status=APPROVED after approval, got {refreshed_draft.status}"
        )
        assert refreshed_draft.reviewer_id == reviewer.id, (
            f"Expected reviewer_id={reviewer.id}, got {refreshed_draft.reviewer_id}"
        )
        assert refreshed_draft.reviewed_at is not None, (
            "Expected reviewed_at to be set after approval"
        )
        assert refreshed_draft.pushed_to_provider is False, (
            "Expected pushed_to_provider=False (Gmail push deferred)"
        )

        # Assert: email state is UNCHANGED — no DRAFT_REJECTED state exists
        refreshed_email_state = asyncio.run(_get_email_state_direct(session_factory, email.id))
        assert refreshed_email_state == EmailState.DRAFT_GENERATED, (
            f"Email state must stay DRAFT_GENERATED after draft approval, "
            f"got {refreshed_email_state}"
        )

    finally:
        asyncio.run(cleanup_email(session_factory, email.id))
        asyncio.run(cleanup_user(session_factory, reviewer.id))


# ---------------------------------------------------------------------------
# Test: reject_draft changes draft.status to REJECTED
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_reject_draft_changes_status(migrated_db: None) -> None:
    """Rejecting a PENDING draft sets draft.status = REJECTED.

    Email state remains DRAFT_GENERATED — there is no DRAFT_REJECTED EmailState.
    The rejected draft persists in the DB for audit purposes.

    Alignment: Lawful Good — verifies exact DB state post-rejection.
    """
    session_factory = _make_session_factory()

    email = asyncio.run(insert_email(session_factory, state=EmailState.DRAFT_GENERATED))
    reviewer = asyncio.run(insert_user(session_factory, role=UserRole.REVIEWER))
    draft = asyncio.run(
        insert_draft(session_factory, email_id=email.id, status=DraftStatus.PENDING)
    )

    try:
        # Pre-conditions
        assert draft.status == DraftStatus.PENDING, (
            f"Pre-condition failed: draft status should be PENDING, got {draft.status}"
        )
        assert email.state == EmailState.DRAFT_GENERATED, (
            f"Pre-condition failed: email state should be DRAFT_GENERATED, got {email.state}"
        )

        # Act: reject the draft
        asyncio.run(reject_draft_in_db(session_factory, draft.id, reviewer.id))

        # Assert: draft status is now REJECTED
        refreshed_draft = asyncio.run(get_draft(session_factory, email.id))
        assert refreshed_draft is not None, "Draft not found after rejection"
        assert refreshed_draft.status == DraftStatus.REJECTED, (
            f"Expected draft.status=REJECTED after rejection, got {refreshed_draft.status}"
        )
        assert refreshed_draft.reviewer_id == reviewer.id, (
            f"Expected reviewer_id={reviewer.id}, got {refreshed_draft.reviewer_id}"
        )
        assert refreshed_draft.reviewed_at is not None, (
            "Expected reviewed_at to be set after rejection"
        )

        # Assert: email state is UNCHANGED — rejection does not touch email state machine
        refreshed_email_state = asyncio.run(_get_email_state_direct(session_factory, email.id))
        assert refreshed_email_state == EmailState.DRAFT_GENERATED, (
            f"Email state must stay DRAFT_GENERATED after draft rejection, "
            f"got {refreshed_email_state}"
        )

    finally:
        asyncio.run(cleanup_email(session_factory, email.id))
        asyncio.run(cleanup_user(session_factory, reviewer.id))


# ---------------------------------------------------------------------------
# Private helper — inline email state fetch (avoids conftest coupling)
# ---------------------------------------------------------------------------


async def _get_email_state_direct(
    session_factory: async_sessionmaker[AsyncSession],
    email_id: uuid.UUID,
) -> EmailState | None:
    """Fetch the current email state directly from DB."""
    async with session_factory() as session:
        result = await session.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        return email.state if email is not None else None
