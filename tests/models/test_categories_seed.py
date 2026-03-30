"""Seed data verification tests — requires PostgreSQL with migrations applied.

Documents the canonical seed data for ActionCategory and TypeCategory tables
as defined in FOUNDATION.md Sec 4.2 and 4.3 and block-01-models.md.

These tests verify:
- Exact slugs are present after alembic upgrade head
- Exactly 1 fallback per category type (is_fallback=True)
- The fallback slug matches the spec (unknown / other)
- Category counts match the spec (4 action + 10 type)

Categories in DB are canonical. A typo in a slug here catches a migration
error early, before the classification service tries to resolve slugs to IDs
and silently falls through to the fallback.

All tests in this module require PostgreSQL. They are skipped unless
pytest is invoked with --run-integration.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# ActionCategory seed data constants (spec source of truth)
# ---------------------------------------------------------------------------

EXPECTED_ACTION_SLUGS = {"urgent", "reply_needed", "informational", "unknown"}
EXPECTED_ACTION_FALLBACK_SLUG = "unknown"
EXPECTED_ACTION_COUNT = 4

# ---------------------------------------------------------------------------
# TypeCategory seed data constants (spec source of truth)
# ---------------------------------------------------------------------------

EXPECTED_TYPE_SLUGS = {
    "customer_support",
    "sales_inquiry",
    "billing",
    "technical",
    "partnership",
    "hr_internal",
    "legal_compliance",
    "marketing_promo",
    "spam_automated",
    "other",
}
EXPECTED_TYPE_FALLBACK_SLUG = "other"
EXPECTED_TYPE_COUNT = 10


@pytest.mark.integration
class TestActionCategorySeedData:
    """ActionCategory table must contain exactly 4 canonical seed rows post-migration."""

    @pytest.fixture(autouse=True)
    def _apply_migrations(self, migrated_db: None) -> None:
        """Ensure migrations are applied before any test in this class."""

    def test_action_categories_count(self, db_session: Session) -> None:
        """Exactly 4 ActionCategory rows must be present after upgrade head."""
        from src.models.category import ActionCategory

        result = db_session.execute(select(ActionCategory))
        rows = result.scalars().all()
        assert len(rows) == EXPECTED_ACTION_COUNT, (
            f"Expected {EXPECTED_ACTION_COUNT} ActionCategory rows, "
            f"found {len(rows)}. Seed data in 001_initial_schema.py may be incomplete."
        )

    def test_action_categories_slugs(self, db_session: Session) -> None:
        """Exact slugs must match FOUNDATION.md Sec 4.2."""
        from src.models.category import ActionCategory

        result = db_session.execute(select(ActionCategory.slug))
        actual_slugs = {row[0] for row in result.fetchall()}
        assert actual_slugs == EXPECTED_ACTION_SLUGS, (
            f"ActionCategory slugs mismatch.\n"
            f"Expected: {EXPECTED_ACTION_SLUGS}\n"
            f"Actual:   {actual_slugs}\n"
            f"Missing:  {EXPECTED_ACTION_SLUGS - actual_slugs}\n"
            f"Extra:    {actual_slugs - EXPECTED_ACTION_SLUGS}"
        )

    def test_action_category_single_fallback(self, db_session: Session) -> None:
        """Exactly 1 ActionCategory must have is_fallback=True."""
        from src.models.category import ActionCategory

        result = db_session.execute(
            select(ActionCategory).where(ActionCategory.is_fallback.is_(True))
        )
        fallback_rows = result.scalars().all()
        assert len(fallback_rows) == 1, (
            f"Expected exactly 1 ActionCategory with is_fallback=True, "
            f"found {len(fallback_rows)}: {[r.slug for r in fallback_rows]}"
        )

    def test_action_fallback_slug_is_unknown(self, db_session: Session) -> None:
        """The sole fallback ActionCategory must have slug='unknown'."""
        from src.models.category import ActionCategory

        result = db_session.execute(
            select(ActionCategory).where(ActionCategory.is_fallback.is_(True))
        )
        fallback = result.scalars().first()
        assert fallback is not None
        assert fallback.slug == EXPECTED_ACTION_FALLBACK_SLUG, (
            f"Fallback ActionCategory slug must be '{EXPECTED_ACTION_FALLBACK_SLUG}', "
            f"got '{fallback.slug}'"
        )

    def test_action_categories_all_active(self, db_session: Session) -> None:
        """All seeded ActionCategories must be active (is_active=True) by default."""
        from src.models.category import ActionCategory

        result = db_session.execute(
            select(ActionCategory).where(ActionCategory.is_active.is_(False))
        )
        inactive = result.scalars().all()
        assert len(inactive) == 0, (
            f"Found inactive ActionCategories after seed: {[r.slug for r in inactive]}"
        )

    def test_action_urgent_exists(self, db_session: Session) -> None:
        """'urgent' category must be present — required by the classification service."""
        from src.models.category import ActionCategory

        result = db_session.execute(select(ActionCategory).where(ActionCategory.slug == "urgent"))
        row = result.scalars().first()
        assert row is not None, "ActionCategory 'urgent' not found in seed data"
        assert row.is_fallback is False

    def test_action_reply_needed_exists(self, db_session: Session) -> None:
        from src.models.category import ActionCategory

        result = db_session.execute(
            select(ActionCategory).where(ActionCategory.slug == "reply_needed")
        )
        row = result.scalars().first()
        assert row is not None, "ActionCategory 'reply_needed' not found in seed data"
        assert row.is_fallback is False

    def test_action_informational_exists(self, db_session: Session) -> None:
        from src.models.category import ActionCategory

        result = db_session.execute(
            select(ActionCategory).where(ActionCategory.slug == "informational")
        )
        row = result.scalars().first()
        assert row is not None, "ActionCategory 'informational' not found in seed data"
        assert row.is_fallback is False


@pytest.mark.integration
class TestTypeCategorySeedData:
    """TypeCategory table must contain exactly 10 canonical seed rows post-migration."""

    @pytest.fixture(autouse=True)
    def _apply_migrations(self, migrated_db: None) -> None:
        """Ensure migrations are applied before any test in this class."""

    def test_type_categories_count(self, db_session: Session) -> None:
        """Exactly 10 TypeCategory rows must be present after upgrade head."""
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory))
        rows = result.scalars().all()
        assert len(rows) == EXPECTED_TYPE_COUNT, (
            f"Expected {EXPECTED_TYPE_COUNT} TypeCategory rows, "
            f"found {len(rows)}. Seed data in 001_initial_schema.py may be incomplete."
        )

    def test_type_categories_slugs(self, db_session: Session) -> None:
        """Exact slugs must match FOUNDATION.md Sec 4.3."""
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory.slug))
        actual_slugs = {row[0] for row in result.fetchall()}
        assert actual_slugs == EXPECTED_TYPE_SLUGS, (
            f"TypeCategory slugs mismatch.\n"
            f"Expected: {EXPECTED_TYPE_SLUGS}\n"
            f"Actual:   {actual_slugs}\n"
            f"Missing:  {EXPECTED_TYPE_SLUGS - actual_slugs}\n"
            f"Extra:    {actual_slugs - EXPECTED_TYPE_SLUGS}"
        )

    def test_type_category_single_fallback(self, db_session: Session) -> None:
        """Exactly 1 TypeCategory must have is_fallback=True."""
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory).where(TypeCategory.is_fallback.is_(True)))
        fallback_rows = result.scalars().all()
        assert len(fallback_rows) == 1, (
            f"Expected exactly 1 TypeCategory with is_fallback=True, "
            f"found {len(fallback_rows)}: {[r.slug for r in fallback_rows]}"
        )

    def test_type_fallback_slug_is_other(self, db_session: Session) -> None:
        """The sole fallback TypeCategory must have slug='other'."""
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory).where(TypeCategory.is_fallback.is_(True)))
        fallback = result.scalars().first()
        assert fallback is not None
        assert fallback.slug == EXPECTED_TYPE_FALLBACK_SLUG, (
            f"Fallback TypeCategory slug must be '{EXPECTED_TYPE_FALLBACK_SLUG}', "
            f"got '{fallback.slug}'"
        )

    def test_type_categories_all_active(self, db_session: Session) -> None:
        """All seeded TypeCategories must be active (is_active=True) by default."""
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory).where(TypeCategory.is_active.is_(False)))
        inactive = result.scalars().all()
        assert len(inactive) == 0, (
            f"Found inactive TypeCategories after seed: {[r.slug for r in inactive]}"
        )

    def test_type_customer_support_exists(self, db_session: Session) -> None:
        from src.models.category import TypeCategory

        result = db_session.execute(
            select(TypeCategory).where(TypeCategory.slug == "customer_support")
        )
        row = result.scalars().first()
        assert row is not None, "TypeCategory 'customer_support' not found in seed data"
        assert row.is_fallback is False

    def test_type_spam_automated_exists(self, db_session: Session) -> None:
        from src.models.category import TypeCategory

        result = db_session.execute(
            select(TypeCategory).where(TypeCategory.slug == "spam_automated")
        )
        row = result.scalars().first()
        assert row is not None, "TypeCategory 'spam_automated' not found in seed data"
        assert row.is_fallback is False

    def test_type_billing_exists(self, db_session: Session) -> None:
        from src.models.category import TypeCategory

        result = db_session.execute(select(TypeCategory).where(TypeCategory.slug == "billing"))
        row = result.scalars().first()
        assert row is not None, "TypeCategory 'billing' not found in seed data"

    def test_type_legal_compliance_exists(self, db_session: Session) -> None:
        from src.models.category import TypeCategory

        result = db_session.execute(
            select(TypeCategory).where(TypeCategory.slug == "legal_compliance")
        )
        row = result.scalars().first()
        assert row is not None, "TypeCategory 'legal_compliance' not found in seed data"
