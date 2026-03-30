from __future__ import annotations

import uuid

import pytest

from src.services.schemas.draft import (
    ClassificationContext,
    CRMContextData,
    DraftContext,
    DraftGenerationConfig,
    DraftRequest,
    DraftResult,
    EmailContent,
    OrgContext,
)

# ---------------------------------------------------------------------------
# EmailContent
# ---------------------------------------------------------------------------


class TestEmailContent:
    def test_required_fields_only(self) -> None:
        ec = EmailContent(
            sender_email="sender@example.com",
            subject="Hello",
            body_snippet="Short snippet",
            received_at="2026-01-01T10:00:00Z",
        )
        assert ec.sender_email == "sender@example.com"
        assert ec.subject == "Hello"
        assert ec.body_snippet == "Short snippet"
        assert ec.sender_name is None

    def test_sender_name_optional_defaults_none(self) -> None:
        ec = EmailContent(
            sender_email="a@b.com",
            subject="S",
            body_snippet="B",
            received_at="2026-01-01T00:00:00Z",
        )
        assert ec.sender_name is None

    def test_sender_name_provided(self) -> None:
        ec = EmailContent(
            sender_email="alice@corp.com",
            sender_name="Alice",
            subject="Meeting",
            body_snippet="Are you free?",
            received_at="2026-02-15T09:30:00Z",
        )
        assert ec.sender_name == "Alice"

    def test_received_at_stored(self) -> None:
        dt = "2026-03-01T12:00:00Z"
        ec = EmailContent(
            sender_email="x@y.com",
            subject="X",
            body_snippet="Y",
            received_at=dt,
        )
        assert ec.received_at == dt


# ---------------------------------------------------------------------------
# ClassificationContext
# ---------------------------------------------------------------------------


class TestClassificationContext:
    def test_happy_path(self) -> None:
        cc = ClassificationContext(action="reply", type="support", confidence="high")
        assert cc.action == "reply"
        assert cc.type == "support"
        assert cc.confidence == "high"

    @pytest.mark.parametrize(
        "action,type_,confidence",
        [
            ("reply", "billing", "high"),
            ("forward", "legal", "low"),
            ("archive", "marketing", "high"),
            ("escalate", "support", "low"),
        ],
    )
    def test_various_values(self, action: str, type_: str, confidence: str) -> None:
        cc = ClassificationContext(action=action, type=type_, confidence=confidence)
        assert cc.action == action
        assert cc.type == type_
        assert cc.confidence == confidence


# ---------------------------------------------------------------------------
# CRMContextData
# ---------------------------------------------------------------------------


class TestCRMContextData:
    def test_all_defaults_none_and_empty(self) -> None:
        crm = CRMContextData()
        assert crm.contact_name is None
        assert crm.company is None
        assert crm.account_tier is None
        assert crm.recent_interactions == []
        assert crm.contact_id is None

    def test_recent_interactions_defaults_empty_list(self) -> None:
        crm = CRMContextData()
        assert isinstance(crm.recent_interactions, list)
        assert len(crm.recent_interactions) == 0

    def test_all_fields_provided(self) -> None:
        crm = CRMContextData(
            contact_name="Bob",
            company="Acme Inc",
            account_tier="enterprise",
            recent_interactions=["Call on Jan 5", "Email on Jan 10"],
            contact_id="crm-001",
        )
        assert crm.contact_name == "Bob"
        assert crm.company == "Acme Inc"
        assert crm.account_tier == "enterprise"
        assert crm.recent_interactions == ["Call on Jan 5", "Email on Jan 10"]
        assert crm.contact_id == "crm-001"

    def test_partial_fields(self) -> None:
        crm = CRMContextData(contact_name="Carol", account_tier="starter")
        assert crm.contact_name == "Carol"
        assert crm.company is None
        assert crm.account_tier == "starter"
        assert crm.recent_interactions == []
        assert crm.contact_id is None

    def test_recent_interactions_list_independence(self) -> None:
        crm1 = CRMContextData()
        crm2 = CRMContextData()
        crm1.recent_interactions.append("Note")
        assert crm2.recent_interactions == []


# ---------------------------------------------------------------------------
# OrgContext
# ---------------------------------------------------------------------------


