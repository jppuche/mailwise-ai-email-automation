"""DraftContextBuilder — pure-local context assembly for draft generation.

Zero try/except enforced (D8). All operations are local computation:
string assembly, conditional checks, data extraction.

contract-docstrings:
  Invariants: All inputs are pre-validated Pydantic models.
  Guarantees: build() NEVER raises — always returns a DraftContext.
    build_llm_prompt() returns a well-formed string prompt.
  Errors raised: None.
  Errors silenced: None — no external state operations.
  External state: None — pure-local module.

try-except D8:
  Local computation only — conditionals, not try/except.
  grep enforcement: ``grep -n "try\\|except" src/services/draft_context.py``
  must return empty (or comments only).
"""

from __future__ import annotations

from src.models.crm_sync import CRMSyncRecord
from src.services.schemas.draft import (
    CRMContextData,
    DraftContext,
    DraftRequest,
    OrgContext,
)


class DraftContextBuilder:
    """Assembles DraftContext from multiple data sources.

    Invariants:
      - All inputs are pre-validated (Pydantic models or ORM objects).

    Guarantees:
      - ``build()`` always returns a ``DraftContext`` — never raises.
      - Missing data sources result in notes, not errors.
      - ``build_llm_prompt()`` returns a well-structured prompt string.
    """

    def build(
        self,
        request: DraftRequest,
        crm_record: CRMSyncRecord | None,
        template_content: str | None,
        org_context: OrgContext,
    ) -> DraftContext:
        """Assemble a complete DraftContext from available data sources.

        Preconditions:
          - ``request`` contains pre-truncated ``body_snippet``.
          - ``crm_record`` may be None (no CRM sync occurred or failed).
          - ``template_content`` may be None (no template selected).

        Guarantees:
          - Always returns a valid ``DraftContext``.
          - Missing sources produce notes, not errors.

        Local computation only (D8) — zero try/except.
        """
        notes: list[str] = []

        # Extract CRM context if available — conditional, not try/except
        crm_context: CRMContextData | None = None
        if crm_record is not None:
            crm_context = self._extract_crm_context(crm_record)
        else:
            notes.append("CRM context unavailable")

        # Resolve template — conditional, not try/except
        template: str | None = None
        if template_content is not None:
            template = template_content
        elif request.template_id is not None:
            notes.append(f"Template '{request.template_id}' not found")

        return DraftContext(
            email_content=request.email_content,
            classification=request.classification,
            crm_context=crm_context,
            org_context=org_context,
            template=template,
            notes=notes,
        )

    def _extract_crm_context(self, record: CRMSyncRecord) -> CRMContextData:
        """Extract CRM context from a CRMSyncRecord.

        Only ``contact_id`` is available from the record (B10).
        Other fields remain at defaults (None/[]).

        Local computation (D8) — no try/except.
        """
        return CRMContextData(contact_id=record.contact_id)

    def build_llm_prompt(self, context: DraftContext) -> str:
        """Build a structured LLM prompt from DraftContext.

        Sections: EMAIL / CLASSIFICATION / CRM CONTEXT / TEMPLATE / NOTES / INSTRUCTIONS
        Separator: ``\\n\\n---\\n\\n``

        Guarantees:
          - Always returns a non-empty string.
          - body_snippet is already truncated — no further truncation here.

        Local computation (D8) — string assembly only.
        """
        sections: list[str] = []

        # EMAIL section
        email = context.email_content
        email_lines = [
            "## EMAIL",
            f"From: {email.sender_email}",
        ]
        if email.sender_name:
            email_lines.append(f"Name: {email.sender_name}")
        email_lines.extend([
            f"Subject: {email.subject}",
            f"Received: {email.received_at}",
            f"Body:\n{email.body_snippet}",
        ])
        sections.append("\n".join(email_lines))

        # CLASSIFICATION section
        cls = context.classification
        sections.append(
            "\n".join([
                "## CLASSIFICATION",
                f"Action: {cls.action}",
                f"Type: {cls.type}",
                f"Confidence: {cls.confidence}",
            ])
        )

        # CRM CONTEXT section (conditional)
        if context.crm_context is not None:
            crm = context.crm_context
            crm_lines = ["## CRM CONTEXT"]
            if crm.contact_id:
                crm_lines.append(f"Contact ID: {crm.contact_id}")
            if crm.contact_name:
                crm_lines.append(f"Contact Name: {crm.contact_name}")
            if crm.company:
                crm_lines.append(f"Company: {crm.company}")
            if crm.account_tier:
                crm_lines.append(f"Account Tier: {crm.account_tier}")
            if crm.recent_interactions:
                crm_lines.append("Recent Interactions:")
                for interaction in crm.recent_interactions:
                    crm_lines.append(f"  - {interaction}")
            sections.append("\n".join(crm_lines))

        # TEMPLATE section (conditional)
        if context.template is not None:
            sections.append(f"## TEMPLATE\n{context.template}")

        # NOTES section (conditional)
        if context.notes:
            note_lines = ["## NOTES"]
            for note in context.notes:
                note_lines.append(f"- {note}")
            sections.append("\n".join(note_lines))

        # INSTRUCTIONS section
        org = context.org_context
        instruction_lines = ["## INSTRUCTIONS"]
        instruction_lines.append(f"Tone: {org.tone}")
        if org.signature:
            instruction_lines.append(f"Signature: {org.signature}")
        if org.prohibited_language:
            instruction_lines.append(
                f"Prohibited language: {', '.join(org.prohibited_language)}"
            )
        instruction_lines.append(
            "Draft a professional reply to this email based on the context above."
        )
        sections.append("\n".join(instruction_lines))

        return "\n\n---\n\n".join(sections)
