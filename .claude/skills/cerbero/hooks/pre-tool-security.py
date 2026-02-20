"""Cerbero hook: PreToolUse — block dangerous shell commands."""
import sys
import json
import re

DANGEROUS_PATTERNS = [
    (r"rm\s+-rf?", "recursive delete"),
    (r"mkfs\.", "filesystem format"),
    (r"dd\s+if=", "disk overwrite"),
    (r"chmod\s+777", "world-writable permissions"),
    (r":\(\)\s*\{.*:\|:&\s*\}\s*;:", "fork bomb"),
    (r"curl.*\|.*sh", "remote code execution via curl|sh"),
    (r"wget.*\|.*sh", "remote code execution via wget|sh"),
    (r"nc\s+-e", "reverse shell via netcat"),
    (r"python.*-c.*import\s+os.*\b(system|exec|popen|spawn)\b", "Python OS command execution"),
    (r"Invoke-WebRequest.*\|.*iex", "PowerShell remote execution"),
    (r"iex\s*\(", "PowerShell Invoke-Expression"),
    (r"Start-Process.*-NoNewWindow", "hidden process execution"),
]

WARNING_PATTERNS = [
    (r"curl\s+.*-o\s", "download to disk via curl -o"),
    (r"curl\s+.*--output\s", "download to disk via curl --output"),
    (r"wget\s+.*-O\s", "download to disk via wget -O"),
    (r"wget\s+.*--output-document", "download to disk via wget --output-document"),
    (r"Invoke-WebRequest.*-OutFile", "download to disk via Invoke-WebRequest"),
]


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")

    for pattern, desc in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            json.dump({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Cerbero: blocked dangerous command ({desc})"
                }
            }, sys.stdout)
            sys.exit(0)

    for pattern, desc in WARNING_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"Cerbero WARNING: detected {desc}. Verify download source and destination.", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