class TestOrgContext:
    def test_required_fields(self) -> None:
        org = OrgContext(system_prompt="You are a helpful assistant.", tone="formal")
        assert org.system_prompt == "You are a helpful assistant."
        assert org.tone == "formal"
        assert org.signature is None
        assert org.prohibited_language == []

    def test_signature_optional(self) -> None:
        org = OrgContext(system_prompt="Prompt", tone="casual")
        assert org.signature is None

    def test_signature_provided(self) -> None:
        org = OrgContext(
            system_prompt="Prompt",
            tone="formal",
            signature="Best regards,\nTeam",
        )
        assert org.signature == "Best regards,\nTeam"

    def test_prohibited_language_as_list(self) -> None:
        org = OrgContext(
            system_prompt="Prompt",
            tone="neutral",
            prohibited_language=["urgent", "ASAP", "immediately"],
        )
        assert isinstance(org.prohibited_language, list)
        assert len(org.prohibited_language) == 3
        assert "urgent" in org.prohibited_language

    def test_prohibited_language_defaults_empty(self) -> None:
        org = OrgContext(system_prompt="P", tone="T")
        assert org.prohibited_language == []

    def test_prohibited_language_list_independence(self) -> None:
        org1 = OrgContext(system_prompt="P", tone="T")
        org2 = OrgContext(system_prompt="P", tone="T")
        org1.prohibited_language.append("test")
        assert org2.prohibited_language == []


# ---------------------------------------------------------------------------
# DraftContext
# ---------------------------------------------------------------------------


def _make_email_content() -> EmailContent:
    return EmailContent(
        sender_email="user@test.com",
        subject="Test Subject",
        body_snippet="Test body",
        received_at="2026-01-15T08:00:00Z",
    )


def _make_classification() -> ClassificationContext:
    return ClassificationContext(action="reply", type="support", confidence="high")


def _make_org_context() -> OrgContext:
    return OrgContext(system_prompt="Be concise.", tone="professional")


class TestDraftContext:
    def test_required_fields_no_optionals(self) -> None:
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            org_context=_make_org_context(),
        )
        assert ctx.crm_context is None
        assert ctx.template is None
        assert ctx.notes == []

    def test_crm_context_optional(self) -> None:
        crm = CRMContextData(contact_name="Dave")
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            org_context=_make_org_context(),
            crm_context=crm,
        )
        assert ctx.crm_context is not None
        assert ctx.crm_context.contact_name == "Dave"

    def test_template_optional(self) -> None:
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            org_context=_make_org_context(),
            template="Dear {{name}},\n\nThank you.",
        )
        assert ctx.template == "Dear {{name}},\n\nThank you."

    def test_notes_default_empty(self) -> None:
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            org_context=_make_org_context(),
        )
        assert ctx.notes == []

    def test_notes_provided(self) -> None:
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            org_context=_make_org_context(),
            notes=["Keep it brief", "Mention ticket number"],
        )
        assert len(ctx.notes) == 2
        assert "Keep it brief" in ctx.notes

    def test_all_optional_fields(self) -> None:
        ctx = DraftContext(
            email_content=_make_email_content(),
            classification=_make_classification(),
            crm_context=CRMContextData(company="Corp"),
            org_context=_make_org_context(),
            template="Hello!",
            notes=["note1"],
        )
        assert ctx.crm_context is not None
        assert ctx.crm_context.company == "Corp"
        assert ctx.template == "Hello!"
        assert ctx.notes == ["note1"]


# ---------------------------------------------------------------------------
# DraftRequest
# ---------------------------------------------------------------------------


class TestDraftRequest:
    def test_happy_path(self) -> None:
        eid = uuid.uuid4()
        req = DraftRequest(
            email_id=eid,
            email_content=_make_email_content(),
            classification=_make_classification(),
        )
        assert req.email_id == eid
        assert req.template_id is None
        assert req.push_to_gmail is False

    def test_push_to_gmail_default_false(self) -> None:
        req = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=_make_email_content(),
            classification=_make_classification(),
        )
        assert req.push_to_gmail is False

    def test_push_to_gmail_explicit_true(self) -> None:
        req = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=_make_email_content(),
            classification=_make_classification(),
            push_to_gmail=True,
        )
        assert req.push_to_gmail is True

    def test_template_id_optional(self) -> None:
        req = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=_make_email_content(),
            classification=_make_classification(),
        )
        assert req.template_id is None

    def test_template_id_provided(self) -> None:
        req = DraftRequest(
            email_id=uuid.uuid4(),
            email_content=_make_email_content(),
            classification=_make_classification(),
            template_id="template-abc",
        )
        assert req.template_id == "template-abc"

    def test_email_id_is_uuid(self) -> None:
        eid = uuid.uuid4()
        req = DraftRequest(
            email_id=eid,
            email_content=_make_email_content(),
            classification=_make_classification(),
        )
        assert isinstance(req.email_id, uuid.UUID)
        assert req.email_id == eid

    def test_uuid_serialization(self) -> None:
        eid = uuid.uuid4()
        req = DraftRequest(
            email_id=eid,
            email_content=_make_email_content(),
            classification=_make_classification(),
        )
        data = req.model_dump()
        assert data["email_id"] == eid


