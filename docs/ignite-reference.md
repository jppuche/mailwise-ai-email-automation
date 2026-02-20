# Ignite Workflow Reference — mailwise

> Quick reference for the Ignite methodology installed in this project.
> Full guide: `_workflow/guides/workflow-guide.md`

## Workflow Phases

| Phase | Purpose | Key Output |
|-------|---------|------------|
| 0. Foundation | Project structure, memory, automation | CLAUDE.md, hooks, rules, CI/CD |
| 1. Technical Landscape | Stack decisions, validation tools, ecosystem scan | DECISIONS.md entries, tool candidates |
| 2. Tooling & Security | Evaluate and install skills/MCPs via Cerbero | Installed tools, security audit |
| 3. Strategic Review | Architecture assessment with installed tools | Architecture doc, confirmed decisions |
| 4. Architecture Blueprint | Detailed design, feature specifications | Block specs in docs/specs/ |
| 5. Team Assembly | Configure agents, assign skills and roles | Agent configs, skill mapping |
| N. Development Blocks | Build features with Ralph Loop | Working features, passing tests |
| Final. Hardening | Security audit, performance, production readiness | Production-ready system |

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project memory (< 200 lines) |
| `docs/STATUS.md` | Current phase and status |
| `docs/DECISIONS.md` | Decision log (append-only) |
| `docs/SCRATCHPAD.md` | Session learning log |
| `docs/CHANGELOG-DEV.md` | Development changelog |
| `docs/LESSONS-LEARNED.md` | Incident post-mortems |
| `docs/AGENT-COORDINATION.md` | Multi-agent coordination protocol |
| `.claude/quality-gate.json` | Quality gate command config |

## Hooks (automated)

| Hook | Event | Purpose |
|------|-------|---------|
| lorekeeper-session-gate.py | SessionStart | Injects context + required actions |
| lorekeeper-commit-gate.py | PreToolUse | Blocks commits if docs stale |
| lorekeeper-session-end.py | SessionEnd | Checkpoint + pending items |
| code-quality-gate.py | PreToolUse | Runs typecheck/lint/test before commit |
| validate-prompt.py | UserPromptSubmit | Prompt injection defense |
| pre-tool-security.py | PreToolUse | Blocks dangerous commands |
| mcp-audit.py | PreToolUse | Audits MCP tool calls |

## Compound Engineering Cycle

```
SCRATCHPAD.md (session) → pattern repeats 3+ times → CLAUDE.md "Learned Patterns"
```

1. **Record** — Log errors, corrections, discoveries in SCRATCHPAD.md
2. **Detect** — Pattern appears 3+ times = graduation candidate
3. **Graduate** — Move to CLAUDE.md Learned Patterns section
4. **Prune** — Remove graduated entries from SCRATCHPAD.md

## Installed Version

- Ignite: 1.2.0
- Installed: 2026-02-19
- Profile: Python (generic)
