# mailwise

Intelligent Email Classification and Routing System

## Stack

Python

## Getting Started

<!-- TODO: Add specific setup instructions for your project -->

## Development Workflow

This project uses the Ignite workflow methodology. Each phase has clear exit
conditions — don't advance until they're met.

| Phase | Purpose | Status |
|-------|---------|--------|
| 0. Foundation | Project structure, memory, automation | Done |
| 1. Technical Landscape | Stack decisions, tools, ecosystem scan | **Next** |
| 2. Tooling & Security | Evaluate and install skills/MCPs | Pending |
| 3. Strategic Review | Architecture assessment (with installed tools) | Pending |
| 4. Architecture Blueprint | Detailed design, feature specs | Pending |
| 5. Team Assembly | Configure agents, assign roles | Pending |
| N. Development Blocks | Build features with Ralph Loop | Pending |
| Final. Hardening | Security audit, performance, production | Pending |

Current status: `docs/STATUS.md`

### Key Principles

- **Context is scarce** — Keep CLAUDE.md under 200 lines. Use `/compact` at 60-70%.
- **Verification gates** — Typecheck + lint + test must pass before advancing.
- **Compound learning** — Mistakes recorded in SCRATCHPAD.md, patterns graduate to CLAUDE.md.
- **Ask before assuming** — Document decisions in docs/DECISIONS.md.

Full workflow guide: `_workflow/guides/workflow-guide.md`

## After Setup — What to Customize

1. **CLAUDE.md** — Fill in the `Style` and `Architecture` sections
2. **Agents** — Adapt domain paths in `.claude/agents/` to your project layout
3. **Styling rule** — Define design tokens in `.claude/rules/styling.md` (if applicable)

## Project Structure

- `CLAUDE.md` — Project memory for Claude Code (< 200 lines)
- `docs/STATUS.md` — Current project status and phase
- `docs/DECISIONS.md` — Technical decisions log (append-only)
- `docs/SCRATCHPAD.md` — Session learning log (compound engineering)
- `docs/specs/` — Feature specifications
- `scripts/validate-docs.sh` — Automated documentation validation
- `_workflow/guides/` — Workflow reference documentation

## Reference

- Workflow methodology: `_workflow/guides/workflow-guide.md`
- Ignite reference: `docs/ignite-reference.md`

---

*Initialized on 2026-02-19 with Ignite*
