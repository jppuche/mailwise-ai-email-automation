"""Unit tests for GET/POST /api/v1/emails/* endpoints.

Coverage:
  - TestListEmails       — pagination, PII exclusion, empty list, auth
  - TestGetEmail         — detail, 404, classification present/absent
  - TestRetryEmail       — admin-only, 403/404/409, run_pipeline called
  - TestReclassifyEmail  — admin-only, 403/404/409, classify_task.delay called
  - TestGetClassification — 200, 404, fallback_applied mapping
  - TestSubmitFeedback   — 201, 404 for missing email/classification/category

Architecture constraints (D8):
  - Tests use assert conditionals — no try/except for response parsing.
  - Mocks follow B08/B09 pattern: MagicMock for ORM models, AsyncMock for DB.
  - run_pipeline and classify_task patched at import site in the router module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from src.models.email import EmailState

BASE = "/api/v1/emails"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email(
    *,
    state: EmailState = EmailState.CLASSIFIED,
    email_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a minimal mock Email ORM object."""
    email = MagicMock()
    email.id = email_id or uuid.uuid4()
    email.subject = "Test Subject"
    email.sender_email = "sender@example.com"
    email.sender_name = "Sender Name"
    email.date = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    email.state = state
    email.snippet = "Short preview…"
    email.thread_id = "thread-abc"
    email.created_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    email.updated_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    # PII — must NOT appear in list responses
    email.body_plain = "FULL BODY TEXT — PII"
    return email


def _make_classification(*, email_id: uuid.UUID) -> MagicMock:
    """Return a minimal mock ClassificationResult ORM object."""
    clf = MagicMock()
    clf.id = uuid.uuid4()
    clf.email_id = email_id
    clf.action_category_id = uuid.uuid4()
    clf.type_category_id = uuid.uuid4()
    clf.confidence = "high"
    clf.fallback_applied = False
    clf.classified_at = datetime(2024, 6, 1, 12, 5, 0, tzinfo=UTC)
    return clf


def _make_action_cat(*, slug: str = "reply") -> MagicMock:
    cat = MagicMock()
    cat.id = uuid.uuid4()
    cat.slug = slug
    return cat


def _make_type_cat(*, slug: str = "complaint") -> MagicMock:
    cat = MagicMock()
    cat.id = uuid.uuid4()
    cat.slug = slug
    return cat


def _scalar_result(value: object) -> MagicMock:
    """Wrap a value so result.scalar_one_or_none() returns it."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _scalar_one_result(value: object) -> MagicMock:
    """Wrap a value so result.scalar_one() returns it."""
    res = MagicMock()
    res.scalar_one.return_value = value
    return res


def _scalars_all_result(items: list[object]) -> MagicMock:
    """Wrap a list so result.scalars().all() returns it."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = items
    return res


# ---------------------------------------------------------------------------
# TestListEmails
# ---------------------------------------------------------------------------


