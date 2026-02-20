"""Cerbero hook: PreToolUse — audit trail for MCP tool invocations."""
import sys
import json
import os
from datetime import datetime, timezone


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "unknown")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", ".")

    log_dir = os.path.join(cwd, ".claude", "security")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "mcp-audit.log")

    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": tool_name,
        "input_keys": sorted(tool_input.keys()),
        "session": data.get("session_id", "unknown"),
    }

    # Log rotation: truncate to last 500 entries if over 1MB
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > 1_000_000:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(log_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-500:])
    except OSError:
        pass  # Fail open on rotation errors

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    counter_path = os.path.join(log_dir, "invocation-counter.txt")
    count = 0
    if os.path.exists(counter_path):
        try:
            count = int(open(counter_path, "r").read().strip())
        except (ValueError, OSError):
            count = 0
    count += 1
    with open(counter_path, "w", encoding="utf-8") as cf:
        cf.write(str(count))
    if count % 50 == 0:
        print(f"Cerbero: {count} MCP invocations since last reset. Consider running /cerbero verify.", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
