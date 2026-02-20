"""Lorekeeper hook: SessionStart — real-time doc evaluation + cross-session pending + version check.

Also fires post-compression (compact). Uses a session marker file to detect
re-injection and remind the agent to persist any undocumented insights.
Pending file is NOT deleted here — session-end handles cleanup. This allows
re-injection after context compression in long sessions.
"""
import sys
import json
import os
import re
from datetime import date

HOOK_VERSION = "1.2.0"


def _version_tuple(v):
    """Convert version string to comparable tuple. Returns (0,0,0) on error."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _read_file_safe(path):
    """Read file content. Returns (content, error_msg). Fail-open."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    except OSError as e:
        return None, str(e)
    except UnicodeDecodeError:
        return None, "encoding error (not UTF-8)"


def _evaluate_scratchpad(cwd, today):
    """Evaluate SCRATCHPAD.md status. Returns dict with findings."""
    path = os.path.join(cwd, "docs", "SCRATCHPAD.md")
    result = {"exists": False, "line_count": 0, "has_today": False, "actions": []}

    if not os.path.exists(path):
        result["actions"].append(
            "SCRATCHPAD.md missing — create with session template"
        )
        return result

    content, err = _read_file_safe(path)
    if content is None:
        result["actions"].append(f"SCRATCHPAD.md unreadable ({err})")
        return result

    result["exists"] = True
    result["line_count"] = len(content.splitlines())
    result["has_today"] = today in content

    if result["line_count"] > 100:
        result["actions"].append(
            f"SCRATCHPAD.md at {result['line_count']}/150 lines "
            "— graduate repeated patterns to CLAUDE.md Learned Patterns"
        )
    if not result["has_today"]:
        result["actions"].append(
            "SCRATCHPAD.md has no entry for today — create session section with template"
        )

    return result


def _evaluate_changelog(cwd, today):
    """Evaluate CHANGELOG-DEV.md status. Returns dict with findings."""
    path = os.path.join(cwd, "docs", "CHANGELOG-DEV.md")
    result = {"exists": False, "has_today": False, "actions": []}

    if not os.path.exists(path):
        result["actions"].append(
            "CHANGELOG-DEV.md missing — create initial entry"
        )
        return result

    content, err = _read_file_safe(path)
    if content is None:
        result["actions"].append(f"CHANGELOG-DEV.md unreadable ({err})")
        return result

    result["exists"] = True
    result["has_today"] = today in content
    # No action at session start for changelog — checked at commit-gate and session-end
    return result


def _extract_current_phase(cwd):
    """Extract current phase description from STATUS.md. Returns string or None."""
    path = os.path.join(cwd, "docs", "STATUS.md")
    content, _ = _read_file_safe(path)
    if not content:
        return None

    lines = content.splitlines()
    in_phase_section = False
    for line in lines:
        if re.match(r"^##\s+(Fase actual|Current phase)", line, re.IGNORECASE):
            in_phase_section = True
            continue
        if in_phase_section:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
            if stripped.startswith("#"):
                break  # Next section reached
    return None


def _extract_pending_tasks(cwd, max_items=5):
    """Extract unchecked tasks from STATUS.md. Returns list of strings."""
    path = os.path.join(cwd, "docs", "STATUS.md")
    content, _ = _read_file_safe(path)
    if not content:
        return []

    tasks = []
    for line in content.splitlines():
        match = re.match(r"^\s*-\s*\[\s*\]\s+(.+)", line)
        if match:
            tasks.append(match.group(1).strip())
            if len(tasks) >= max_items:
                break
    return tasks


