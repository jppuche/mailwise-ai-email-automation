"""Tests for EmailState state machine — pure unit tests, no database required.

Documents the state machine behaviour defined in block-01-models.md:
- Valid transitions update email.state
- Invalid transitions raise InvalidStateTransitionError directly (D8: no try/except wrapping)
- Terminal state RESPONDED has no allowed outgoing transitions
- Recovery paths allow retrying from error states
- Exception message includes current state, target state, and allowed set

Architecture directive D8 (try-except skill):
  transition_to() is local computation that enforces invariants.
  It must raise directly — callers MUST NOT wrap it in try/except.
  A failing transition is a programmer error, not an operational error.
"""

import datetime
import uuid

import pytest

from src.core.exceptions import InvalidStateTransitionError
from src.models.email import VALID_TRANSITIONS, Email, EmailState

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_email(state: EmailState) -> Email:
    """Create an Email instance in a given state without a DB session.

    Uses the normal constructor so SQLAlchemy's ORM instrumentation is
    properly initialized. transition_to() reads/writes self.state through
    ORM descriptors, so __new__ alone is not sufficient.
    """
    return Email(
        id=uuid.uuid4(),
        provider_message_id=f"test-{uuid.uuid4()}",
        account="test@example.com",
        sender_email="sender@example.com",
        date=datetime.datetime.now(datetime.UTC),
        state=state,
    )


