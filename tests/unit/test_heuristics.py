"""Tests for HeuristicClassifier in src/services/heuristics.py.

Pure local computation — no external I/O, no try/except, no DB.
All tests are synchronous.
"""

from __future__ import annotations

import uuid

import pytest

from src.services.heuristics import HeuristicClassifier
from src.services.schemas.classification import ClassificationRequest, HeuristicResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    subject: str = "Test subject",
    body: str = "Normal email body",
    sender_email: str = "user@example.com",
    sender_domain: str = "example.com",
) -> ClassificationRequest:
    return ClassificationRequest(
        email_id=uuid.uuid4(),
        sanitized_body=body,
        subject=subject,
        sender_email=sender_email,
        sender_domain=sender_domain,
    )


# Convenience: classify with empty internal_domains unless overridden.
def _classify(
    classifier: HeuristicClassifier,
    request: ClassificationRequest,
    internal_domains: list[str] | None = None,
) -> HeuristicResult:
    return classifier.classify(request, internal_domains=internal_domains or [])


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def classifier() -> HeuristicClassifier:
    return HeuristicClassifier()


# ---------------------------------------------------------------------------
# Rule 1: urgent_keyword
# ---------------------------------------------------------------------------


class TestUrgentKeyword:
    def test_urgent_uppercase_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="URGENT: contract renewal"))
        assert result.type_hint == "urgent"
        assert "urgent_keyword" in result.rules_fired
        assert result.has_opinion is True

    def test_asap_lowercase_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="please respond asap"))
        assert result.type_hint == "urgent"
        assert "urgent_keyword" in result.rules_fired

    def test_urgent_in_body_does_not_trigger(self, classifier: HeuristicClassifier) -> None:
        # The rule only checks the subject field.
        result = _classify(
            classifier,
            _make_request(subject="Quarterly update", body="This is urgent for the team"),
        )
        assert "urgent_keyword" not in result.rules_fired

    def test_immediately_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Act immediately"))
        assert result.type_hint == "urgent"
        assert "urgent_keyword" in result.rules_fired

    def test_critical_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Critical system failure"))
        assert result.type_hint == "urgent"
        assert "urgent_keyword" in result.rules_fired


# ---------------------------------------------------------------------------
# Rule 2: complaint_keyword
# ---------------------------------------------------------------------------


class TestComplaintKeyword:
    def test_dissatisfied_in_body(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(body="I am totally dissatisfied with the service."),
        )
        assert result.type_hint == "complaint"
        assert "complaint_keyword" in result.rules_fired
        assert result.has_opinion is True

    def test_refund_in_body(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(body="I need a refund for my order."),
        )
        assert result.type_hint == "complaint"
        assert "complaint_keyword" in result.rules_fired

    def test_complaint_keyword_in_subject_does_not_trigger(
        self, classifier: HeuristicClassifier
    ) -> None:
        # Rule 2 only inspects the body.
        result = _classify(
            classifier,
            _make_request(subject="refund request", body="Please help me out."),
        )
        assert "complaint_keyword" not in result.rules_fired

    def test_unacceptable_in_body(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(body="This is completely unacceptable behavior."),
        )
        assert result.type_hint == "complaint"
        assert "complaint_keyword" in result.rules_fired

    def test_terrible_in_body(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(body="The worst and terrible experience I have ever had."),
        )
        assert result.type_hint == "complaint"
        assert "complaint_keyword" in result.rules_fired


# ---------------------------------------------------------------------------
# Rule 3: internal_domain
# ---------------------------------------------------------------------------


class TestInternalDomain:
    def test_sender_domain_in_list(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="corp.internal"),
            internal_domains=["corp.internal", "subsidiary.corp"],
        )
        assert result.type_hint == "internal"
        assert "internal_domain" in result.rules_fired
        assert result.has_opinion is True

    def test_sender_domain_not_in_list(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="external.com"),
            internal_domains=["corp.internal"],
        )
        assert "internal_domain" not in result.rules_fired

    def test_empty_internal_domains_never_fires(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="corp.internal"),
            internal_domains=[],
        )
        assert "internal_domain" not in result.rules_fired
        # type_hint may be set by other rules, but not by internal_domain
        assert result.type_hint != "internal"

    def test_domain_match_is_case_insensitive(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="CORP.INTERNAL"),
            internal_domains=["corp.internal"],
        )
        assert "internal_domain" in result.rules_fired

    def test_domain_match_trims_whitespace(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="corp.internal"),
            internal_domains=["  corp.internal  "],
        )
        assert "internal_domain" in result.rules_fired


# ---------------------------------------------------------------------------
# Rule 4: spam_keyword (both groups required)
# ---------------------------------------------------------------------------


