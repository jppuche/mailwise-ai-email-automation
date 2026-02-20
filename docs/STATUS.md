# Project Status — mailwise

**Last updated:** 2026-02-20

## Current phase

Phase N: Development Blocks (Phase 4 complete — ready to build)

## Completed

- [x] Phase 0: Foundation (directory structure, CLAUDE.md, hooks, Cerbero)
- [x] Phase 1: Technical Landscape (15 tech decisions, ecosystem scan)
- [x] Phase 2: Tooling & Security (8 candidates evaluated, 2 approved, 3 rejected, 1 deferred, 2 skipped)
- [x] Phase 3: Strategic Review (15 confirmed, 6 adjusted, 18 architecture directives, agent composition confirmed)
- [x] Phase 4: Architecture Blueprint (20 block specs, Sentinel security review: 0 critical, 3 warnings, 5 suggestions)
- [x] Phase 5: Team Assembly (5 agents installed, 7 skills assigned, Section 13 populated)

## Pending

- [ ] Phase N: Development Blocks (start with block-00-scaffolding)

## Blockers

None

## Notes

- Dual objective: portfolio (AI Engineer) + consultant showcase
- Phase order: 2→3→5→4 (agents before specs)
- Phase 4 security review: docs/reviews/phase-4-security-review.md
- D16 corrected: 5-layer prompt injection defense (Sec 11.2 + Sec 4.5) — DECISIONS.md updated

## Team & Tooling

### Agents
| Agent | Model | Role |
|-------|-------|------|
| Lorekeeper | sonnet | Docs, CLAUDE.md, compound engineering |
| Inquisidor | sonnet | Tests, type precision, exception audit |
| Sentinel | opus | Security, contracts, fragility analysis |
| backend-worker | sonnet | API, services, adapters, models |
| frontend-worker | sonnet | Dashboard SPA, components, styles |

### Tier 1 — Core Tools
| Tool | Status | Notes |
|------|--------|-------|
| mcp-scan | Installed | --opt-out, scan-only, uvx |
| claude-code-security-review | Approved | GitHub Action, install when CI has PRs |

### Tier 2 — Specialist Tools (INSTALLED)
| Tool | Status | Agent | Notes |
|------|--------|-------|-------|
| honnibal/tighten-types | Installed | Inquisidor | Type precision for Pydantic/adapters |
| honnibal/try-except | Installed | Inquisidor | Exception audit for Celery/integrations |
| honnibal/contract-docstrings | Installed | Sentinel | Adapter boundary contracts |
| honnibal/pre-mortem | Installed | Sentinel | Pipeline fragility analysis |
| honnibal/alignment-chart | Installed | Inquisidor | Function/test categorization |
| honnibal/concept-analysis | Installed | Lorekeeper | Domain glossary, naming consistency |

### Rejected: PostgreSQL MCP (SQLi), SAST MCP (untrusted), HubSpot MCP (deferred), Slack MCP (redundant), laurigates skill (redundant)
