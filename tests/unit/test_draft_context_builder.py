"""Unit tests for DraftContextBuilder.

Covers:
- build() always returns DraftContext (D8 — never raises)
- Missing CRM record → crm_context=None + note
- Missing template_content with template_id → note
- Both CRM and template absent → both notes
- Prompt contains body_snippet only (not full body)
- build_llm_prompt() section presence/absence based on context state
- _extract_crm_context() populates only contact_id from CRMSyncRecord
- Zero try/except enforcement (D8 — structural)
"""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import MagicMock

import pytest

from src.models.crm_sync import CRMSyncRecord
from src.services.draft_context import DraftContextBuilder
from src.services.schemas.draft import (
    ClassificationContext,
    CRMContextData,
    DraftContext,
    DraftRequest,
    EmailContent,
    OrgContext,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SEPARATOR = "\n\n---\n\n"


@pytest.fixture()
def builder() -> DraftContextBuilder:
    return DraftContextBuilder()


@pytest.fixture()
def email_content() -> EmailContent:
    return EmailContent(
        sender_email="customer@example.com",
        sender_name="John Doe",
        subject="Help with order",
        body_snippet="I need help with my order #12345...",
        received_at="2026-02-28T10:00:00Z",
    )


@pytest.fixture()
def classification() -> ClassificationContext:
    return ClassificationContext(action="respond", type="support", confidence="high")


@pytest.fixture()
def org_context() -> OrgContext:
    return OrgContext(
        system_prompt="You are a support agent",
        tone="professional",
        signature="Best regards, Support Team",
        prohibited_language=["unfortunately", "can't help"],
    )


@pytest.fixture()
def org_context_minimal() -> OrgContext:
    """OrgContext with no optional fields — tone only."""
    return OrgContext(system_prompt="You are a support agent", tone="professional")


@pytest.fixture()
def draft_request(
    email_content: EmailContent, classification: ClassificationContext
) -> DraftRequest:
    return DraftRequest(
        email_id=uuid.uuid4(),
        email_content=email_content,
        classification=classification,
    )


@pytest.fixture()
def draft_request_with_template(
    email_content: EmailContent,
    classification: ClassificationContext,
) -> DraftRequest:
    return DraftRequest(
        email_id=uuid.uuid4(),
        email_content=email_content,
        classification=classification,
        template_id="support-acknowledge",
    )


@pytest.fixture()
def mock_crm_record() -> MagicMock:
    record = MagicMock(spec=CRMSyncRecord)
    record.contact_id = "crm-123"
    return record


# ---------------------------------------------------------------------------
# Helper: build a minimal DraftContext directly for prompt tests
# ---------------------------------------------------------------------------


def _make_context(
    email_content: EmailContent,
    classification: ClassificationContext,
    org_context: OrgContext,
    crm_context: CRMContextData | None = None,
    template: str | None = None,
    notes: list[str] | None = None,
) -> DraftContext:
    return DraftContext(
        email_content=email_content,
        classification=classification,
        crm_context=crm_context,
        org_context=org_context,
        template=template,
        notes=notes or [],
    )


# ===========================================================================
# 1. build() — return type and full context
# ===========================================================================


class TestBuildReturnType:
    def test_build_returns_draft_context(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        mock_crm_record: MagicMock,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, mock_crm_record, "Template body", org_context)
        assert isinstance(result, DraftContext)

    def test_build_full_context_all_fields_populated(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        mock_crm_record: MagicMock,
        org_context: OrgContext,
    ) -> None:
        template_content = "Please acknowledge the customer's request."
        result = builder.build(draft_request, mock_crm_record, template_content, org_context)

        assert result.crm_context is not None
        assert result.crm_context.contact_id == "crm-123"
        assert result.template == template_content
        assert result.notes == []
        assert result.org_context == org_context
        assert result.email_content == draft_request.email_content
        assert result.classification == draft_request.classification

    def test_build_propagates_email_content(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, None, None, org_context)
        assert result.email_content.sender_email == "customer@example.com"
        assert result.email_content.subject == "Help with order"
        assert result.email_content.body_snippet == "I need help with my order #12345..."

    def test_build_propagates_classification(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, None, None, org_context)
        assert result.classification.action == "respond"
        assert result.classification.type == "support"
        assert result.classification.confidence == "high"


# ===========================================================================
# 2. build() — no CRM record
# ===========================================================================


class TestBuildNoCRM:
    def test_no_crm_record_sets_crm_context_none(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, None, None, org_context)
        assert result.crm_context is None

    def test_no_crm_record_adds_unavailable_note(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, None, None, org_context)
        assert "CRM context unavailable" in result.notes

    def test_with_crm_record_no_note_added(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        mock_crm_record: MagicMock,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request, mock_crm_record, None, org_context)
        assert "CRM context unavailable" not in result.notes


# ===========================================================================
# 3. build() — no template_content but template_id set
# ===========================================================================


class TestBuildNoTemplate:
    def test_no_template_content_sets_template_none(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        assert result.template is None

    def test_no_template_content_with_template_id_adds_note(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        assert any("support-acknowledge" in note for note in result.notes)
        assert any("not found" in note for note in result.notes)

    def test_note_contains_template_id_name(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        matching_notes = [n for n in result.notes if "support-acknowledge" in n]
        assert len(matching_notes) == 1

    def test_no_template_id_no_note_for_missing_template(
        self,
        builder: DraftContextBuilder,
        draft_request: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        # draft_request has no template_id — silence is correct
        result = builder.build(draft_request, None, None, org_context)
        assert not any("not found" in note for note in result.notes)

    def test_template_content_provided_is_stored(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        mock_crm_record: MagicMock,
        org_context: OrgContext,
    ) -> None:
        content = "Acknowledge the customer's request and offer next steps."
        result = builder.build(draft_request_with_template, mock_crm_record, content, org_context)
        assert result.template == content
        assert not any("not found" in note for note in result.notes)


# ===========================================================================
# 4. build() — both CRM and template missing
# ===========================================================================


class TestBuildBothMissing:
    def test_both_missing_both_notes_present(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        assert "CRM context unavailable" in result.notes
        assert any("not found" in note for note in result.notes)
        assert len(result.notes) == 2

    def test_both_missing_crm_context_is_none(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        assert result.crm_context is None

    def test_both_missing_template_is_none(
        self,
        builder: DraftContextBuilder,
        draft_request_with_template: DraftRequest,
        org_context: OrgContext,
    ) -> None:
        result = builder.build(draft_request_with_template, None, None, org_context)
        assert result.template is None


# ===========================================================================
# 5. build() never raises (D8 enforcement)
# ===========================================================================


class TestBuildNeverRaises:
    def test_build_never_raises_with_all_none(self, builder: DraftContextBuilder) -> None:
        """D8: build() must never raise regardless of missing optional inputs."""
        request = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=EmailContent(
                sender_email="x@example.com",
                subject="Test",
                body_snippet="snippet",
                received_at="2026-01-01T00:00:00Z",
            ),
            classification=ClassificationContext(action="ignore", type="spam", confidence="low"),
        )
        org = OrgContext(system_prompt="You are a bot", tone="neutral")
        result = builder.build(request, None, None, org)
        assert isinstance(result, DraftContext)

    def test_build_never_raises_sender_name_none(self, builder: DraftContextBuilder) -> None:
        """sender_name is optional — build() still returns DraftContext."""
        request = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=EmailContent(
                sender_email="anon@example.com",
                sender_name=None,
                subject="No name",
                body_snippet="Body",
                received_at="2026-01-01T00:00:00Z",
            ),
            classification=ClassificationContext(
                action="respond", type="inquiry", confidence="high"
            ),
        )
        org = OrgContext(system_prompt="Agent", tone="friendly")
        result = builder.build(request, None, None, org)
        assert isinstance(result, DraftContext)


# ===========================================================================
# 6. _extract_crm_context — only contact_id populated
# ===========================================================================


class TestExtractCRMContext:
    def test_extract_crm_context_returns_crm_context_data(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert isinstance(result, CRMContextData)

    def test_extract_crm_context_populates_contact_id(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert result.contact_id == "crm-123"

    def test_extract_crm_context_contact_name_is_none(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert result.contact_name is None

    def test_extract_crm_context_company_is_none(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert result.company is None

    def test_extract_crm_context_account_tier_is_none(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert result.account_tier is None

    def test_extract_crm_context_recent_interactions_empty(
        self,
        builder: DraftContextBuilder,
        mock_crm_record: MagicMock,
    ) -> None:
        result = builder._extract_crm_context(mock_crm_record)
        assert result.recent_interactions == []

    def test_extract_crm_context_none_contact_id_allowed(
        self,
        builder: DraftContextBuilder,
    ) -> None:
        """contact_id may be None on a record where sync produced no CRM contact."""
        record = MagicMock(spec=CRMSyncRecord)
        record.contact_id = None
        result = builder._extract_crm_context(record)
        assert result.contact_id is None


# ===========================================================================
# 7. build_llm_prompt() — EMAIL section
# ===========================================================================


class TestBuildLLMPromptEmailSection:
    def test_prompt_contains_email_header(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "## EMAIL" in prompt

    def test_prompt_contains_sender_email(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "customer@example.com" in prompt

    def test_prompt_contains_sender_name_when_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "John Doe" in prompt

    def test_prompt_omits_name_line_when_sender_name_none(
        self,
        builder: DraftContextBuilder,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        email_no_name = EmailContent(
            sender_email="anon@example.com",
            sender_name=None,
            subject="Anonymous",
            body_snippet="Some body snippet",
            received_at="2026-01-01T00:00:00Z",
        )
        context = _make_context(email_no_name, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Name:" not in prompt

    def test_prompt_contains_subject(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Help with order" in prompt

    def test_prompt_contains_body_snippet(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "I need help with my order #12345..." in prompt

    def test_prompt_does_not_contain_full_body_beyond_snippet(
        self,
        builder: DraftContextBuilder,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        """body_snippet is pre-truncated — prompt must not contain more than snippet."""
        snippet = "First 200 chars of body..."
        full_body_marker = "FULL_BODY_SENTINEL_CONTENT_NOT_IN_SNIPPET"
        email = EmailContent(
            sender_email="sender@example.com",
            subject="Subject",
            body_snippet=snippet,
            received_at="2026-01-01T00:00:00Z",
        )
        context = _make_context(email, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert snippet in prompt
        assert full_body_marker not in prompt


# ===========================================================================
# 8. build_llm_prompt() — CLASSIFICATION section
# ===========================================================================


class TestBuildLLMPromptClassificationSection:
    def test_prompt_contains_classification_header(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "## CLASSIFICATION" in prompt

    def test_prompt_contains_action(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Action: respond" in prompt

    def test_prompt_contains_type(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Type: support" in prompt

    def test_prompt_contains_confidence(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Confidence: high" in prompt


# ===========================================================================
# 9. build_llm_prompt() — CRM CONTEXT section (conditional)
# ===========================================================================


class TestBuildLLMPromptCRMSection:
    def test_prompt_includes_crm_section_when_crm_context_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        crm = CRMContextData(contact_id="crm-456")
        context = _make_context(email_content, classification, org_context, crm_context=crm)
        prompt = builder.build_llm_prompt(context)
        assert "## CRM CONTEXT" in prompt

    def test_prompt_includes_contact_id_in_crm_section(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        crm = CRMContextData(contact_id="crm-456")
        context = _make_context(email_content, classification, org_context, crm_context=crm)
        prompt = builder.build_llm_prompt(context)
        assert "Contact ID: crm-456" in prompt

    def test_prompt_omits_crm_section_when_crm_context_none(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context, crm_context=None)
        prompt = builder.build_llm_prompt(context)
        assert "## CRM CONTEXT" not in prompt

    def test_prompt_crm_section_includes_contact_name_when_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        crm = CRMContextData(contact_id="crm-789", contact_name="Alice Smith")
        context = _make_context(email_content, classification, org_context, crm_context=crm)
        prompt = builder.build_llm_prompt(context)
        assert "Contact Name: Alice Smith" in prompt

    def test_prompt_crm_section_includes_company_when_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        crm = CRMContextData(contact_id="crm-789", company="Acme Corp")
        context = _make_context(email_content, classification, org_context, crm_context=crm)
        prompt = builder.build_llm_prompt(context)
        assert "Company: Acme Corp" in prompt

    def test_prompt_crm_section_includes_recent_interactions(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        crm = CRMContextData(
            contact_id="crm-789",
            recent_interactions=["Call on 2026-01-15", "Email on 2026-02-01"],
        )
        context = _make_context(email_content, classification, org_context, crm_context=crm)
        prompt = builder.build_llm_prompt(context)
        assert "Recent Interactions:" in prompt
        assert "Call on 2026-01-15" in prompt
        assert "Email on 2026-02-01" in prompt


# ===========================================================================
# 10. build_llm_prompt() — TEMPLATE section (conditional)
# ===========================================================================


class TestBuildLLMPromptTemplateSection:
    def test_prompt_includes_template_section_when_template_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        template = "Thank you for contacting us. We will respond within 24 hours."
        context = _make_context(email_content, classification, org_context, template=template)
        prompt = builder.build_llm_prompt(context)
        assert "## TEMPLATE" in prompt
        assert template in prompt

    def test_prompt_omits_template_section_when_template_none(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context, template=None)
        prompt = builder.build_llm_prompt(context)
        assert "## TEMPLATE" not in prompt


# ===========================================================================
# 11. build_llm_prompt() — NOTES section (conditional)
# ===========================================================================


class TestBuildLLMPromptNotesSection:
    def test_prompt_includes_notes_section_when_notes_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        notes = ["CRM context unavailable", "Template 'support-ack' not found"]
        context = _make_context(email_content, classification, org_context, notes=notes)
        prompt = builder.build_llm_prompt(context)
        assert "## NOTES" in prompt
        assert "CRM context unavailable" in prompt
        assert "Template 'support-ack' not found" in prompt

    def test_prompt_omits_notes_section_when_notes_empty(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context, notes=[])
        prompt = builder.build_llm_prompt(context)
        assert "## NOTES" not in prompt

    def test_notes_are_formatted_as_bullet_list(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        notes = ["First note", "Second note"]
        context = _make_context(email_content, classification, org_context, notes=notes)
        prompt = builder.build_llm_prompt(context)
        assert "- First note" in prompt
        assert "- Second note" in prompt


# ===========================================================================
# 12. build_llm_prompt() — INSTRUCTIONS section
# ===========================================================================


class TestBuildLLMPromptInstructionsSection:
    def test_prompt_always_contains_instructions_header(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context_minimal: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context_minimal)
        prompt = builder.build_llm_prompt(context)
        assert "## INSTRUCTIONS" in prompt

    def test_prompt_includes_tone_in_instructions(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Tone: professional" in prompt

    def test_prompt_includes_signature_when_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Signature: Best regards, Support Team" in prompt

    def test_prompt_omits_signature_line_when_absent(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context_minimal: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context_minimal)
        prompt = builder.build_llm_prompt(context)
        assert "Signature:" not in prompt

    def test_prompt_includes_prohibited_language_when_present(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Prohibited language:" in prompt
        assert "unfortunately" in prompt
        assert "can't help" in prompt

    def test_prompt_omits_prohibited_language_when_empty(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context_minimal: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context_minimal)
        prompt = builder.build_llm_prompt(context)
        assert "Prohibited language:" not in prompt

    def test_prompt_instructions_contains_draft_directive(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        """INSTRUCTIONS section must end with the standard draft directive."""
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert "Draft a professional reply" in prompt


# ===========================================================================
# 13. build_llm_prompt() — section separator
# ===========================================================================


class TestBuildLLMPromptSeparator:
    def test_prompt_uses_correct_separator_between_sections(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        context = _make_context(email_content, classification, org_context)
        prompt = builder.build_llm_prompt(context)
        assert SEPARATOR in prompt

    def test_minimum_two_separators_for_email_classification_instructions(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context_minimal: OrgContext,
    ) -> None:
        """Minimal context (no CRM, template, notes) = 3 sections = 2 separators."""
        context = _make_context(email_content, classification, org_context_minimal)
        prompt = builder.build_llm_prompt(context)
        assert prompt.count(SEPARATOR) == 2

    def test_all_optional_sections_add_separators(
        self,
        builder: DraftContextBuilder,
        email_content: EmailContent,
        classification: ClassificationContext,
        org_context: OrgContext,
    ) -> None:
        """EMAIL + CLASSIFICATION + CRM + TEMPLATE + NOTES + INSTRUCTIONS = 5 separators."""
        crm = CRMContextData(contact_id="crm-001")
        template = "Standard response template."
        notes = ["A note"]
        context = _make_context(
            email_content,
            classification,
            org_context,
            crm_context=crm,
            template=template,
            notes=notes,
        )
        prompt = builder.build_llm_prompt(context)
        assert prompt.count(SEPARATOR) == 5


# ===========================================================================
# 14. D8 structural enforcement — zero try/except in module
# ===========================================================================


class TestD8TryExceptEnforcement:
    def test_draft_context_module_has_no_try_except(self) -> None:
        """D8: DraftContextBuilder is pure-local computation — zero try/except.

        Uses tokenize to detect actual try/except keywords, not occurrences
        inside string literals or comments (which would produce false positives).
        """
        import io
        import tokenize as tok_module

        import src.services.draft_context as module

        source = inspect.getsource(module)
        tokens = list(tok_module.generate_tokens(io.StringIO(source).readline))
        keyword_names = {token.string for token in tokens if token.type == tok_module.NAME}
        assert "try" not in keyword_names, "Found 'try' keyword — D8 violation"
        assert "except" not in keyword_names, "Found 'except' keyword — D8 violation"
