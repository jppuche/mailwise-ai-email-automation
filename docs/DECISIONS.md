# Technical Decisions — mailwise

> Append-only. One entry per decision. Never delete previous entries.
> Note: Section headings (Candidate Ecosystem Catalog, Strategic Assessment, etc.) are anchor names — keep in English regardless of language. Adapt only descriptive text within sections.

| Date | Decision | Context | Alternatives discarded |
|------|----------|---------|------------------------|
| 2026-02-19 | Initial project setup | .claude/ + docs/ structure | -- |
| 2026-02-19 | Generalist agents pre-selected | Lorekeeper + Inquisidor + Sentinel for Phase 5 | Lorekeeper only |
| 2026-02-19 | Agent Teams enabled | Multi-agent coordination for future full-stack development | Disabled |
| 2026-02-19 | Cerbero security framework enabled | OWASP MCP Top 10 coverage + mcp-scan evaluation in Phase 2 | No security framework |
| 2026-02-20 | Dual objective: portfolio + consultant showcase | Code as replicable template (adapter swapping) + methodology as process showcase (FOUNDATION.md + specs). Architecture must be clean enough to serve as reference implementation. | Portfolio only |
| 2026-02-20 | Phase order adjusted: 2→3→5→4 | Install agents (Phase 5) before writing block specs (Phase 4) so Sentinel reviews security specs and Inquisidor validates testing exit conditions with specialized knowledge | Original order 2→3→4→5 |
| 2026-02-20 | Backend framework: FastAPI | Async native, auto OpenAPI docs (portfolio differentiator), Pydantic validates Appendix B contracts, <500ms API target (Sec 12.1). Dependency injection maps to adapter pattern (Sec 9). | Django + DRF (sync by default, admin overlaps dashboard), Flask (more assembly, no auto docs) |
| 2026-02-20 | Database: PostgreSQL | Relational integrity for email→classification→routing FK chains. JSONB for semi-structured data (LLM raw output, routing payloads). pg_trgm for search <5s over 100K emails (Sec 12.1). Docker Compose makes setup trivial. | SQLite (no concurrent writes for background workers), MongoDB (overkill, less portfolio signal for relational) |
| 2026-02-20 | ORM: SQLAlchemy 2.0 (async) + Alembic | Industry standard. Async via asyncpg driver for FastAPI. Auto-migrations on startup (Sec 12.5). Type-annotated models align with CLAUDE.md style. Model definitions document Appendix B contracts. | Tortoise ORM (smaller ecosystem), raw asyncpg (no migrations, tedious CRUD) |
| 2026-02-20 | Frontend: React + Vite + TypeScript | SPA required for complex dashboard UI: drag-to-reorder routing rules, side-by-side email/draft review, real-time charts, search/filter (Sec 8.1). Highest portfolio signal. TypeScript enforces Appendix B contracts on frontend. CSS variables enable dark mode from day 1 (Tier 2). | Jinja2 + HTMX (limited interactivity for drag-reorder/charts), Vue 3 (smaller job market) |
| 2026-02-20 | Task queue: Celery + Redis | Native retry with exponential backoff (Sec 5.5, 6.4, 10.1). Task chaining for email state machine (FETCHED→CLASSIFIED→ROUTED→...). Redis doubles as classification cache (Sec 10.6) and session store. Professional appearance for consultant showcase. | asyncio + tenacity (simpler but no persistent queue, tasks lost on restart), arq (lighter but smaller community) |
| 2026-02-20 | Scheduler: APScheduler (in dedicated container) | Lightweight cron-like polling at 5-min interval (Sec 3.2). Runs in dedicated container to prevent duplicate polls if API scales. | Celery Beat (heavier, couples scheduling to Celery), cron (not portable) |
| 2026-02-20 | LLM integration: LiteLLM | Unified completion() for OpenAI/Anthropic/Ollama (Sec 9.5). Easy model switching (lesson 14.3.2: thinking-mode models break parsers). Config-level model change, not code change. Different models for classification (cheap, temp 0.1) vs drafts (capable, temp 0.7) per Appendix C. | Official SDKs (two SDKs to maintain), LangChain (over-engineered, heavy deps, frequent breaking changes) |
| 2026-02-20 | Email SDK: google-api-python-client + google-auth-oauthlib | Official Google SDK. OAuth2 with token refresh (Sec 11.3). Minimum scopes: gmail.readonly + gmail.modify + gmail.compose. Proven in predecessor project. | simplegmail (unmaintained) |
| 2026-02-20 | Notification SDK: slack-sdk (official) | AsyncWebClient for FastAPI. Block Kit formatting for structured routing notifications (Sec 5.4 payload). Built-in rate limit handling (Sec 5.5). | slack-bolt (overkill for sending notifications), httpx direct (must handle auth/rate-limiting manually) |
| 2026-02-20 | CRM: HubSpot (hubspot-api-client) | Free tier available for testing — portfolio reviewers can actually run the system. Official Python SDK covers all Sec 6.2 operations. REST-native API. Adapter pattern means Salesforce can be added later without core changes. | Salesforce/simple-salesforce (complex auth, no free tier, SOQL queries) |
| 2026-02-20 | Auth: JWT (python-jose) + passlib[bcrypt] + Redis refresh tokens | Stateless API auth for React SPA. bcrypt hashing (Sec 11.3). Short-lived access tokens (15 min) + Redis-stored refresh tokens with configurable timeout (Sec 8.2). Two roles as JWT claims: Admin, Reviewer. Redis already in stack. | FastAPI-Users (opinionated for 2-role system), session-based cookies (less suited for SPA) |
| 2026-02-20 | Containers: Docker Compose | Single command start (Sec 12.5). 5 services: api (FastAPI), worker (Celery), scheduler (APScheduler), db (PostgreSQL), redis, frontend (Vite dev / Nginx prod). Health checks in compose for all services. Dev and prod profiles. | Podman (smaller ecosystem), bare metal (not cloud-ready) |
| 2026-02-20 | Testing: pytest + pytest-asyncio + httpx + pytest-cov + factory-boy + Playwright | Unit/integration/E2E per Sec 12.6. >70% coverage target. httpx AsyncClient for FastAPI testing. factory-boy for realistic test data. Playwright for dashboard E2E. pytest already in CI (quality.yml). | unittest (verbose), Playwright deferred to Phase Final if time-constrained |
| 2026-02-20 | Code quality: ruff (lint+format) + mypy (types) | ruff replaces flake8+isort+black in one tool (Rust, fast). mypy enforces type hints (CLAUDE.md style). Both integrate into code-quality-gate.py hook. | flake8+black+isort (4 tools vs 1), pyright (less mainstream in CI) |
| 2026-02-20 | Project structure: src layout + pyproject.toml | Modern Python packaging standard. src/ layout prevents accidental imports. pyproject.toml consolidates all tool config. adapters/ directory maps to FOUNDATION.md Sec 9 (4 adapter families). | flat layout (import confusion), setup.py (deprecated) |
| 2026-02-20 | mcp-scan APPROVED (with conditions) | Cerbero evaluation: SUSPICIOUS rating → REQUIRES HUMAN REVIEW → User APPROVED. Conditions: --opt-out mandatory (anonymous UUID still sent but no tool descriptions), scan-only (no proxy/intercept mode), monitor Snyk ownership transition. Installed via uvx (isolated execution). | Cisco MCP Scanner (offline but heavier), MCPGuard (no CLI), Proximity (NOVA rules, complementary) |
| 2026-02-20 | claude-code-security-review APPROVED (with conditions) | Anthropic publisher (trusted). GitHub Action for PR security review via Claude API. ~3K stars, MIT. Anthropic warns: not hardened against prompt injection. Checkmarx demonstrated 3 bypass techniques. Conditions: trusted PRs only, never sole gate, pin commit SHA, API key as secret. | Manual code review only, SonarQube (heavier, not AI-native) |
| 2026-02-20 | PostgreSQL MCP REJECTED | Confirmed SQL injection (Datadog Security Labs): query stacking bypasses read-only transaction (`COMMIT; DROP SCHEMA`). Server archived May 2025, npm v0.6.2 unpatched (21K weekly downloads). | crystaldba/postgres-mcp (safe alt), antonorlov/mcp-postgres-server (prepared statements), AWS Labs Aurora MCP |
| 2026-02-20 | SAST MCP REJECTED | Untrusted publisher (Sengtocxoen, 5 stars). Executes 23+ tools via shell incl. offensive: SQLMap, Nmap, Nikto. Unauthenticated Flask HTTP server. Path traversal risk. | Run Bandit/Semgrep directly in CI, claude-code-security-review for PR review |
| 2026-02-20 | HubSpot MCP DEFERRED | First-party HubSpot (trusted publisher, not in trusted-publishers.txt). Beta v0.4.0, closed-source (no public repo), stale release (~8mo). Node.js dep in Python stack. hubspot-api-client SDK covers all Sec 6.2 ops natively. Re-evaluate at GA/v1.0+. | hubspot-api-client SDK (already selected, Python-native, open-source, mature) |
| 2026-02-20 | Slack MCP SKIP | Archived May 2025. slack-sdk already in stack with AsyncWebClient + Block Kit + rate limiting. Marginal benefit. Official Slack MCP at docs.slack.dev exists but requires published app. | Direct SDK usage (already decided) |
| 2026-02-20 | Python code quality skill SKIP | 85% overlap with CLAUDE.md. Command reference sheet for ruff/mypy — commands already configured in quality-gate.json and CLAUDE.md. | Existing CLAUDE.md + quality-gate.json |
| 2026-02-20 | Honnibal Python skills APPROVED (selective install) | 7 analytical methodology skills by spaCy creator. Only 15% overlap. MIT, markdown-only (.md.txt), no executable code. Install priority: tighten-types + try-except (HIGH), contract-docstrings + pre-mortem (MEDIUM). Defer: hypothesis-tests, mutation-testing (Phase Final). | No equivalent — unique analytical methodologies |

