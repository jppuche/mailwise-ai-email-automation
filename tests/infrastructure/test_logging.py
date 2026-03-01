"""Infrastructure tests for structured logging.

Validates:
  - JSON output when LOG_FORMAT=json
  - Console output when LOG_FORMAT=text
  - correlation_id injected from ContextVar
  - PII fields redacted by PiiSanitizingFilter

Capture strategy
----------------
Tests that call ``configure_logging()`` inside the test body use
``capsys`` — ``force=True`` in ``basicConfig`` recreates the handler
pointing at pytest's redirected stderr.

Tests in ``TestPiiSanitization`` call ``configure_logging()`` inside
the test body for the same reason, then parse the last JSON line from
stderr.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.core.correlation import (
    _correlation_id,
    get_correlation_id,
    set_email_correlation_id,
)
from src.core.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_correlation_id() -> None:
    """Reset correlation ID to the default between tests for determinism."""
    _correlation_id.set("no-correlation")


def _last_json_line(stderr: str) -> dict[str, object]:
    """Parse the last non-empty line of stderr as JSON.

    Raises ``AssertionError`` if stderr is empty or no valid JSON is found.
    """
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    assert lines, "Expected log output on stderr — got nothing"
    return json.loads(lines[-1])  # type: ignore[no-any-return]


class TestConfigureLogging:
    """configure_logging sets up structlog processors correctly."""

    def test_json_format_produces_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="json")
        logger = get_logger("test.json")
        logger.info("test_message", key="value")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed["event"] == "test_message"
        assert parsed["key"] == "value"

    def test_text_format_produces_readable_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="text")
        logger = get_logger("test.text")
        logger.info("readable_message")

        captured = capsys.readouterr()
        assert "readable_message" in captured.err

    def test_log_level_filters_below_threshold(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="WARNING", log_format="text")
        logger = get_logger("test.level")
        logger.info("should_not_appear")
        logger.warning("should_appear")

        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.err
        assert "should_appear" in captured.err

    def test_get_logger_returns_a_callable_logger(self) -> None:
        """get_logger returns a structlog proxy that supports .info/.warning etc.

        structlog returns a ``BoundLoggerLazyProxy`` at call time, not
        ``BoundLogger`` directly.  We test the contracted interface (the
        methods exist and are callable) rather than the internal class.
        """
        configure_logging(log_level="INFO", log_format="json")
        logger = get_logger("test.type")
        assert callable(getattr(logger, "info", None))
        assert callable(getattr(logger, "warning", None))
        assert callable(getattr(logger, "error", None))
        assert callable(getattr(logger, "debug", None))

    def test_json_output_contains_logger_name(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="json")
        logger = get_logger("mymodule.submodule")
        logger.info("named_event")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed.get("logger") == "mymodule.submodule"

    def test_json_output_contains_log_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="json")
        logger = get_logger("test.loglevel")
        logger.warning("level_test")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed.get("level") == "warning"

    def test_json_output_contains_timestamp(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="json")
        logger = get_logger("test.timestamp")
        logger.info("ts_test")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert "timestamp" in parsed


class TestCorrelationId:
    """Correlation ID injection via ContextVar."""

    def test_default_correlation_id(self) -> None:
        # Autouse fixture resets to "no-correlation" before each test
        assert get_correlation_id() == "no-correlation"

    def test_set_and_get_correlation_id(self) -> None:
        email_id = uuid.uuid4()
        set_email_correlation_id(email_id)
        assert get_correlation_id() == str(email_id)

    def test_set_stores_string_representation(self) -> None:
        email_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        set_email_correlation_id(email_id)
        result = get_correlation_id()
        assert result == "12345678-1234-5678-1234-567812345678"
        assert isinstance(result, str)

    def test_correlation_id_in_log_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="INFO", log_format="json")
        email_id = uuid.uuid4()
        set_email_correlation_id(email_id)

        logger = get_logger("test.correlation")
        logger.info("correlated_event")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed["correlation_id"] == str(email_id)

    def test_default_correlation_id_in_log_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When no ID is set, logs include the 'no-correlation' sentinel."""
        configure_logging(log_level="INFO", log_format="json")
        # Autouse fixture ensures "no-correlation" is the current value
        logger = get_logger("test.nocorr")
        logger.info("uncorrelated_event")

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed["correlation_id"] == "no-correlation"

    def test_overwriting_correlation_id(self) -> None:
        """Calling set_email_correlation_id twice uses the most recent value."""
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        set_email_correlation_id(first_id)
        set_email_correlation_id(second_id)
        assert get_correlation_id() == str(second_id)


class TestPiiSanitization:
    """PII fields are redacted from log output.

    Each test calls ``configure_logging()`` at the start of the test body
    so that ``logging.basicConfig(force=True)`` creates the StreamHandler
    after pytest has redirected sys.stderr, ensuring capsys captures output.
    """

    @pytest.mark.parametrize(
        "pii_field",
        [
            "subject",
            "from_address",
            "body_plain",
            "body_html",
            "sender_name",
            "recipient_address",
            "sender_email",
        ],
    )
    def test_pii_field_redacted(self, pii_field: str, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="DEBUG", log_format="json")
        logger = get_logger("test.pii")
        logger.info("pii_test", **{pii_field: "sensitive-data"})

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed[pii_field] == "[REDACTED]"

    def test_non_pii_field_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(log_level="DEBUG", log_format="json")
        logger = get_logger("test.pii.safe")
        logger.info("safe_test", email_id="abc-123", duration_ms=42)

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        assert parsed["email_id"] == "abc-123"
        assert parsed["duration_ms"] == 42

    def test_pii_field_value_not_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The raw PII value must not appear anywhere in the serialized log line."""
        configure_logging(log_level="DEBUG", log_format="json")
        logger = get_logger("test.pii.raw")
        secret_value = "very-secret-subject-content"
        logger.info("raw_pii_test", subject=secret_value)

        captured = capsys.readouterr()
        lines = [line for line in captured.err.strip().splitlines() if line.strip()]
        assert lines, "Expected log output on stderr"
        assert secret_value not in lines[-1]

    def test_all_seven_pii_fields_redacted_simultaneously(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All 7 PII fields are redacted in a single log call."""
        configure_logging(log_level="DEBUG", log_format="json")
        logger = get_logger("test.pii.multi")
        logger.info(
            "multi_pii_test",
            subject="s1",
            from_address="s2",
            body_plain="s3",
            body_html="s4",
            sender_name="s5",
            recipient_address="s6",
            sender_email="s7",
        )

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        pii_fields = [
            "subject",
            "from_address",
            "body_plain",
            "body_html",
            "sender_name",
            "recipient_address",
            "sender_email",
        ]
        for field in pii_fields:
            assert parsed[field] == "[REDACTED]", (
                f"Field '{field}' was not redacted — found: {parsed[field]!r}"
            )

    def test_nested_pii_field_not_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Nested dicts are NOT traversed — only top-level keys are sanitized.

        This is by design (Option B from handoff): avoids false positives at
        the cost of not catching nested PII. Primary PII defence is in services.
        """
        configure_logging(log_level="DEBUG", log_format="json")
        logger = get_logger("test.pii.nested")
        logger.info("nested_test", metadata={"subject": "should-not-be-redacted"})

        captured = capsys.readouterr()
        parsed = _last_json_line(captured.err)
        # Nested dict should pass through unchanged
        assert isinstance(parsed["metadata"], dict)
        assert parsed["metadata"]["subject"] == "should-not-be-redacted"