class TestSpamKeyword:
    def test_both_groups_present_triggers_spam(self, classifier: HeuristicClassifier) -> None:
        body = "Please unsubscribe or click here to stop receiving emails."
        result = _classify(classifier, _make_request(body=body))
        assert result.type_hint == "spam"
        assert "spam_keyword" in result.rules_fired
        assert result.has_opinion is True

    def test_only_unsubscribe_does_not_trigger(self, classifier: HeuristicClassifier) -> None:
        body = "To stop getting emails, click unsubscribe."
        result = _classify(classifier, _make_request(body=body))
        # "click here" is not present — group B not satisfied
        assert "spam_keyword" not in result.rules_fired

    def test_only_click_here_does_not_trigger(self, classifier: HeuristicClassifier) -> None:
        body = "Please click here for our newsletter."
        result = _classify(classifier, _make_request(body=body))
        # "unsubscribe" not present — group A not satisfied
        assert "spam_keyword" not in result.rules_fired

    def test_opt_out_satisfies_group_b(self, classifier: HeuristicClassifier) -> None:
        body = "unsubscribe at any time by choosing opt out from our list."
        result = _classify(classifier, _make_request(body=body))
        assert "spam_keyword" in result.rules_fired

    def test_opt_out_hyphenated_satisfies_group_b(self, classifier: HeuristicClassifier) -> None:
        body = "You can unsubscribe or opt-out via our preference center."
        result = _classify(classifier, _make_request(body=body))
        assert "spam_keyword" in result.rules_fired

    def test_neither_group_no_spam(self, classifier: HeuristicClassifier) -> None:
        body = "Looking forward to our meeting tomorrow."
        result = _classify(classifier, _make_request(body=body))
        assert "spam_keyword" not in result.rules_fired


# ---------------------------------------------------------------------------
# Rule 5: escalate_keyword
# ---------------------------------------------------------------------------


class TestEscalateKeyword:
    def test_legal_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Legal action pending"))
        assert result.action_hint == "escalate"
        assert "escalate_keyword" in result.rules_fired
        assert result.has_opinion is True

    def test_lawsuit_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Threatened with a lawsuit"))
        assert result.action_hint == "escalate"
        assert "escalate_keyword" in result.rules_fired

    def test_escalate_keyword_in_body_does_not_trigger(
        self, classifier: HeuristicClassifier
    ) -> None:
        # Rule 5 only inspects the subject.
        result = _classify(
            classifier,
            _make_request(subject="Hello", body="We may pursue legal action."),
        )
        assert "escalate_keyword" not in result.rules_fired

    def test_attorney_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Contact my attorney"))
        assert result.action_hint == "escalate"
        assert "escalate_keyword" in result.rules_fired

    def test_gdpr_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="GDPR data request"))
        assert result.action_hint == "escalate"
        assert "escalate_keyword" in result.rules_fired

    def test_compliance_in_subject(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request(subject="Compliance violation report"))
        assert result.action_hint == "escalate"
        assert "escalate_keyword" in result.rules_fired


# ---------------------------------------------------------------------------
# Rule 6: noreply_sender
# ---------------------------------------------------------------------------


class TestNoreplySender:
    def test_noreply_prefix(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(sender_email="noreply@example.com"),
        )
        assert result.type_hint == "notification"
        assert "noreply_sender" in result.rules_fired
        assert result.has_opinion is True

    def test_no_reply_hyphenated_prefix(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(sender_email="no-reply@test.com"),
        )
        assert result.type_hint == "notification"
        assert "noreply_sender" in result.rules_fired

    def test_normal_sender_does_not_trigger(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(sender_email="alice@example.com"),
        )
        assert "noreply_sender" not in result.rules_fired

    def test_noreply_prefix_case_insensitive(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(sender_email="NOREPLY@EXAMPLE.COM"),
        )
        assert "noreply_sender" in result.rules_fired

    def test_sender_containing_noreply_not_as_prefix_does_not_trigger(
        self, classifier: HeuristicClassifier
    ) -> None:
        # "support-noreply@example.com" does NOT start with "noreply@" or "no-reply@".
        result = _classify(
            classifier,
            _make_request(sender_email="support-noreply@example.com"),
        )
        assert "noreply_sender" not in result.rules_fired


# ---------------------------------------------------------------------------
# No rules fire
# ---------------------------------------------------------------------------


class TestNoRulesFire:
    def test_plain_email_has_no_opinion(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(
                subject="Meeting tomorrow at 3pm",
                body="Can you please confirm attendance?",
                sender_email="alice@external.com",
                sender_domain="external.com",
            ),
        )
        assert result.has_opinion is False
        assert result.action_hint is None
        assert result.type_hint is None
        assert result.rules_fired == []

    def test_result_is_heuristic_result_instance(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request())
        assert isinstance(result, HeuristicResult)

    def test_rules_fired_is_empty_list_not_none(self, classifier: HeuristicClassifier) -> None:
        result = _classify(classifier, _make_request())
        assert result.rules_fired == []
        assert isinstance(result.rules_fired, list)