# ---------------------------------------------------------------------------
# Valid transitions — all allowed edges in the state graph
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Every allowed transition in VALID_TRANSITIONS must succeed and update state."""

    def test_fetched_to_sanitized(self) -> None:
        email = _make_email(EmailState.FETCHED)
        email.transition_to(EmailState.SANITIZED)
        assert email.state is EmailState.SANITIZED

    def test_sanitized_to_classified(self) -> None:
        email = _make_email(EmailState.SANITIZED)
        email.transition_to(EmailState.CLASSIFIED)
        assert email.state is EmailState.CLASSIFIED

    def test_sanitized_to_classification_failed(self) -> None:
        email = _make_email(EmailState.SANITIZED)
        email.transition_to(EmailState.CLASSIFICATION_FAILED)
        assert email.state is EmailState.CLASSIFICATION_FAILED

    def test_classified_to_routed(self) -> None:
        email = _make_email(EmailState.CLASSIFIED)
        email.transition_to(EmailState.ROUTED)
        assert email.state is EmailState.ROUTED

    def test_classified_to_routing_failed(self) -> None:
        email = _make_email(EmailState.CLASSIFIED)
        email.transition_to(EmailState.ROUTING_FAILED)
        assert email.state is EmailState.ROUTING_FAILED

    def test_routed_to_crm_synced(self) -> None:
        email = _make_email(EmailState.ROUTED)
        email.transition_to(EmailState.CRM_SYNCED)
        assert email.state is EmailState.CRM_SYNCED

    def test_routed_to_crm_sync_failed(self) -> None:
        email = _make_email(EmailState.ROUTED)
        email.transition_to(EmailState.CRM_SYNC_FAILED)
        assert email.state is EmailState.CRM_SYNC_FAILED

    def test_crm_synced_to_draft_generated(self) -> None:
        email = _make_email(EmailState.CRM_SYNCED)
        email.transition_to(EmailState.DRAFT_GENERATED)
        assert email.state is EmailState.DRAFT_GENERATED

    def test_crm_synced_to_draft_failed(self) -> None:
        email = _make_email(EmailState.CRM_SYNCED)
        email.transition_to(EmailState.DRAFT_FAILED)
        assert email.state is EmailState.DRAFT_FAILED

    def test_draft_generated_to_completed(self) -> None:
        email = _make_email(EmailState.DRAFT_GENERATED)
        email.transition_to(EmailState.COMPLETED)
        assert email.state is EmailState.COMPLETED

    def test_completed_to_responded(self) -> None:
        email = _make_email(EmailState.COMPLETED)
        email.transition_to(EmailState.RESPONDED)
        assert email.state is EmailState.RESPONDED

    def test_valid_transitions_coverage(self) -> None:
        """Every state in VALID_TRANSITIONS that has allowed targets has at least one."""
        non_terminal_states = [s for s, targets in VALID_TRANSITIONS.items() if targets]
        assert len(non_terminal_states) > 0, "State graph must have non-terminal states"
        for state in non_terminal_states:
            assert len(VALID_TRANSITIONS[state]) > 0


# ---------------------------------------------------------------------------
# Recovery paths — error states can retry from their predecessor
# ---------------------------------------------------------------------------


class TestRecoveryPaths:
    """Error states expose recovery paths so the pipeline can retry failed stages."""

    def test_classification_failed_to_sanitized(self) -> None:
        """CLASSIFICATION_FAILED retries by going back to SANITIZED."""
        email = _make_email(EmailState.CLASSIFICATION_FAILED)
        email.transition_to(EmailState.SANITIZED)
        assert email.state is EmailState.SANITIZED

    def test_routing_failed_to_classified(self) -> None:
        """ROUTING_FAILED retries by going back to CLASSIFIED."""
        email = _make_email(EmailState.ROUTING_FAILED)
        email.transition_to(EmailState.CLASSIFIED)
        assert email.state is EmailState.CLASSIFIED

    def test_crm_sync_failed_to_routed(self) -> None:
        """CRM_SYNC_FAILED retries by going back to ROUTED."""
        email = _make_email(EmailState.CRM_SYNC_FAILED)
        email.transition_to(EmailState.ROUTED)
        assert email.state is EmailState.ROUTED

    def test_draft_failed_to_crm_synced(self) -> None:
        """DRAFT_FAILED retries by going back to CRM_SYNCED."""
        email = _make_email(EmailState.DRAFT_FAILED)
        email.transition_to(EmailState.CRM_SYNCED)
        assert email.state is EmailState.CRM_SYNCED


# ---------------------------------------------------------------------------
# Invalid transitions — each forbidden edge must raise
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    """Invalid transitions raise InvalidStateTransitionError without wrapping.

    D8 (try-except directive): transition_to() performs local computation that
    enforces invariants. It must raise directly — no try/except in production
    code should catch this. The test itself does NOT use try/except; it uses
    pytest.raises() which is the testing idiom for asserting exceptions.
    """

    def test_fetched_cannot_skip_to_classified(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.CLASSIFIED)

    def test_fetched_cannot_skip_to_routed(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.ROUTED)

    def test_fetched_cannot_skip_to_completed(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.COMPLETED)

    def test_fetched_cannot_transition_to_itself(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.FETCHED)

    def test_classified_cannot_go_back_to_sanitized(self) -> None:
        """Forward-only constraint: classified emails do not go back to sanitized."""
        email = _make_email(EmailState.CLASSIFIED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.SANITIZED)

    def test_classified_cannot_skip_to_crm_synced(self) -> None:
        email = _make_email(EmailState.CLASSIFIED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.CRM_SYNCED)

    def test_routed_cannot_skip_to_draft_generated(self) -> None:
        email = _make_email(EmailState.ROUTED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.DRAFT_GENERATED)

    def test_routed_cannot_skip_to_completed(self) -> None:
        email = _make_email(EmailState.ROUTED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.COMPLETED)

    def test_sanitized_cannot_go_to_routed(self) -> None:
        email = _make_email(EmailState.SANITIZED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.ROUTED)

    def test_draft_generated_cannot_go_to_sanitized(self) -> None:
        email = _make_email(EmailState.DRAFT_GENERATED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.SANITIZED)

    def test_draft_generated_cannot_skip_to_responded(self) -> None:
        """DRAFT_GENERATED → RESPONDED skips COMPLETED; must be rejected."""
        email = _make_email(EmailState.DRAFT_GENERATED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(EmailState.RESPONDED)


# ---------------------------------------------------------------------------
# Terminal state — RESPONDED has no outgoing transitions
# ---------------------------------------------------------------------------


class TestTerminalState:
    """RESPONDED is the terminal state: every outgoing transition must raise."""

    @pytest.mark.parametrize("target", list(EmailState))
    def test_responded_rejects_all_transitions(self, target: EmailState) -> None:
        """From RESPONDED, transitioning to ANY state (including itself) is invalid."""
        email = _make_email(EmailState.RESPONDED)
        with pytest.raises(InvalidStateTransitionError):
            email.transition_to(target)

    def test_responded_has_empty_allowed_set(self) -> None:
        """VALID_TRANSITIONS documents RESPONDED as frozenset() — terminal."""
        assert VALID_TRANSITIONS[EmailState.RESPONDED] == frozenset()


# ---------------------------------------------------------------------------
# Exception message quality
# ---------------------------------------------------------------------------


class TestExceptionMessage:
    """The error message must provide actionable diagnostic information.

    A developer encountering InvalidStateTransitionError in logs must be able
    to identify: what state the email was in, what transition was attempted,
    and what transitions are actually allowed.
    """

    def test_message_contains_current_state(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError, match="FETCHED"):
            email.transition_to(EmailState.CLASSIFIED)

    def test_message_contains_target_state(self) -> None:
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError, match="CLASSIFIED"):
            email.transition_to(EmailState.CLASSIFIED)

    def test_message_contains_allowed_transitions(self) -> None:
        """The allowed set must appear in the message so the developer knows valid options."""
        email = _make_email(EmailState.FETCHED)
        with pytest.raises(InvalidStateTransitionError, match="SANITIZED"):
            email.transition_to(EmailState.CLASSIFIED)

    def test_message_for_terminal_state_contains_state_name(self) -> None:
        email = _make_email(EmailState.RESPONDED)
        with pytest.raises(InvalidStateTransitionError, match="RESPONDED"):
            email.transition_to(EmailState.FETCHED)


# ---------------------------------------------------------------------------
# State graph completeness — all EmailState members have entries in VALID_TRANSITIONS
# ---------------------------------------------------------------------------


class TestStateGraphCompleteness:
    """VALID_TRANSITIONS must cover every EmailState member.

    A missing entry would allow silent state skipping — pre-mortem Cat 1
    (implicit ordering). The state machine is only as strong as its coverage.
    """

    def test_all_states_have_transition_entry(self) -> None:
        """Every EmailState member must be a key in VALID_TRANSITIONS."""
        for state in EmailState:
            assert state in VALID_TRANSITIONS, (
                f"EmailState.{state.name} has no entry in VALID_TRANSITIONS. "
                "Add it (use frozenset() for terminal states)."
            )

    def test_transition_targets_are_valid_states(self) -> None:
        """Every target state in VALID_TRANSITIONS must be a valid EmailState member."""
        valid_states = set(EmailState)
        for source, targets in VALID_TRANSITIONS.items():
            for target in targets:
                assert target in valid_states, (
                    f"VALID_TRANSITIONS[{source}] contains {target!r} "
                    "which is not a valid EmailState member."
                )

    def test_happy_path_states_are_defined(self) -> None:
        """All documented happy-path states exist."""
        happy_path = [
            EmailState.FETCHED,
            EmailState.SANITIZED,
            EmailState.CLASSIFIED,
            EmailState.ROUTED,
            EmailState.CRM_SYNCED,
            EmailState.DRAFT_GENERATED,
            EmailState.COMPLETED,
            EmailState.RESPONDED,
        ]
        for state in happy_path:
            assert state in EmailState

    def test_error_states_are_defined(self) -> None:
        """All documented error states exist."""
        error_states = [
            EmailState.CLASSIFICATION_FAILED,
            EmailState.ROUTING_FAILED,
            EmailState.CRM_SYNC_FAILED,
            EmailState.DRAFT_FAILED,
        ]
        for state in error_states:
            assert state in EmailState

    def test_total_state_count(self) -> None:
        """State machine has exactly 12 states as per spec."""
        assert len(EmailState) == 12
