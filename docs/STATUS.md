# Project Status — mailwise

**Last updated:** 2026-02-28

## Current phase

Phase N: Development Blocks (Phase 4 complete — ready to build)

## Completed

- [x] Phase 0: Foundation (directory structure, CLAUDE.md, hooks, Cerbero)
- [x] Phase 1: Technical Landscape (15 tech decisions, ecosystem scan)
- [x] Phase 2: Tooling & Security (8 evaluated, 2 approved, 3 rejected, 1 deferred)
- [x] Phase 3: Strategic Review (15 confirmed, 6 adjusted, 18 directives)
- [x] Phase 4: Architecture Blueprint (20 block specs, Sentinel review: 0 critical)
- [x] Phase 5: Team Assembly (5 agents, 7 skills, Section 13 populated)

## In Progress

- [ ] Block 07: Ingestion Pipeline (next)
- [ ] Blocks 08-19 (pending)

## Recently Completed

- [x] Block 06: HubSpot CRM Adapter (HubSpotAdapter, 7 methods, 170 tests, 637 total)
- [x] Block 05: Slack Channel Adapter (SlackAdapter, Block Kit formatter, 103 tests, 467 total)
- [x] Block 04: LLM Adapter (LiteLLMAdapter, 7-shape parser, 106 tests, 364 total)
- [x] Block 03: Gmail Adapter (ABC + GmailAdapter, 85 tests, 258 total)
- [x] Block 02: Auth & Users (JWT+bcrypt, Redis refresh tokens, RBAC, 231 tests)
- [x] Block 01: Database Models (9 models, 132 tests, Sentinel pass)
- [x] Block 00: Scaffolding (Docker 4/6 healthy)

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

Rejected: PostgreSQL MCP, SAST MCP, HubSpot MCP (deferred), Slack MCP, laurigates skill
