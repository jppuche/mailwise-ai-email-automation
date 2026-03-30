"""Initial schema — all tables, enums, indices, and seed data.

Revision ID: 001
Revises: None
Create Date: 2026-02-20

Creates:
  - PostgreSQL ENUM types: emailstate, classificationconfidence,
    routingactionstatus, draftstatus, userrole, crmsyncstatus
  - Tables (10): users, action_categories, type_categories, emails,
    classification_results, routing_rules, routing_actions, drafts,
    crm_sync_records, classification_feedback
  - Indices: state, thread_id, account, composite (state+date, account+state),
    email_id FKs, priority
  - Seed data: 4 ActionCategory rows, 10 TypeCategory rows

Downgrade order: drop tables in FK-dependency reverse order, then drop enums.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Tables (order: no-FK tables first, then FK-dependent tables)
    #
    # ENUM types are created inline via create_type=True (default).
    # Each enum is referenced by exactly one table, so no duplication.
    # ------------------------------------------------------------------

    # users — no FK dependencies
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "reviewer", name="userrole", create_type=True),
            nullable=False,
            server_default="reviewer",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # action_categories — no FK dependencies
    op.create_table(
        "action_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_fallback", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_action_categories_slug"),
    )

    # type_categories — no FK dependencies
    op.create_table(
        "type_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_fallback", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_type_categories_slug"),
    )

    # emails — no FK dependencies (state enum references emailstate)
    op.create_table(
        "emails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("account", sa.String(255), nullable=False),
        sa.Column("sender_email", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("recipients", JSONB, nullable=False, server_default="[]"),
        sa.Column("subject", sa.Text, nullable=False, server_default=""),
        sa.Column("body_plain", sa.Text, nullable=True),
        sa.Column("body_html", sa.Text, nullable=True),
        sa.Column("snippet", sa.String(500), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attachments", JSONB, nullable=False, server_default="[]"),
        sa.Column("provider_labels", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "state",
            sa.Enum(
                "FETCHED",
                "SANITIZED",
                "CLASSIFIED",
                "ROUTED",
                "CRM_SYNCED",
                "DRAFT_GENERATED",
                "COMPLETED",
                "RESPONDED",
                "CLASSIFICATION_FAILED",
                "ROUTING_FAILED",
                "CRM_SYNC_FAILED",
                "DRAFT_FAILED",
                name="emailstate",
                create_type=True,
            ),
            nullable=False,
            server_default="FETCHED",
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("provider_message_id", name="uq_emails_provider_message_id"),
    )
    op.create_index("ix_emails_thread_id", "emails", ["thread_id"])
    op.create_index("ix_emails_account", "emails", ["account"])
    op.create_index("ix_emails_state", "emails", ["state"])
    op.create_index("ix_emails_state_date", "emails", ["state", "date"])
    op.create_index("ix_emails_account_state", "emails", ["account", "state"])

    # routing_rules — no FK dependencies
    op.create_table(
        "routing_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("actions", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_routing_rules_priority", "routing_rules", ["priority"])

    # classification_results — FKs: emails, action_categories, type_categories
    op.create_table(
        "classification_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_category_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type_category_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "confidence",
            sa.Enum("high", "low", name="classificationconfidence", create_type=True),
            nullable=False,
        ),
        sa.Column("raw_llm_output", JSONB, nullable=False),
        sa.Column("fallback_applied", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["emails.id"], ondelete="CASCADE", name="fk_classification_results_email"
        ),
        sa.ForeignKeyConstraint(
            ["action_category_id"],
            ["action_categories.id"],
            name="fk_classification_results_action_category",
        ),
        sa.ForeignKeyConstraint(
            ["type_category_id"],
            ["type_categories.id"],
            name="fk_classification_results_type_category",
        ),
    )
    op.create_index("ix_classification_results_email_id", "classification_results", ["email_id"])

    # routing_actions — FKs: emails, routing_rules
    op.create_table(
        "routing_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "dispatched",
                "failed",
                "skipped",
                name="routingactionstatus",
                create_type=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("dispatch_id", sa.String(255), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["emails.id"], ondelete="CASCADE", name="fk_routing_actions_email"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["routing_rules.id"],
            ondelete="SET NULL",
            name="fk_routing_actions_rule",
        ),
    )
    op.create_index("ix_routing_actions_email_id", "routing_actions", ["email_id"])

    # drafts — FKs: emails, users
    op.create_table(
        "drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="draftstatus", create_type=True),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "pushed_to_provider", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["emails.id"], ondelete="CASCADE", name="fk_drafts_email"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], ondelete="SET NULL", name="fk_drafts_reviewer"
        ),
    )
    op.create_index("ix_drafts_email_id", "drafts", ["email_id"])

    # crm_sync_records — FK: emails
    op.create_table(
        "crm_sync_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.String(255), nullable=True),
        sa.Column("activity_id", sa.String(255), nullable=True),
        sa.Column("lead_id", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("synced", "failed", "skipped", name="crmsyncstatus", create_type=True),
            nullable=False,
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["emails.id"], ondelete="CASCADE", name="fk_crm_sync_records_email"
        ),
    )
    op.create_index("ix_crm_sync_records_email_id", "crm_sync_records", ["email_id"])

    # classification_feedback — FKs: emails, action_categories (x2), type_categories (x2), users
    op.create_table(
        "classification_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_type_id", UUID(as_uuid=True), nullable=False),
        sa.Column("corrected_action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("corrected_type_id", UUID(as_uuid=True), nullable=False),
        sa.Column("corrected_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "corrected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["emails.id"],
            ondelete="CASCADE",
            name="fk_classification_feedback_email",
        ),
        sa.ForeignKeyConstraint(
            ["original_action_id"],
            ["action_categories.id"],
            name="fk_classification_feedback_original_action",
        ),
        sa.ForeignKeyConstraint(
            ["original_type_id"],
            ["type_categories.id"],
            name="fk_classification_feedback_original_type",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_action_id"],
            ["action_categories.id"],
            name="fk_classification_feedback_corrected_action",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_type_id"],
            ["type_categories.id"],
            name="fk_classification_feedback_corrected_type",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_by"],
            ["users.id"],
            name="fk_classification_feedback_corrected_by",
        ),
    )
    op.create_index("ix_classification_feedback_email_id", "classification_feedback", ["email_id"])

    # ------------------------------------------------------------------
    # 3. Seed data (FOUNDATION.md Sec 4.2 and 4.3)
    # ------------------------------------------------------------------

    action_categories_table = sa.table(
        "action_categories",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_fallback", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("display_order", sa.Integer),
    )

    op.bulk_insert(
        action_categories_table,
        [
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "slug": "urgent",
                "name": "Urgent — Requires Immediate Attention",
                "description": "Email requires immediate action or response.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 1,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
                "slug": "reply_needed",
                "name": "Reply Needed — Standard Response Required",
                "description": "Email requires a response but is not urgent.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 2,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
                "slug": "informational",
                "name": "Informational — No Action Required",
                "description": "Email is informational and requires no action.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 3,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
                "slug": "unknown",
                "name": "Unknown — Fallback Category",
                "description": "Classification could not be determined. Used as fallback.",
                "is_fallback": True,
                "is_active": True,
                "display_order": 99,
            },
        ],
    )

    type_categories_table = sa.table(
        "type_categories",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_fallback", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("display_order", sa.Integer),
    )

    op.bulk_insert(
        type_categories_table,
        [
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000001"),
                "slug": "customer_support",
                "name": "Customer Support Request",
                "description": "Customer asking for help, reporting an issue, or requesting support.",  # noqa: E501
                "is_fallback": False,
                "is_active": True,
                "display_order": 1,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000002"),
                "slug": "sales_inquiry",
                "name": "Sales Inquiry / Lead",
                "description": "Prospect or customer inquiring about products, pricing, or purchasing.",  # noqa: E501
                "is_fallback": False,
                "is_active": True,
                "display_order": 2,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000003"),
                "slug": "billing",
                "name": "Billing / Payment",
                "description": "Questions or issues related to invoices, payments, or subscriptions.",  # noqa: E501
                "is_fallback": False,
                "is_active": True,
                "display_order": 3,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000004"),
                "slug": "technical",
                "name": "Technical Issue / Bug Report",
                "description": "Bug reports, technical errors, or integration issues.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 4,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000005"),
                "slug": "partnership",
                "name": "Partnership / Business Development",
                "description": "Partnership proposals, collaboration requests, or BD outreach.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 5,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000006"),
                "slug": "hr_internal",
                "name": "HR / Internal Communication",
                "description": "HR matters, internal announcements, or employee communications.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 6,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000007"),
                "slug": "legal_compliance",
                "name": "Legal / Compliance",
                "description": "Legal notices, compliance requirements, or regulatory communications.",  # noqa: E501
                "is_fallback": False,
                "is_active": True,
                "display_order": 7,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000008"),
                "slug": "marketing_promo",
                "name": "Marketing / Promotional",
                "description": "Marketing campaigns, promotional offers, or newsletters.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 8,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000009"),
                "slug": "spam_automated",
                "name": "Spam / Automated Message",
                "description": "Spam, automated notifications, or bot-generated messages.",
                "is_fallback": False,
                "is_active": True,
                "display_order": 9,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0001-000000000010"),
                "slug": "other",
                "name": "Other — Fallback Type",
                "description": "Does not fit any defined category. Used as fallback type.",
                "is_fallback": True,
                "is_active": True,
                "display_order": 99,
            },
        ],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop tables in reverse FK-dependency order.
    # Tables with FKs pointing to other tables must be dropped first.
    # ------------------------------------------------------------------

    op.drop_table("classification_feedback")
    op.drop_table("crm_sync_records")
    op.drop_table("drafts")
    op.drop_table("routing_actions")
    op.drop_table("classification_results")
    op.drop_table("routing_rules")
    op.drop_table("emails")
    op.drop_table("type_categories")
    op.drop_table("action_categories")
    op.drop_table("users")

    # ------------------------------------------------------------------
    # Drop ENUM types after all tables are gone.
    # PostgreSQL raises an error if any column still references the type.
    # ------------------------------------------------------------------

    op.execute("DROP TYPE IF EXISTS emailstate")
    op.execute("DROP TYPE IF EXISTS classificationconfidence")
    op.execute("DROP TYPE IF EXISTS routingactionstatus")
    op.execute("DROP TYPE IF EXISTS draftstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS crmsyncstatus")