---

## Candidate Ecosystem Catalog

> Populated during Phase 1.4 (Ecosystem Scan). Evaluated in Phase 4 (Tooling & Security).

| Name | Source | Tier | Target | Impact | Risk | Status |
|------|--------|------|--------|--------|------|--------|
| HubSpot Official MCP | [developers.hubspot.com/mcp](https://developers.hubspot.com/mcp) | 1 | Core (CRM block) | HIGH — Official MCP could replace/simplify CRM adapter development for Block 14. OAuth 2.1 (remote, read-only) + Private App Token (local, read+write). Public beta since May 2025. | Medium (beta v0.4.0, closed-source, Node.js dep, stale release ~8mo) | **DEFERRED** — hubspot-api-client SDK (already selected) covers all Sec 6.2 ops, is Python-native, mature, open-source. Re-evaluate at GA. |
| PostgreSQL MCP | [modelcontextprotocol/servers-archived](https://github.com/modelcontextprotocol/servers-archived/tree/HEAD/src/postgres) | 1 | Core (dev tooling) | MEDIUM — Claude Code manages DB schema directly. Useful during Blocks 0-1 for model iteration. | **CRITICAL** (confirmed SQL injection CVE, archived, unpatched on npm) | **REJECTED** — SQL injection bypasses read-only. Consider crystaldba/postgres-mcp as alternative. |
| SAST MCP Server | [Sengtocxoen/sast-mcp](https://github.com/Sengtocxoen/sast-mcp) | 2 | Sentinel | MEDIUM — 23+ SAST tools (Bandit, Semgrep, TruffleHog + offensive: SQLMap, Nmap, Nikto). | **CRITICAL** (shell exec, untrusted publisher, 5 stars, offensive tools bundled) | **REJECTED** — Untrusted publisher, arbitrary shell execution, offensive tooling exceeds SAST scope. |
| claude-code-security-review | [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) | 1 | Core (CI) | MEDIUM — Official Anthropic GitHub Action for PR security review. ~3K stars. MIT. Sends diffs to Claude API. | Medium (prompt injection not hardened per Anthropic; Checkmarx demonstrated bypasses) | **APPROVED** (conditions: trusted PRs only, never sole gate, pin commit SHA, store API key as secret) |
| mcp-scan | [invariantlabs-ai/mcp-scan](https://github.com/invariantlabs-ai/mcp-scan) | 1 | Core (security) | HIGH — Scans MCPs for prompt injection, tool poisoning, rug pulls. Required before any MCP install. Apache-2.0, 1.5k stars. | Low (scan-only, opt-out telemetry) | **APPROVED** (conditions: --opt-out mandatory, scan-only usage, no proxy mode) |
| Slack MCP | [modelcontextprotocol/servers-archived](https://github.com/modelcontextprotocol/servers-archived/tree/HEAD/src/slack) | 2 | Inquisidor | LOW — Dev-time testing of Slack integration. Marginal over direct SDK usage. | Low (archived, unmaintained) | **SKIP** — Archived May 2025, slack-sdk already in stack, marginal benefit. Official Slack MCP (docs.slack.dev) exists but requires published Slack app. |
| Python code quality skill | [laurigates/dotfiles](https://claude-plugins.dev/skills/@laurigates/dotfiles/python-code-quality) | 2 | Core (dev) | LOW — ruff + mypy command reference. 85% overlap with CLAUDE.md. | Low (markdown only) | **SKIP** — Redundant with existing CLAUDE.md configuration. Just a command cheat sheet. |
| spaCy creator Python skills | [honnibal/claude-skills](https://github.com/honnibal/claude-skills) | 2 | Core (dev) | MEDIUM — 7 analytical skills (tighten-types, try-except, pre-mortem, contract-docstrings, hypothesis-tests, mutation-testing, stub-package). Only 15% overlap with CLAUDE.md. | Low (markdown only, MIT, no executable code) | **APPROVED** (install selectively: tighten-types + try-except HIGH priority, contract-docstrings + pre-mortem MEDIUM) |

---

## Strategic Assessment

> Completed during Phase 3 (Strategic Review). Each Phase 1 decision evaluated against Phase 2 tooling results through 7 analytical dimensions: Stack Fit (tighten-types), Agent Composition (Cerbero), Skill Coverage (contract-docstrings), MCP Opportunities (Cerbero), Validation Strategy (try-except + pre-mortem), Security Posture (OWASP + pre-mortem), Architecture Implications (pre-mortem 10 categories).

### Confirmations

**API & Data Layer**
- **FastAPI** — Pydantic v2 validates Appendix B contracts at API boundary with zero `Any` leakage. DI maps 1:1 to adapter registration (Sec 9.6). OpenAPI auto-gen enables frontend type codegen. *(tighten-types: boundary precision confirmed)*
- **PostgreSQL** — JSONB stores LLM raw output and routing payloads without schema migration. pg_trgm covers <5s search. PostgreSQL MCP rejection has no impact — Alembic migrations sufficient. *(Cerbero: MCP rejection validated)*
- **SQLAlchemy 2.0 async + Alembic** — `Mapped[]` type annotations propagate through mypy. asyncpg driver typed. Dual session factories (async for FastAPI, sync for Celery) well-documented pattern. *(tighten-types: type propagation confirmed)*

**Pipeline & Workers**
- **Celery + Redis** — Task chaining maps to state machine (Sec 3.4). Redis triples as: classification cache (Sec 10.6), refresh token store (Sec 8.2), Celery broker. *(try-except: each task boundary is external-state transition requiring structured exception handling)*
- **APScheduler (dedicated container)** — Prevents duplicate polls by design (Sec 3.2). *(pre-mortem Cat 8: 5-min interval is load-bearing default — specs must document explicitly)*
- **LiteLLM** — Unified `completion()` avoids dual-SDK maintenance. Config-level model switch addresses lesson 14.3.2. *(tighten-types: `ModelResponse` wraps dynamic data — see Adjustments)*

**Integrations**
- **google-api-python-client** — Predecessor validated OAuth refresh flow. Minimum scopes proven. *(contract-docstrings: Sec 9.2 interface well-defined)*
- **slack-sdk** — AsyncWebClient + Block Kit covers Sec 5.4 payload formatting. Slack MCP skip validates SDK-direct approach. *(Cerbero: MCP skip confirmed)*
- **hubspot-api-client** — HubSpot MCP deferral validates SDK-native path. Free tier enables portfolio demo. *(Cerbero: MCP deferral confirmed — see Adjustments)*
- **JWT + passlib + Redis** — Stateless SPA auth. Redis already in stack. *(pre-mortem Cat 8: 15-min TTL, bcrypt rounds, CORS origins are load-bearing defaults)*

**Frontend & Tooling**
- **React + Vite + TypeScript** — OpenAPI-to-TypeScript codegen enforces Appendix B contracts end-to-end. *(tighten-types: type generation eliminates manual duplication)*
- **Docker Compose** — 6 services (api, worker, scheduler, db, redis, frontend). Health checks per service. *(corrected: 6 not 5)*
- **pytest stack** — pytest-asyncio for async tests, httpx AsyncClient for API integration, factory-boy for contract-compliant test data. *(try-except: mock external adapters, never mock DB in integration tests)*
- **ruff + mypy** — Integrated into code-quality-gate.py hook. Skills supplement static analysis with methodology-driven review. *(tighten-types + try-except: additive layer)*
- **src layout + pyproject.toml** — `src/adapters/{email,channel,crm,llm}/` maps directly to Sec 9. *(confirmed)*
- **mcp-scan** — Installed, operational with `--opt-out`. Gate for any future MCP additions. *(Cerbero: operational)*

### Adjustments

| Decision | Adjustment | Phase 4 Impact |
|----------|-----------|----------------|
| claude-code-security-review | Add as CI validation layer when repo has PRs. Pin commit SHA, trusted PRs only, never sole gate. | CI/CD block spec references this as additive layer, not blocking gate. |
| PostgreSQL MCP REJECTED | No DB MCP shortcut. Schema work via Alembic + standard SQL. | Model/migration block specs include Alembic workflow, no MCP assumption. |
| HubSpot MCP DEFERRED | Full CRM adapter via hubspot-api-client SDK. No MCP simplification. | CRM block spec budgets full adapter (6 methods per Sec 9.4). |
| LiteLLM `ModelResponse` typing | `ModelResponse` wraps dynamic provider JSON. Services must not depend on it directly. | LLM adapter spec defines typed `ClassificationResult` and `DraftText` at boundary. tighten-types applies at review. |
| Celery task return types | `AsyncResult.get()` returns `Any`. Task chains lose type info across boundaries. | Pipeline specs define typed result dataclasses per task. Chain via Redis/DB, not Celery result backend. |
| Docker Compose service count | 6 services, not 5 (frontend was undercounted in Phase 1). | Compose spec reflects 6 services: api, worker, scheduler, db, redis, frontend. |
| Newly discovered skills | `alignment-chart` and `concept-analysis` (honnibal repo) not evaluated in Phase 2. | Phase 5: Cerbero evaluates both before install decision. |

### Agent Composition

**Confirmed: Lorekeeper + Inquisidor + Sentinel (3 generalist agents) + backend-worker + frontend-worker (2 specialist workers).**

| Agent | Assigned Skills | Application |
|-------|----------------|-------------|
| Lorekeeper | compound engineering (native) | CLAUDE.md, SCRATCHPAD, docs, graduation protocol |
| Inquisidor | tighten-types, try-except | Type precision at adapter boundaries, exception strategy per pipeline stage |
| Sentinel | Cerbero, contract-docstrings, pre-mortem | Security evaluation, adapter contract definitions, fragility analysis |
| backend-worker | consults Inquisidor/Sentinel | API, services, adapters, models, migrations |
| frontend-worker | consults Inquisidor for types | Dashboard SPA, OpenAPI type codegen |

Newly discovered skills: `alignment-chart` → Inquisidor (test categorization), `concept-analysis` → Lorekeeper (domain glossary). Three agents remain sufficient — no specialist addition needed.

### Architecture Directives for Phase 4

> Phase 4 block specs MUST enforce these directives, organized by skill methodology source.

**tighten-types directives:**
1. Every adapter interface method: fully typed signatures — no `dict[str, Any]` at boundaries. Pydantic models or dataclasses for all Appendix B contracts.
2. LLM adapter returns typed `ClassificationResult` and `DraftText`, not raw `ModelResponse`. Extraction and validation inside adapter.
3. Celery task results: typed dataclasses stored in DB/Redis, not passed through Celery result backend.
4. Frontend: auto-generated TypeScript types from OpenAPI spec. Manual type duplication prohibited.

**contract-docstrings directives:**
5. Each adapter spec (email, channel, CRM, LLM) documents: input invariants, return guarantees, errors raised, external state errors, silenced errors — per Sec 9.2-9.5.
6. Pipeline state transitions (FETCHED→SANITIZED→CLASSIFIED→ROUTED→...) document preconditions and postconditions per state.

**try-except directives:**
7. External-state operations (Gmail, Slack, HubSpot, LiteLLM, Redis, PostgreSQL): structured try/except with specific exception types. Never bare `except Exception` (except top-level Celery task handlers).
8. Local computation (classification parsing, routing rule eval, draft assembly): conditionals, not try/except. Parse failures are validation errors.
9. Each pipeline stage defines: max attempts, backoff strategy, fallback behavior, failure state (per Sec 3.4).

**pre-mortem directives:**
10. Cat 1 (implicit ordering): state machine transitions enforced via DB enum column, not convention. No state skipping.
11. Cat 3 (stringly-typed): routing conditions and classification categories as DB-backed enums with FK validation. Not free-form strings.
12. Cat 4 (unstated preconditions): LLM output shape assumptions documented. Validation layer between raw LLM response and typed result with fallback path.
13. Cat 6 (non-atomic): each pipeline stage commits independently. Partial failure at stage N does not roll back N-1. Failed stages logged with specific error state.
14. Cat 8 (load-bearing defaults): configurable via env/config, not hardcoded — LLM temperature (0.1/0.7), polling interval (5min), retry max, backoff base, batch size (50), JWT TTL (15min), bcrypt rounds (12), body truncation (4000 chars), snippet length (200 chars).
15. Cat 10 (version-coupled): pin all SDK versions in pyproject.toml. Document known-compatible versions per adapter spec.

**Security directives (Cerbero + OWASP):**
16. Prompt injection defense: 4-layer architecture (Sec 11.2) — classification block spec allocates explicit implementation per layer.
17. PII never in logs (Sec 11.4). Structured logging references emails by ID only.
18. Single-tenant: runtime monitoring deferred. CORS, rate limiting, input validation sufficient for Phase N.

---

## Architecture Pivot Summary

> Completed during Phase 5.4 (Architecture Reconciliation), if applicable.

### Deltas
<!-- Differences between Phase 3 blueprint and actual Phase 4 tooling -->

### Spec Adjustments
<!-- Changes applied to specs post-reconciliation -->

### Optimizations
<!-- Architectural simplifications enabled by installed tools -->
