# Project Status — mailwise

**Last updated:** 2026-03-01

## Current phase

All 20 development blocks (B00-B19) complete. Ready for final review and deployment.

## Completed

- [x] Phases 0-5: Foundation, Landscape, Tooling, Review, Blueprint, Team Assembly

## Recently Completed

- [x] Block 19: Deployment & Docs — Structured logging, Docker health checks (6 services), .env.example (60+ vars), deployment guide, adapter guide, 40 infra tests, 1487 total
- [x] Block 18: E2E Tests — 18 E2E tests, 9 factories, pipeline + API integration coverage, 1504 total backend
- [x] Block 17: Frontend Remaining — Routing Rules, Integrations, Analytics, Overview, Logs (5 pages, 10 components, 5 hooks, 5 API modules, 200 new tests, 342 total frontend)
- [x] Block 16: Frontend Core — Email Browser, Review Queue, Classification Config (4 pages, 7 components, 4 hooks, 25 API fns, 142 tests total)
- [x] Block 15: Frontend SPA — Auth & Email List (auth + shell + 27 tests; email list delivered in B16)
- [x] Block 14: Analytics & Admin Endpoints (4 routers, 26 endpoints, 3 services, 139 tests, 1616 total)
- [x] Block 13: API Endpoints (4 routers, 22 endpoints, exception handlers, 110 tests, 1477 total)
- [x] Block 12: Pipeline & Scheduler (Celery 5-task chain, APScheduler, Redis lock, 172 tests, 1367 total)
- [x] Block 11: Draft Generation (DraftContextBuilder, DraftGenerationService, Gmail push, 138 tests, 1195 total)
- [x] Block 10: CRM Sync Service (CRMSyncService, 6-op chain, idempotent, 57 tests, 1057 total)
- [x] Block 09: Routing Service (RoutingService, RuleEngine, 6 operators, idempotent dispatch, 135 tests, 1000 total)
- [x] Block 08: Classification Service (PromptBuilder, HeuristicClassifier, 5-layer defense, 175 tests, 865 total)
- [x] Block 07: Ingestion Pipeline (IngestionService, dedup, thread-aware, 53 tests, 690 total)
- [x] Block 06: HubSpot CRM Adapter (HubSpotAdapter, 7 methods, 170 tests, 637 total)
- [x] Block 05: Slack Channel Adapter (SlackAdapter, Block Kit formatter, 103 tests, 467 total)
- [x] Block 04: LLM Adapter (LiteLLMAdapter, 7-shape parser, 106 tests, 364 total)
- [x] Blocks 00-03: Scaffolding, DB Models, Auth & Users, Gmail Adapter (258 tests)

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
| honnibal/concept-analysis | Installed | Lorekeeper | Domain glossary, naming consistency | <!-- Rejected: PostgreSQL MCP, SAST MCP, HubSpot MCP (deferred), Slack MCP, laurigates skill -->
