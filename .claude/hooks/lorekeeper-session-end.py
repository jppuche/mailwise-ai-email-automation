"""Lorekeeper hook: SessionEnd — documentation checkpoint + cross-session pending + graduation automation."""
import sys
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import date, datetime, timezone


def analyze_graduation_candidates(scratchpad_path):
    """Analyze SCRATCHPAD.md for patterns appearing in 3+ different sessions.

    Returns list of graduation candidate strings, or empty list.
    Fails silently (returns []) on any error.
    """
    try:
        with open(scratchpad_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    lines = content.splitlines()

    # Parse entries by session date (sessions start with "## YYYY-MM-DD")
    session_entries = {}  # date -> [lines]
    current_date = None

    for line in lines:
        date_match = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if date_match:
            current_date = date_match.group(1)
            session_entries.setdefault(current_date, [])
            continue
        if current_date and line.strip().startswith("- "):
            # Strip agent tags like [claude], [lorekeeper], etc.
            clean = re.sub(r"\[[\w-]+\]\s*", "", line.strip()[2:]).strip().lower()
            if len(clean) > 10:  # Skip very short entries
                session_entries[current_date].append(clean)

    if len(session_entries) < 3:
        return []  # Not enough sessions to detect patterns

    # Find phrases (bigrams) that appear across 3+ different sessions
    phrase_sessions = defaultdict(set)  # phrase -> set of dates

    for session_date, entries in session_entries.items():
        for entry in entries:
            words = re.findall(r"\b[a-z]{3,}\b", entry)
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i + 1]}"
                phrase_sessions[bigram].add(session_date)

    # Filter: 3+ different session dates, cap at 5 suggestions
    candidates = []
    for phrase, dates in sorted(phrase_sessions.items(), key=lambda x: -len(x[1])):
        if len(dates) >= 3:
            candidates.append(f'"{phrase}" (in {len(dates)} sessions)')
        if len(candidates) >= 5:
            break

    return candidates


def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd", ".")

    # Cleanup session marker (used by session-gate to detect post-compression)
    marker_path = os.path.join(cwd, ".claude", "lorekeeper-session-active.marker")
    if os.path.exists(marker_path):
        try:
            os.remove(marker_path)
        except OSError:
            pass

    pending_items = []
    today = date.today().isoformat()

    # 1. Check if SCRATCHPAD was updated today
    scratchpad_path = os.path.join(cwd, "docs", "SCRATCHPAD.md")
    if os.path.isfile(scratchpad_path):
        try:
            with open(scratchpad_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            pending_items.append(f"SCRATCHPAD.md unreadable ({e})")
            content = None

        if content is not None:
            if today not in content:
                pending_items.append("SCRATCHPAD.md not updated today — add session entry")

            line_count = len(content.splitlines())
            if line_count > 100:
                pending_items.append(
                    f"SCRATCHPAD.md at {line_count}/150 lines — review for graduation candidates"
                )
            # 1b. Check for graduation candidates (patterns across 3+ sessions)
            candidates = analyze_graduation_candidates(scratchpad_path)
            if candidates:
                pending_items.append(
                    f"SCRATCHPAD graduation candidates ({len(candidates)}): "
                    + "; ".join(candidates[:3])
                    + " — review and graduate to CLAUDE.md Learned Patterns"
                )
    else:
        pending_items.append("SCRATCHPAD.md missing")

    # 1c. Check if CHANGELOG-DEV.md was updated today
    changelog_path = os.path.join(cwd, "docs", "CHANGELOG-DEV.md")
    if os.path.isfile(changelog_path):
        try:
            with open(changelog_path, "r", encoding="utf-8") as f:
                changelog_content = f.read()
            if today not in changelog_content:
                pending_items.append(
                    "CHANGELOG-DEV.md not updated today "
                    "— add entry if significant changes were made"
                )
        except (OSError, UnicodeDecodeError):
            pass
    else:
        pending_items.append("CHANGELOG-DEV.md missing — create initial entry")

    # 2. Check CLAUDE.md line count
    claude_md_path = os.path.join(cwd, "CLAUDE.md")
    if os.path.isfile(claude_md_path):
        try:
            with open(claude_md_path, "r", encoding="utf-8") as f:
                claude_lines = len(f.readlines())
            if claude_lines > 180:
                pending_items.append(
                    f"CLAUDE.md at {claude_lines}/200 lines — prune with relevance test"
                )
        except (OSError, UnicodeDecodeError):
            pass  # Fail open — CLAUDE.md line count is advisory

    # 3. Run validate-docs.sh (safe: SessionEnd fires once per session)
    script_path = os.path.join(cwd, "scripts", "validate-docs.sh")
    validation_summary = ""
    if os.path.isfile(script_path):
        try:
            bash_cmd = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", "bash")
            result = subprocess.run(
                [bash_cmd, script_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )
            for line in result.stdout.splitlines():
                if "RESULTADO:" in line:
                    validation_summary = line.strip()
                    break
            if result.returncode != 0:
                fail_lines = [
                    l.strip() for l in result.stdout.splitlines() if "[FAIL]" in l
                ]
                for line in fail_lines[:3]:
                    pending_items.append(f"Validation: {line}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 4. Write pending items for next session (or cleanup stale)
    pending_path = os.path.join(cwd, ".claude", "lorekeeper-pending.json")
    if pending_items:
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)
        pending_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_date": today,
            "items": pending_items[:5],  # Cap to match session-gate display limit
        }
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_data, f, indent=2)
    elif os.path.exists(pending_path):
        os.remove(pending_path)

    # 5. Output summary to stderr (shown to user)
    msg = "Lorekeeper: Session end checkpoint.\n"
    if validation_summary:
        msg += f"  Docs: {validation_summary}\n"
    if pending_items:
        msg += f"  Pending items ({min(len(pending_items), 5)}) saved for next session:\n"
        for i, item in enumerate(pending_items[:5], 1):
            msg += f"    {i}. {item}\n"
        if len(pending_items) > 5:
            msg += f"    ... and {len(pending_items) - 5} more (not persisted)\n"
    else:
        msg += "  All documentation up to date.\n"

    print(msg, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
