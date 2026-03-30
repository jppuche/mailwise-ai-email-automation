import pytest

from src.core.sanitizer import SanitizedText, sanitize_email_body


class TestStripHtml:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("<b>hello</b>", "hello"),
            ("<p>Hello <br>World</p>", "Hello World"),
            ("<div><span>nested</span></div>", "nested"),
            ('<a href="http://example.com">link</a>', "link"),
            ("plain text", "plain text"),
            ("", ""),
        ],
    )
    def test_html_stripped(self, raw: str, expected: str) -> None:
        result = sanitize_email_body(raw, max_length=4000)
        assert result == expected

    def test_strip_html_false_preserves_tags(self) -> None:
        result = sanitize_email_body("<b>hello</b>", max_length=4000, strip_html=False)
        assert result == "<b>hello</b>"


class TestUnicodeRemoval:
    def test_removes_zero_width_space(self) -> None:
        result = sanitize_email_body("hel\u200blo", max_length=4000)
        assert result == "hello"

    def test_removes_zero_width_non_joiner(self) -> None:
        result = sanitize_email_body("hel\u200clo", max_length=4000)
        assert result == "hello"

    def test_removes_zero_width_joiner(self) -> None:
        result = sanitize_email_body("hel\u200dlo", max_length=4000)
        assert result == "hello"

    def test_removes_left_to_right_mark(self) -> None:
        result = sanitize_email_body("hel\u200elo", max_length=4000)
        assert result == "hello"

    def test_removes_right_to_left_mark(self) -> None:
        result = sanitize_email_body("hel\u200flo", max_length=4000)
        assert result == "hello"

    def test_removes_word_joiner(self) -> None:
        result = sanitize_email_body("hel\u2060lo", max_length=4000)
        assert result == "hello"

    def test_removes_bom(self) -> None:
        result = sanitize_email_body("\ufeffhello", max_length=4000)
        assert result == "hello"

    def test_removes_soft_hyphen(self) -> None:
        result = sanitize_email_body("hel\u00adlo", max_length=4000)
        assert result == "hello"

    def test_removes_tag_characters(self) -> None:
        # U+E0001 is a tag character
        result = sanitize_email_body("hel\U000e0001lo", max_length=4000)
        assert result == "hello"


class TestTruncation:
    def test_truncates_to_exact_max_length(self) -> None:
        text = "a" * 5000
        result = sanitize_email_body(text, max_length=4000)
        assert len(result) == 4000

    def test_no_truncation_under_max(self) -> None:
        text = "a" * 3000
        result = sanitize_email_body(text, max_length=4000)
        assert len(result) == 3000

    def test_exact_max_length_unchanged(self) -> None:
        text = "a" * 4000
        result = sanitize_email_body(text, max_length=4000)
        assert len(result) == 4000


class TestEdgeCases:
    def test_empty_string(self) -> None:
        result = sanitize_email_body("", max_length=4000)
        assert result == ""

    def test_clean_text_preserved(self) -> None:
        text = "Hello, World! This is clean text with numbers 123 and symbols @#$."
        result = sanitize_email_body(text, max_length=4000)
        assert result == text

    def test_return_type_is_str(self) -> None:
        # At runtime, NewType is transparent — SanitizedText IS str.
        # mypy enforces the distinction at compile time.
        result = sanitize_email_body("hello", max_length=4000)
        assert isinstance(result, str)

    def test_return_type_annotation(self) -> None:
        # Verify the function signature returns SanitizedText
        annotations = sanitize_email_body.__annotations__
        assert annotations["return"] is SanitizedText
