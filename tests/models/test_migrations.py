"""Migration lifecycle tests — requires PostgreSQL.

Tests the complete Alembic migration lifecycle:
- upgrade head creates all 10 tables
- downgrade base removes all tables and enum types cleanly
- upgrade head is idempotent (second run does not fail)
- FK enforcement works at DB level (not just ORM level)

These tests are the integration gate for block-01. They use the Alembic API
directly to run migrations — the same codepath as env.py — avoiding subprocess
deadlocks with the test engine's connection pool on Windows/PostgreSQL.

All tests require PostgreSQL. Skipped unless --run-integration is passed.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from alembic import command as alembic_command

# Expected tables after alembic upgrade head
EXPECTED_TABLES = {
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
    # Alembic internal tables
    "alembic_version",
}

# Expected PostgreSQL ENUM type names created by migrations
EXPECTED_ENUM_TYPES = {
    "emailstate",
    "classificationconfidence",
    "routingactionstatus",
    "draftstatus",
    "userrole",
    "crmsyncstatus",
}


@pytest.mark.integration
class TestMigrationUpgrade:
    """alembic upgrade head creates the complete schema."""

    @pytest.fixture(autouse=True)
    def _apply_migrations(self, migrated_db: None) -> None:
        """Apply migrations once for all tests in this class."""

    def test_upgrade_creates_all_tables(self, sync_engine: Engine) -> None:
        """upgrade head creates all 10 domain tables plus alembic_version."""
        inspector = inspect(sync_engine)
        actual_tables = set(inspector.get_table_names())
        domain_tables = EXPECTED_TABLES - {"alembic_version"}
        missing = domain_tables - actual_tables
        assert not missing, (
            f"Tables missing after alembic upgrade head: {missing}\nActual tables: {actual_tables}"
        )

    def test_upgrade_creates_emails_table(self, sync_engine: Engine) -> None:
        inspector = inspect(sync_engine)
        assert "emails" in inspector.get_table_names()

    def test_upgrade_creates_category_tables(self, sync_engine: Engine) -> None:
        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()
        assert "action_categories" in tables
        assert "type_categories" in tables

    def test_upgrade_creates_alembic_version_table(self, sync_engine: Engine) -> None:
        """alembic_version must exist so subsequent upgrades are idempotent."""
        inspector = inspect(sync_engine)
        assert "alembic_version" in inspector.get_table_names()

    def test_upgrade_creates_email_state_enum(self, sync_engine: Engine) -> None:
        """EmailState column must be a PostgreSQL ENUM, not VARCHAR.

        DB-level ENUM prevents invalid state values even when Python validation
        is bypassed.
        """
        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'emails' AND column_name = 'state'"
                )
            )
            row = result.fetchone()
        assert row is not None, "emails.state column not found"
        # PostgreSQL reports custom ENUMs as USER-DEFINED
        assert row[0].upper() == "USER-DEFINED", (
            f"emails.state is '{row[0]}', expected USER-DEFINED (PostgreSQL ENUM). "
            "The column may have been created as VARCHAR — check the Alembic migration."
        )

    def test_upgrade_creates_emails_indices(self, sync_engine: Engine) -> None:
        """Composite indices on emails table must be created."""
        inspector = inspect(sync_engine)
        indices = {idx["name"] for idx in inspector.get_indexes("emails")}
        assert "ix_emails_state_date" in indices, (
            "Composite index ix_emails_state_date missing — "
            "email queries by state+date will be slow"
        )
        assert "ix_emails_account_state" in indices, (
            "Composite index ix_emails_account_state missing — "
            "per-account state queries will be slow"
        )

    def test_upgrade_emails_has_provider_message_id_unique(self, sync_engine: Engine) -> None:
        """provider_message_id must have a unique constraint for deduplication."""
        inspector = inspect(sync_engine)
        indices = inspector.get_indexes("emails")
        unique_cols = []
        for idx in indices:
            if idx.get("unique"):
                unique_cols.extend(idx["column_names"])
        assert "provider_message_id" in unique_cols, (
            "emails.provider_message_id unique constraint missing. "
            "Without it, duplicate ingestion cannot be detected at DB level."
        )

    def test_upgrade_creates_classification_results_fk(self, sync_engine: Engine) -> None:
        """classification_results must have FK to emails, action_categories, type_categories."""
        inspector = inspect(sync_engine)
        fks = inspector.get_foreign_keys("classification_results")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "emails" in referred_tables
        assert "action_categories" in referred_tables
        assert "type_categories" in referred_tables

    def test_upgrade_creates_routing_actions_fk_to_emails(self, sync_engine: Engine) -> None:
        inspector = inspect(sync_engine)
        fks = inspector.get_foreign_keys("routing_actions")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "emails" in referred_tables

    def test_upgrade_creates_drafts_fk_to_users(self, sync_engine: Engine) -> None:
        """drafts.reviewer_id must reference users.id (nullable FK)."""
        inspector = inspect(sync_engine)
        fks = inspector.get_foreign_keys("drafts")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "users" in referred_tables

    def test_upgrade_creates_feedback_fks(self, sync_engine: Engine) -> None:
        """classification_feedback must FK to emails, action_categories, type_categories, users."""
        inspector = inspect(sync_engine)
        fks = inspector.get_foreign_keys("classification_feedback")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "emails" in referred_tables
        assert "action_categories" in referred_tables
        assert "type_categories" in referred_tables
        assert "users" in referred_tables


@pytest.mark.integration
class TestMigrationIdempotent:
    """alembic upgrade head run twice must not fail."""

    def test_upgrade_idempotent(self) -> None:
        """Running upgrade head twice is safe — second run is a no-op."""
        from tests.models.conftest import _get_alembic_config

        cfg = _get_alembic_config()
        # First upgrade
        alembic_command.upgrade(cfg, "head")
        # Second upgrade — must not raise
        alembic_command.upgrade(cfg, "head")


@pytest.mark.integration
class TestMigrationDowngrade:
    """alembic downgrade base removes all tables and enum types cleanly."""

    def test_downgrade_removes_all_domain_tables(self, sync_engine: Engine) -> None:
        """After downgrade base, no domain tables remain."""
        from tests.models.conftest import _get_alembic_config

        cfg = _get_alembic_config()
        alembic_command.upgrade(cfg, "head")
        sync_engine.dispose()
        alembic_command.downgrade(cfg, "base")

        # Reconnect after dispose to inspect
        inspector = inspect(sync_engine)
        actual_tables = set(inspector.get_table_names())
        domain_tables = EXPECTED_TABLES - {"alembic_version"}
        remaining = domain_tables & actual_tables
        assert not remaining, (
            f"Tables still present after alembic downgrade base: {remaining}\n"
            "The migration downgrade path is incomplete."
        )
        # Restore schema for subsequent tests
        alembic_command.upgrade(cfg, "head")

    def test_downgrade_removes_email_state_enum(self, sync_engine: Engine) -> None:
        """The emailstate PostgreSQL ENUM type must be dropped on downgrade.

        If the enum type is not dropped, a subsequent upgrade will fail with
        'type already exists'. This validates the downgrade order: tables
        must be dropped BEFORE their enum types.
        """
        from tests.models.conftest import _get_alembic_config

        cfg = _get_alembic_config()
        alembic_command.upgrade(cfg, "head")
        sync_engine.dispose()
        alembic_command.downgrade(cfg, "base")

        with sync_engine.connect() as conn:
            result = conn.execute(
                text("SELECT typname FROM pg_type WHERE typname = 'emailstate' AND typtype = 'e'")
            )
            row = result.fetchone()
        assert row is None, (
            "PostgreSQL ENUM 'emailstate' still exists after downgrade base. "
            "Downgrade must drop enum types after dropping dependent tables."
        )
        # Restore schema for subsequent tests
        alembic_command.upgrade(cfg, "head")

    def test_upgrade_after_downgrade_succeeds(self) -> None:
        """A full down/up cycle must succeed — validates complete migration roundtrip."""
        from tests.models.conftest import _get_alembic_config

        cfg = _get_alembic_config()
        alembic_command.upgrade(cfg, "head")
        alembic_command.downgrade(cfg, "base")
        # This will fail if enums or tables were not fully cleaned up
        alembic_command.upgrade(cfg, "head")


@pytest.mark.integration
class TestForeignKeyEnforcement:
    """FK constraints must be enforced at DB level, not just ORM level.

    Even if Python code bypasses ORM validation, the DB must reject invalid
    category IDs. This is the architectural guarantee that prevents corrupted
    classification results.
    """

    @pytest.fixture(autouse=True)
    def _apply_migrations(self, migrated_db: None) -> None:
        """Ensure migrations are applied before FK enforcement tests."""

    def test_classification_result_rejects_invalid_action_category_id(
        self, sync_engine: Engine
    ) -> None:
        """Inserting ClassificationResult with non-existent FK raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        fake_email_id = str(uuid.uuid4())
        fake_action_id = str(uuid.uuid4())
        fake_type_id = str(uuid.uuid4())

        with sync_engine.connect() as conn:
            # First we need a real email row to satisfy the email FK
            conn.execute(
                text(
                    "INSERT INTO emails "
                    "(id, provider_message_id, account, sender_email, subject, "
                    "date, recipients, attachments, provider_labels, state) "
                    "VALUES (:id, :msg_id, :account, :sender, :subject, "
                    "NOW(), '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'FETCHED')"
                ),
                {
                    "id": fake_email_id,
                    "msg_id": f"test-{fake_email_id}",
                    "account": "test@example.com",
                    "sender": "sender@example.com",
                    "subject": "Test",
                },
            )
            conn.commit()

            # Now attempt to insert ClassificationResult with invalid category IDs
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO classification_results "
                        "(id, email_id, action_category_id, type_category_id, "
                        "confidence, raw_llm_output, fallback_applied) "
                        "VALUES (:id, :email_id, :action_id, :type_id, "
                        "'high', '{}'::jsonb, false)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "email_id": fake_email_id,
                        "action_id": fake_action_id,  # Does not exist
                        "type_id": fake_type_id,  # Does not exist
                    },
                )
            # Rollback the failed transaction before cleanup
            conn.rollback()
            conn.execute(
                text("DELETE FROM emails WHERE id = :id"),
                {"id": fake_email_id},
            )
            conn.commit()

    def test_emails_provider_message_id_unique_constraint(self, sync_engine: Engine) -> None:
        """Inserting two emails with the same provider_message_id raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        duplicate_msg_id = f"duplicate-{uuid.uuid4()}"
        email_id_1 = str(uuid.uuid4())
        email_id_2 = str(uuid.uuid4())

        insert_sql = text(
            "INSERT INTO emails "
            "(id, provider_message_id, account, sender_email, subject, "
            "date, recipients, attachments, provider_labels, state) "
            "VALUES (:id, :msg_id, :account, :sender, :subject, "
            "NOW(), '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'FETCHED')"
        )

        with sync_engine.connect() as conn:
            conn.execute(
                insert_sql,
                {
                    "id": email_id_1,
                    "msg_id": duplicate_msg_id,
                    "account": "test@example.com",
                    "sender": "sender@example.com",
                    "subject": "First",
                },
            )
            conn.commit()

            with pytest.raises(IntegrityError):
                conn.execute(
                    insert_sql,
                    {
                        "id": email_id_2,
                        "msg_id": duplicate_msg_id,  # Duplicate!
                        "account": "test@example.com",
                        "sender": "sender@example.com",
                        "subject": "Duplicate",
                    },
                )
            # Rollback the failed transaction before cleanup
            conn.rollback()
            conn.execute(
                text("DELETE FROM emails WHERE provider_message_id = :msg_id"),
                {"msg_id": duplicate_msg_id},
            )
            conn.commit()