# ---------------------------------------------------------------------------
# Multiple rules fire
# ---------------------------------------------------------------------------


class TestMultipleRulesFire:
    def test_urgent_and_escalate_both_fire(self, classifier: HeuristicClassifier) -> None:
        # "asap" triggers urgent_keyword; "lawsuit" triggers escalate_keyword.
        result = _classify(
            classifier,
            _make_request(subject="asap — lawsuit filed against us"),
        )
        assert "urgent_keyword" in result.rules_fired
        assert "escalate_keyword" in result.rules_fired
        assert len(result.rules_fired) == 2
        assert result.has_opinion is True
        # Last type-setting rule wins: escalate_keyword sets action_hint, not type_hint.
        # urgent_keyword sets type_hint = "urgent".
        assert result.type_hint == "urgent"
        assert result.action_hint == "escalate"

    def test_complaint_and_spam_both_fire(self, classifier: HeuristicClassifier) -> None:
        # Body has both complaint keyword and spam pair.
        body = "I am dissatisfied. Please unsubscribe me or click here to opt out."
        result = _classify(classifier, _make_request(body=body))
        assert "complaint_keyword" in result.rules_fired
        assert "spam_keyword" in result.rules_fired
        assert len(result.rules_fired) == 2

    def test_noreply_and_urgent_both_fire(self, classifier: HeuristicClassifier) -> None:
        result = _classify(
            classifier,
            _make_request(
                subject="URGENT notification",
                sender_email="noreply@system.com",
            ),
        )
        assert "urgent_keyword" in result.rules_fired
        assert "noreply_sender" in result.rules_fired
        assert result.has_opinion is True

    def test_all_rules_fired_list_grows_per_match(self, classifier: HeuristicClassifier) -> None:
        body = "I am dissatisfied. unsubscribe or click here to stop."
        result = classifier.classify(
            _make_request(
                subject="URGENT legal action asap",
                body=body,
                sender_email="noreply@corp.internal",
                sender_domain="corp.internal",
            ),
            internal_domains=["corp.internal"],
        )
        # urgent_keyword, complaint_keyword, internal_domain, spam_keyword,
        # escalate_keyword, noreply_sender — 6 rules.
        assert len(result.rules_fired) == 6
        assert "urgent_keyword" in result.rules_fired
        assert "complaint_keyword" in result.rules_fired
        assert "internal_domain" in result.rules_fired
        assert "spam_keyword" in result.rules_fired
        assert "escalate_keyword" in result.rules_fired
        assert "noreply_sender" in result.rules_fired


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    @pytest.mark.parametrize("subject", ["URGENT", "urgent", "Urgent", "uRgEnT"])
    def test_urgent_case_variants(
        self, classifier: HeuristicClassifier, subject: str
    ) -> None:
        result = _classify(classifier, _make_request(subject=subject))
        assert "urgent_keyword" in result.rules_fired

    @pytest.mark.parametrize("body", ["DISSATISFIED", "dissatisfied", "Dissatisfied"])
    def test_complaint_case_variants(
        self, classifier: HeuristicClassifier, body: str
    ) -> None:
        result = _classify(classifier, _make_request(body=body))
        assert "complaint_keyword" in result.rules_fired

    @pytest.mark.parametrize("subject", ["LEGAL", "Legal", "legal"])
    def test_escalate_case_variants(
        self, classifier: HeuristicClassifier, subject: str
    ) -> None:
        result = _classify(classifier, _make_request(subject=subject))
        assert "escalate_keyword" in result.rules_fired


# ---------------------------------------------------------------------------
# Empty internal_domains — internal_domain rule never fires
# ---------------------------------------------------------------------------


class TestEmptyInternalDomains:
    def test_empty_list_never_fires(self, classifier: HeuristicClassifier) -> None:
        result = classifier.classify(
            _make_request(sender_domain="corp.internal"),
            internal_domains=[],
        )
        assert "internal_domain" not in result.rules_fired

    def test_type_hint_not_internal_when_domains_empty(
        self, classifier: HeuristicClassifier
    ) -> None:
        result = classifier.classify(
            _make_request(sender_domain="corp.internal"),
            internal_domains=[],
        )
        assert result.type_hint != "internal"

    def test_has_opinion_false_when_only_candidate_was_internal(
        self, classifier: HeuristicClassifier
    ) -> None:
        # Only the internal_domain rule could have fired — with empty list it does not.
        result = classifier.classify(
            _make_request(
                subject="Weekly sync",
                body="Let us catch up tomorrow.",
                sender_email="alice@corp.internal",
                sender_domain="corp.internal",
            ),
            internal_domains=[],
        )
        assert result.has_opinion is False