class TestListEmails:
    """GET /api/v1/emails/ — paginated list."""

    async def test_admin_receives_200_with_items(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin user gets 200 with paginated email list."""
        email = _make_email()

        mock_db.execute.side_effect = [
            _scalar_one_result(1),  # COUNT
            _scalars_all_result([email]),  # paginated emails
            _scalars_all_result([]),  # classifications batch
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["pages"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == str(email.id)

    async def test_reviewer_receives_200(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer role is authorized for list endpoint."""
        email = _make_email()

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([email]),
            _scalars_all_result([]),
        ]

        resp = await reviewer_client.get(f"{BASE}/")
        assert resp.status_code == 200

    async def test_unauthenticated_receives_401(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Unauthenticated requests receive 401."""
        resp = await unauthenticated_client.get(f"{BASE}/")
        assert resp.status_code == 401

    async def test_empty_list_returns_correct_pagination_metadata(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Empty result set: items=[], total=0, pages=0."""
        mock_db.execute.side_effect = [
            _scalar_one_result(0),  # COUNT = 0
            _scalars_all_result([]),  # no emails
        ]

        resp = await admin_client.get(f"{BASE}/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["pages"] == 0

    async def test_response_items_do_not_contain_body_plain(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """body_plain must never appear in list items (PII policy)."""
        email = _make_email()

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([email]),
            _scalars_all_result([]),
        ]

        resp = await admin_client.get(f"{BASE}/")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "body_plain" not in item

    async def test_classification_summary_included_when_present(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """When a ClassificationResult exists, classification summary is populated.

        The router builds dicts keyed by ActionCategory.id / TypeCategory.id.
        So action_cat.id must match clf.action_category_id (and same for type).
        """
        email = _make_email()
        clf = _make_classification(email_id=email.id)

        # Align category IDs so the router's dict lookup finds the right slug.
        action_cat = _make_action_cat(slug="reply")
        action_cat.id = clf.action_category_id

        type_cat = _make_type_cat(slug="complaint")
        type_cat.id = clf.type_category_id

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _scalars_all_result([email]),
            _scalars_all_result([clf]),
            _scalars_all_result([action_cat]),  # ActionCategory batch
            _scalars_all_result([type_cat]),  # TypeCategory batch
        ]

        resp = await admin_client.get(f"{BASE}/")
        assert resp.status_code == 200
        clf_data = resp.json()["items"][0]["classification"]
        assert clf_data is not None
        assert clf_data["action"] == "reply"
        assert clf_data["type"] == "complaint"
        assert clf_data["is_fallback"] is False


# ---------------------------------------------------------------------------
# TestGetEmail
# ---------------------------------------------------------------------------


class TestGetEmail:
    """GET /api/v1/emails/{email_id} — full detail."""

    async def test_returns_200_with_detail(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin receives 200 with complete email detail."""
        email = _make_email()
        email_id = email.id

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email lookup
            _scalar_result(None),  # ClassificationResult (none)
            _scalars_all_result([]),  # RoutingActions
            _scalar_result(None),  # CRMSyncRecord
            _scalar_result(None),  # Draft
        ]

        resp = await admin_client.get(f"{BASE}/{email_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(email_id)
        assert body["subject"] == "Test Subject"
        assert body["sender_email"] == "sender@example.com"
        assert "body_plain" not in body

    async def test_returns_404_for_missing_email(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Missing email returns 404."""
        mock_db.execute.side_effect = [_scalar_result(None)]

        resp = await admin_client.get(f"{BASE}/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    async def test_returns_401_without_auth(
        self,
        unauthenticated_client: AsyncClient,
    ) -> None:
        """Unauthenticated request for detail returns 401."""
        resp = await unauthenticated_client.get(f"{BASE}/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_classification_present_when_available(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """classification field is populated when ClassificationResult exists."""
        email = _make_email()
        clf = _make_classification(email_id=email.id)
        action_cat = _make_action_cat(slug="forward")
        type_cat = _make_type_cat(slug="inquiry")

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email lookup
            _scalar_result(clf),  # ClassificationResult
            _scalar_result(action_cat),  # ActionCategory
            _scalar_result(type_cat),  # TypeCategory
            _scalars_all_result([]),  # RoutingActions
            _scalar_result(None),  # CRMSyncRecord
            _scalar_result(None),  # Draft
        ]

        resp = await reviewer_client.get(f"{BASE}/{email.id}")
        assert resp.status_code == 200
        clf_data = resp.json()["classification"]
        assert clf_data is not None
        assert clf_data["action"] == "forward"
        assert clf_data["type"] == "inquiry"

    async def test_classification_is_none_when_absent(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """classification field is None when no ClassificationResult exists."""
        email = _make_email(state=EmailState.SANITIZED)

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email lookup
            _scalar_result(None),  # ClassificationResult: absent
            _scalars_all_result([]),  # RoutingActions
            _scalar_result(None),  # CRMSyncRecord
            _scalar_result(None),  # Draft
        ]

        resp = await admin_client.get(f"{BASE}/{email.id}")
        assert resp.status_code == 200
        assert resp.json()["classification"] is None


# ---------------------------------------------------------------------------
# TestRetryEmail
# ---------------------------------------------------------------------------


class TestRetryEmail:
    """POST /api/v1/emails/{email_id}/retry — admin-only pipeline re-queue."""

    async def test_admin_can_retry_failed_email(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin retries a CLASSIFICATION_FAILED email — 200 queued=True."""
        email = _make_email(state=EmailState.CLASSIFICATION_FAILED)

        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.run_pipeline") as mock_run:
            resp = await admin_client.post(f"{BASE}/{email.id}/retry", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["email_id"] == str(email.id)
        mock_run.assert_called_once_with(email.id)

    async def test_reviewer_gets_403(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer is not authorized to retry emails — 403."""
        resp = await reviewer_client.post(f"{BASE}/{uuid.uuid4()}/retry", json={})
        assert resp.status_code == 403

    async def test_missing_email_returns_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Retry on nonexistent email returns 404."""
        mock_db.execute.side_effect = [_scalar_result(None)]

        with patch("src.api.routers.emails.run_pipeline"):
            resp = await admin_client.post(f"{BASE}/{uuid.uuid4()}/retry", json={})

        assert resp.status_code == 404

    async def test_non_failed_state_returns_409(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Retry on a non-failed email (e.g. CLASSIFIED) returns 409."""
        email = _make_email(state=EmailState.CLASSIFIED)
        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.run_pipeline"):
            resp = await admin_client.post(f"{BASE}/{email.id}/retry", json={})

        assert resp.status_code == 409
        assert resp.json()["error"] == "invalid_state_transition"

    async def test_run_pipeline_called_with_email_id(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Verify run_pipeline receives the correct email ORM id."""
        email = _make_email(state=EmailState.ROUTING_FAILED)
        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.run_pipeline") as mock_run:
            await admin_client.post(f"{BASE}/{email.id}/retry", json={})

        mock_run.assert_called_once_with(email.id)


# ---------------------------------------------------------------------------
# TestReclassifyEmail
# ---------------------------------------------------------------------------


class TestReclassifyEmail:
    """POST /api/v1/emails/{email_id}/reclassify — admin power operation."""

    async def test_admin_can_reclassify_classified_email(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Admin reclassifies a CLASSIFIED email — 200 queued=True."""
        email = _make_email(state=EmailState.CLASSIFIED)

        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.classify_task") as mock_task:
            resp = await admin_client.post(f"{BASE}/{email.id}/reclassify", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["email_id"] == str(email.id)
        mock_task.delay.assert_called_once_with(str(email.id))

    async def test_reviewer_gets_403(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reviewer is not authorized to reclassify — 403."""
        resp = await reviewer_client.post(f"{BASE}/{uuid.uuid4()}/reclassify", json={})
        assert resp.status_code == 403

    async def test_missing_email_returns_404(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Reclassify nonexistent email returns 404."""
        mock_db.execute.side_effect = [_scalar_result(None)]

        with patch("src.api.routers.emails.classify_task"):
            resp = await admin_client.post(f"{BASE}/{uuid.uuid4()}/reclassify", json={})

        assert resp.status_code == 404

    async def test_fetched_state_returns_409(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """FETCHED is not reclassifiable — returns 409."""
        email = _make_email(state=EmailState.FETCHED)
        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.classify_task"):
            resp = await admin_client.post(f"{BASE}/{email.id}/reclassify", json={})

        assert resp.status_code == 409
        assert resp.json()["error"] == "invalid_state_transition"

    async def test_classify_task_delay_called(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """classify_task.delay receives the email id as string."""
        email = _make_email(state=EmailState.ROUTED)
        mock_db.execute.side_effect = [_scalar_result(email)]

        with patch("src.api.routers.emails.classify_task") as mock_task:
            await admin_client.post(f"{BASE}/{email.id}/reclassify", json={})

        mock_task.delay.assert_called_once_with(str(email.id))


# ---------------------------------------------------------------------------
# TestGetClassification
# ---------------------------------------------------------------------------


class TestGetClassification:
    """GET /api/v1/emails/{email_id}/classification — classification detail."""

    async def test_returns_200_with_classification_detail(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Classification detail endpoint returns 200 with typed fields."""
        email_id = uuid.uuid4()
        clf = _make_classification(email_id=email_id)
        action_cat = _make_action_cat(slug="archive")
        type_cat = _make_type_cat(slug="billing")

        mock_db.execute.side_effect = [
            _scalar_result(clf),  # ClassificationResult
            _scalar_result(action_cat),  # ActionCategory
            _scalar_result(type_cat),  # TypeCategory
        ]

        resp = await admin_client.get(f"{BASE}/{email_id}/classification")

        assert resp.status_code == 200
        body = resp.json()
        assert body["email_id"] == str(email_id)
        assert body["action"] == "archive"
        assert body["type"] == "billing"
        assert body["confidence"] == "high"
        assert "is_fallback" in body

    async def test_returns_404_if_no_classification(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Missing ClassificationResult returns 404."""
        mock_db.execute.side_effect = [_scalar_result(None)]

        resp = await reviewer_client.get(f"{BASE}/{uuid.uuid4()}/classification")

        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    async def test_fallback_applied_maps_to_is_fallback(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """ORM fallback_applied=True surfaces as is_fallback=True in response."""
        email_id = uuid.uuid4()
        clf = _make_classification(email_id=email_id)
        clf.fallback_applied = True
        action_cat = _make_action_cat(slug="reply")
        type_cat = _make_type_cat(slug="inquiry")

        mock_db.execute.side_effect = [
            _scalar_result(clf),
            _scalar_result(action_cat),
            _scalar_result(type_cat),
        ]

        resp = await admin_client.get(f"{BASE}/{email_id}/classification")

        assert resp.status_code == 200
        assert resp.json()["is_fallback"] is True


# ---------------------------------------------------------------------------
# TestSubmitFeedback
# ---------------------------------------------------------------------------


class TestSubmitFeedback:
    """POST /api/v1/emails/{email_id}/classification/feedback — reviewer correction."""

    async def test_returns_201_with_feedback_id(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Valid feedback submission returns 201 with a feedback_id UUID."""
        email = _make_email()
        clf = _make_classification(email_id=email.id)
        corrected_action_cat = _make_action_cat(slug="forward")
        corrected_type_cat = _make_type_cat(slug="inquiry")

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email existence check
            _scalar_result(clf),  # ClassificationResult
            _scalar_result(corrected_action_cat),  # corrected_action slug resolve
            _scalar_result(corrected_type_cat),  # corrected_type slug resolve
        ]

        resp = await reviewer_client.post(
            f"{BASE}/{email.id}/classification/feedback",
            json={"corrected_action": "forward", "corrected_type": "inquiry"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["recorded"] is True
        assert "feedback_id" in body
        # feedback_id must be a valid UUID
        uuid.UUID(body["feedback_id"])

    async def test_returns_404_if_email_does_not_exist(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Feedback on nonexistent email returns 404."""
        mock_db.execute.side_effect = [_scalar_result(None)]

        resp = await reviewer_client.post(
            f"{BASE}/{uuid.uuid4()}/classification/feedback",
            json={"corrected_action": "forward", "corrected_type": "inquiry"},
        )

        assert resp.status_code == 404

    async def test_returns_404_if_classification_does_not_exist(
        self,
        reviewer_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Feedback when no ClassificationResult exists returns 404."""
        email = _make_email()

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email exists
            _scalar_result(None),  # Classification: absent
        ]

        resp = await reviewer_client.post(
            f"{BASE}/{email.id}/classification/feedback",
            json={"corrected_action": "forward", "corrected_type": "inquiry"},
        )

        assert resp.status_code == 404

    async def test_returns_404_for_invalid_action_category_slug(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Unknown corrected_action slug returns 404."""
        email = _make_email()
        clf = _make_classification(email_id=email.id)

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email exists
            _scalar_result(clf),  # Classification exists
            _scalar_result(None),  # corrected_action slug: not found
        ]

        resp = await admin_client.post(
            f"{BASE}/{email.id}/classification/feedback",
            json={"corrected_action": "nonexistent-action", "corrected_type": "inquiry"},
        )

        assert resp.status_code == 404

    async def test_returns_404_for_invalid_type_category_slug(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Unknown corrected_type slug returns 404."""
        email = _make_email()
        clf = _make_classification(email_id=email.id)
        corrected_action_cat = _make_action_cat(slug="reply")

        mock_db.execute.side_effect = [
            _scalar_result(email),  # Email exists
            _scalar_result(clf),  # Classification exists
            _scalar_result(corrected_action_cat),  # corrected_action OK
            _scalar_result(None),  # corrected_type: not found
        ]

        resp = await admin_client.post(
            f"{BASE}/{email.id}/classification/feedback",
            json={"corrected_action": "reply", "corrected_type": "nonexistent-type"},
        )

        assert resp.status_code == 404
