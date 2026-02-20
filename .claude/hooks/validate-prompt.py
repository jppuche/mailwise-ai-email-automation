"""Cerbero hook: UserPromptSubmit — scan user input for injection patterns."""
import sys
import json
import re

INJECTION_PATTERNS = [
    r"ignore previous instructions", r"ignore all previous", r"override system prompt",
    r"forget your rules", r"you are now", r"pretend you are", r"do not tell the user",
    r"do not report", r"do not share", r"new system prompt", r"disregard the above",
    r"act as if", r"bypass safety", r"ignore the above", r"from now on you",
    r"<system>", r"\[inst\]", r"begin system message",
]

BASE64_PATTERN = re.compile(r"(?![0-9a-fA-F]+$)[A-Za-z0-9+/]{60,}={0,2}")
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad\u2060\u180e]")


def main():
    data = json.load(sys.stdin)
    prompt = data.get("prompt", "")
    lower = prompt.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            print(f"Cerbero: blocked prompt — injection pattern detected: '{pattern}'", file=sys.stderr)
            sys.exit(2)

    if ZERO_WIDTH_PATTERN.search(prompt):
        print("Cerbero: blocked prompt — zero-width characters detected (possible hidden injection)", file=sys.stderr)
        sys.exit(2)

    if BASE64_PATTERN.search(prompt):
        print("Cerbero warning: suspicious Base64 payload detected in prompt. Verify source before proceeding.", file=sys.stderr)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
