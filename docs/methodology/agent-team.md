# Multi-Agent Development Team

## Overview

mailwise was built using a structured multi-agent architecture where each agent owns a distinct technical domain and operates within strict file boundaries. This design enables parallel specialization — security review, test engineering, documentation, backend, and frontend progress independently without merge conflicts or context bleed. A compound learning system (Lorekeeper) accumulates discoveries across sessions, ensuring lessons from early blocks inform later ones automatically.

---

## Agent Roster

| Agent | Model | Role | Specialization | Key Deliverables |
|-------|-------|------|----------------|------------------|
| **Sentinel** | Claude Opus | Security & Architecture Auditor | MCP/Skill security evaluation, adapter contract definition, system fragility analysis | Security review reports, hook implementations, architecture directives for all 20 blocks |
| **Inquisidor** | Claude Sonnet | Testing & Quality Specialist | Unit, integration, and E2E test authoring; type precision at adapter boundaries; exception strategy per pipeline stage | 1,780+ tests across 21 blocks, pytest infrastructure, quality gates |
| **Lorekeeper** | Claude Sonnet | Documentation Governance | Compound engineering via CLAUDE.md, decision log, session scratchpad, pattern graduation | CLAUDE.md, DECISIONS.md, SCRATCHPAD.md, STATUS.md — maintained across all 21 blocks |
| **backend-worker** | Claude Sonnet | Backend Implementation | FastAPI routers, SQLAlchemy models, Celery tasks, service layer, all external adapter integrations | 4 adapter families (email, channel, CRM, LLM), 5-task pipeline, 26 analytics endpoints |
| **frontend-worker** | Claude Sonnet | Frontend Implementation | React + TypeScript SPA, OpenAPI-driven type codegen, dashboard components, dark mode theming | 11 pages, 17+ components, 15 hooks, 342 frontend tests |

---

## Analytical Skills

Seven specialized skills augment the agents' reasoning. Each is a methodology document (no executable code) consulted on demand rather than loaded at startup, preserving token economy.

| Skill | Assigned To | Purpose |
|-------|-------------|---------|
| **cerbero** | Sentinel | OWASP MCP Top 10 evaluation framework. Applied before every MCP or third-party skill installation. Produced structured SUMMARY / CAPABILITIES / RISK / VERDICT reports for 8 candidates; 3 rejected, 2 deferred, 3 approved with conditions. |
| **contract-docstrings** | Sentinel | Defines adapter interface contracts: input invariants, return guarantees, errors raised, silenced errors, and state transition pre/postconditions. Applied to all four adapter families and the 5-stage Celery pipeline. |
| **pre-mortem** | Sentinel | Fragility analysis across 10 failure categories (implicit ordering, stringly-typed data, unstated preconditions, non-atomic commits, load-bearing defaults, version coupling). Produced 6 architecture directives embedded in every block spec. |
| **tighten-types** | Inquisidor | Eliminates `Any` leakage at adapter boundaries. Enforces typed `ClassificationResult` / `DraftText` from the LLM adapter, typed Celery task results, and auto-generated TypeScript types from OpenAPI — no manual duplication. |
| **try-except** | Inquisidor | Distinguishes external-state operations (structured `try/except` with specific exception types) from local computation (conditionals, not exceptions). Each pipeline stage defines max attempts, backoff strategy, fallback behavior, and failure state. |
| **alignment-chart** | Inquisidor | Categorizes functions and tests by correctness risk and collaboration surface (inspired by D&D alignment axes). Used as an exit criterion for block validation to ensure test suite coverage aligns with implementation risk. |
| **concept-analysis** | Lorekeeper | Naming consistency and domain glossary enforcement. Ensures terms like `classification`, `routing`, `draft`, and `review` map to single, unambiguous concepts across backend models, API contracts, and frontend components. |

---

## Coordination Model

**Orchestrator delegation.** The lead (Claude Code) decomposes each block into parallel or sequenced sub-tasks and delegates to the appropriate specialist. Backend implementation, test authoring, and security review of the same block can run concurrently because file ownership is exclusive and non-overlapping.

**File ownership prevents conflicts.** Each agent has an explicit `exclusive` domain and a `prohibited` list:
- Sentinel: `.claude/hooks/`, `docs/reviews/` — read-only on all production code
- Inquisidor: `tests/`, `conftest.py` — reads `src/` and `frontend/src/` without modifying
- Lorekeeper: `CLAUDE.md`, `docs/*.md` — never touches `src/` or `frontend/`
- backend-worker: `src/` — never touches `frontend/` or `tests/`
- frontend-worker: `frontend/src/` — never touches `src/` or `tests/`

**Compound learning via Lorekeeper.** Every session close appends discoveries to `docs/SCRATCHPAD.md` with agent tags. Patterns that recur three or more times graduate to `CLAUDE.md` "Learned Patterns" and become permanent context for all subsequent sessions. This prevented 30+ classes of repeated errors across 21 blocks (e.g., SQLAlchemy enum `.value` vs `.name`, passlib/bcrypt incompatibility, structlog processor signatures).

**Parallel deployment for independent tasks.** When block sub-tasks are genuinely independent (e.g., writing adapter code and writing its tests), agents are deployed in parallel, reducing elapsed time approximately 4x compared to sequential execution.

**Automated quality gates.** Three Claude Code hooks enforce standards without human intervention:
- `lorekeeper-session-gate.py` (SessionStart) — injects required actions from prior session
- `lorekeeper-commit-gate.py` (PreToolUse:Bash) — blocks commits if documentation is stale or validation fails
- `code-quality-gate.py` (PreToolUse:Bash) — runs `pytest`, `ruff`, and `mypy` before every commit

---

## Results

| Metric | Value |
|--------|-------|
| Development blocks delivered | 21 (B00 – B19 + scaffolding) |
| Backend tests | 1,487 |
| Frontend tests | 342 |
| Total tests | 1,780+ |
| Test coverage | 93% |
| API endpoints | 48 (26 analytics/admin + 22 core) |
| Adapter families | 4 (email / channel / CRM / LLM) |
| Celery pipeline tasks | 5 (ingest → classify → route → CRM sync → draft) |
| Frontend pages | 11 |
| Architectural decisions logged | 25 (append-only, traceable) |
| Learned patterns graduated to CLAUDE.md | 30+ |