# ---------------------------------------------------------------------------
# DraftResult
# ---------------------------------------------------------------------------


class TestDraftResult:
    @pytest.mark.parametrize(
        "status",
        ["generated", "failed", "generated_push_failed"],
    )
    def test_status_strings(self, status: str) -> None:
        result = DraftResult(email_id=uuid.uuid4(), status=status)
        assert result.status == status

    def test_defaults(self) -> None:
        eid = uuid.uuid4()
        result = DraftResult(email_id=eid, status="generated")
        assert result.draft_id is None
        assert result.gmail_draft_id is None
        assert result.model_used is None
        assert result.fallback_applied is False
        assert result.error_detail is None

    def test_all_fields_provided(self) -> None:
        eid = uuid.uuid4()
        did = uuid.uuid4()
        result = DraftResult(
            email_id=eid,
            draft_id=did,
            gmail_draft_id="gmail-draft-xyz",
            status="generated",
            model_used="gpt-4o",
            fallback_applied=True,
            error_detail=None,
        )
        assert result.email_id == eid
        assert result.draft_id == did
        assert result.gmail_draft_id == "gmail-draft-xyz"
        assert result.model_used == "gpt-4o"
        assert result.fallback_applied is True
        assert result.error_detail is None

    def test_failed_status_with_error_detail(self) -> None:
        result = DraftResult(
            email_id=uuid.uuid4(),
            status="failed",
            error_detail="LLM timeout after 3 retries",
        )
        assert result.status == "failed"
        assert result.error_detail == "LLM timeout after 3 retries"
        assert result.fallback_applied is False

    def test_push_failed_status(self) -> None:
        did = uuid.uuid4()
        result = DraftResult(
            email_id=uuid.uuid4(),
            draft_id=did,
            status="generated_push_failed",
            model_used="claude-3-haiku",
            error_detail="Gmail API 503",
        )
        assert result.status == "generated_push_failed"
        assert result.draft_id == did
        assert result.error_detail == "Gmail API 503"

    def test_email_id_is_uuid(self) -> None:
        eid = uuid.uuid4()
        result = DraftResult(email_id=eid, status="generated")
        assert isinstance(result.email_id, uuid.UUID)

    def test_draft_id_is_uuid_when_provided(self) -> None:
        did = uuid.uuid4()
        result = DraftResult(email_id=uuid.uuid4(), draft_id=did, status="generated")
        assert isinstance(result.draft_id, uuid.UUID)

    def test_uuid_serialization(self) -> None:
        eid = uuid.uuid4()
        did = uuid.uuid4()
        result = DraftResult(email_id=eid, draft_id=did, status="generated")
        data = result.model_dump()
        assert data["email_id"] == eid
        assert data["draft_id"] == did

    def test_fallback_applied_explicit_true(self) -> None:
        result = DraftResult(
            email_id=uuid.uuid4(),
            status="generated",
            fallback_applied=True,
        )
        assert result.fallback_applied is True


# ---------------------------------------------------------------------------
# DraftGenerationConfig
# ---------------------------------------------------------------------------


class TestDraftGenerationConfig:
    def test_valid_construction(self) -> None:
        org = _make_org_context()
        cfg = DraftGenerationConfig(
            push_to_gmail=False,
            org_context=org,
            retry_max=3,
        )
        assert cfg.push_to_gmail is False
        assert cfg.org_context is org
        assert cfg.retry_max == 3

    def test_push_to_gmail_true(self) -> None:
        cfg = DraftGenerationConfig(
            push_to_gmail=True,
            org_context=_make_org_context(),
            retry_max=2,
        )
        assert cfg.push_to_gmail is True

    def test_retry_max_stored(self) -> None:
        cfg = DraftGenerationConfig(
            push_to_gmail=False,
            org_context=_make_org_context(),
            retry_max=5,
        )
        assert cfg.retry_max == 5

    def test_org_context_nested(self) -> None:
        org = OrgContext(
            system_prompt="Be professional.",
            tone="formal",
            signature="Regards",
            prohibited_language=["ASAP"],
        )
        cfg = DraftGenerationConfig(push_to_gmail=True, org_context=org, retry_max=1)
        assert cfg.org_context.system_prompt == "Be professional."
        assert cfg.org_context.signature == "Regards"
        assert cfg.org_context.prohibited_language == ["ASAP"]

    @pytest.mark.parametrize("retry_max", [0, 1, 3, 10])
    def test_retry_max_values(self, retry_max: int) -> None:
        cfg = DraftGenerationConfig(
            push_to_gmail=False,
            org_context=_make_org_context(),
            retry_max=retry_max,
        )
        assert cfg.retry_max == retry_max