def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd", ".")

    # Detect if this is a post-compression re-injection
    # Marker stored in .claude/ (project-scoped) to avoid cross-project false positives
    marker_path = os.path.join(cwd, ".claude", "lorekeeper-session-active.marker")
    is_post_compression = False
    if os.path.exists(marker_path):
        # Check marker age — stale markers (>24h) indicate a crash, not compression
        try:
            marker_age = (date.today() - date.fromisoformat(
                open(marker_path, "r").read().strip()[:10]
            )).days
            is_post_compression = marker_age < 1
        except (ValueError, OSError):
            is_post_compression = False  # Unreadable marker — treat as stale

    if not is_post_compression:
        # First invocation this session — create marker with timestamp
        try:
            os.makedirs(os.path.dirname(marker_path), exist_ok=True)
            with open(marker_path, "w") as f:
                f.write(date.today().isoformat())
        except OSError as e:
            print(f"Lorekeeper: marker creation failed at {marker_path}: {e}", file=sys.stderr)

    # Check for pending work from previous session
    pending_path = os.path.join(cwd, ".claude", "lorekeeper-pending.json")
    pending_items = []
    if os.path.exists(pending_path):
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                pending = json.load(f)
            pending_items = pending.get("items", [])
            # Don't delete — session-end handles cleanup.
            # Keeps file available for re-injection after context compression.
        except (json.JSONDecodeError, OSError):
            pass

    # Check for version drift (hook updated but project config stale)
    version_msg = ""
    version_path = os.path.join(cwd, ".claude", "ignite-version.json")
    if os.path.exists(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            installed_version = version_data.get("version", "0.0.0")
            installed_date = version_data.get("installed_date", "")

            if _version_tuple(HOOK_VERSION) > _version_tuple(installed_version):
                version_msg = (
                    f"Ignite update: hooks are v{HOOK_VERSION} but project config "
                    f"is from v{installed_version}. Consider re-running "
                    "/project-workflow-init to update generated files."
                )

            # Age check: if installed > 30 days ago
            if installed_date and not version_msg:
                try:
                    inst_date = date.fromisoformat(installed_date)
                    days_old = (date.today() - inst_date).days
                    if days_old > 30:
                        version_msg = (
                            f"Ignite config is {days_old} days old "
                            f"(installed {installed_date}). Check for updates."
                        )
                except ValueError:
                    pass
        except (json.JSONDecodeError, OSError, KeyError):
            pass  # Fail open

    # Phase transition reminder
    phase_reminder = ""
    status_path = os.path.join(cwd, "docs", "STATUS.md")
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                status_content = f.read()
            phase_0_done = re.search(
                r"(Phase 0|Fase 0|Foundation|Fundamentos).*?"
                r"(completad|complete|done|\[x\])",
                status_content, re.IGNORECASE
            )
            phase_1_not_started = not re.search(
                r"(Phase 1|Fase 1|Technical Landscape|Panorama).*?"
                r"(completad|complete|done|in.progress|en.curso|\[x\])",
                status_content, re.IGNORECASE
            )
            if phase_0_done and phase_1_not_started:
                days_since = ""
                if os.path.exists(version_path):
                    try:
                        with open(version_path, "r", encoding="utf-8") as f:
                            vdata = json.load(f)
                        installed = vdata.get("installed_date", "")
                        if installed:
                            try:
                                delta = (date.today() - date.fromisoformat(installed)).days
                                if delta > 0:
                                    days_since = f" ({delta} day{'s' if delta != 1 else ''} ago)"
                            except ValueError:
                                pass
                    except (json.JSONDecodeError, OSError):
                        pass
                phase_reminder = (
                    f"Phase 0: Foundation completed{days_since}. "
                    "Phase 1: Technical Landscape is pending — "
                    "stack decisions, validation tools, ecosystem scan. "
                    "See _workflow/guides/workflow-guide.md (Phase 1) for details."
                )
        except OSError:
            pass  # Fail open

    # --- Real-time file evaluation ---
    today = date.today().isoformat()
    scratchpad_eval = _evaluate_scratchpad(cwd, today)
    changelog_eval = _evaluate_changelog(cwd, today)
    current_phase = _extract_current_phase(cwd)
    pending_tasks = _extract_pending_tasks(cwd)

    # Build REQUIRED ACTIONS (prioritized)
    required_actions = []
    # Priority 1: Pending items from previous session
    for item in pending_items[:5]:
        required_actions.append(item)
    # Priority 2: Scratchpad actions
    for action in scratchpad_eval["actions"]:
        required_actions.append(action)
    # Priority 3: Changelog actions
    for action in changelog_eval["actions"]:
        required_actions.append(action)

    # --- Build structured message ---
    if is_post_compression:
        msg = (
            "Lorekeeper SESSION PROTOCOL [post-compression] — MANDATORY before any work:\n\n"
            "RECOVERY ACTION:\n"
            "  Context was compressed. Verify that insights from before compression\n"
            "  are persisted in docs/SCRATCHPAD.md — conversational context is now\n"
            "  reduced to a summary and details may be lost.\n"
        )
    else:
        msg = "Lorekeeper SESSION PROTOCOL — MANDATORY before any work:\n"

    if required_actions:
        msg += "\nREQUIRED ACTIONS (do these FIRST):\n"
        for i, action in enumerate(required_actions[:8], 1):
            msg += f"  {i}. {action}\n"

    msg += "\nSESSION CONTEXT:\n"
    if scratchpad_eval["exists"]:
        msg += f"  SCRATCHPAD: {scratchpad_eval['line_count']}/150 lines\n"
    else:
        msg += "  SCRATCHPAD: missing\n"
    if current_phase:
        msg += f"  Current phase: {current_phase}\n"
    if pending_tasks:
        msg += f"  Pending tasks from STATUS.md:\n"
        for task in pending_tasks:
            msg += f"    - {task}\n"

    if version_msg:
        msg += f"\n  {version_msg}\n"

    if phase_reminder:
        msg += f"\n  {phase_reminder}\n"

    msg += "\nREMINDERS:\n"
    msg += "  - Update SCRATCHPAD with errors/corrections/discoveries AS THEY HAPPEN (not at the end)\n"
    msg += "  - Run `bash scripts/validate-docs.sh` before every commit\n"
    msg += "  - Update CHANGELOG-DEV.md if significant changes are made\n"

    # Output structured JSON — additionalContext goes directly into Claude's context
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": msg,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
