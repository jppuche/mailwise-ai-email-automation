from html.parser import HTMLParser
from typing import NewType

SanitizedText = NewType("SanitizedText", str)

# Pre-compiled removal table for invisible Unicode characters.
# Ranges: U+200B-200F (zero-width), U+2060-2064 (word joiner family),
# U+E0000-E007F (tag characters), U+FEFF (BOM), U+00AD (soft hyphen).
_INVISIBLE_RANGES: list[range | list[int]] = [
    range(0x200B, 0x2010),
    range(0x2060, 0x2065),
    range(0xE0000, 0xE0080),
    [0xFEFF],
    [0x00AD],
]
_REMOVAL_TABLE = str.maketrans("", "", "".join(chr(cp) for r in _INVISIBLE_RANGES for cp in r))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def sanitize_email_body(
    raw_body: str,
    *,
    max_length: int,
    strip_html: bool = True,
) -> SanitizedText:
    """Sanitize email body text for downstream processing.

    Invariants (input):
      - raw_body: str, may be empty, may contain HTML, may contain invisible Unicode.
      - max_length: positive int. Defined by Settings.max_body_length.

    Guarantees (output):
      - Returns SanitizedText (str with branded type).
      - No HTML tags if strip_html=True.
      - No invisible Unicode characters from the documented ranges.
      - Length <= max_length characters.
      - Never raises — pure local computation (D8: conditionals, not try/except).

    Errors: None — if raw_body is invalid, returns SanitizedText("").
    State transitions: None — pure function with no side effects.
    """
    if not raw_body:
        return SanitizedText("")

    text = raw_body

    if strip_html:
        extractor = _TextExtractor()
        extractor.feed(text)
        text = extractor.get_text()

    text = text.translate(_REMOVAL_TABLE)

    if len(text) > max_length:
        text = text[:max_length]

    return SanitizedText(text)
