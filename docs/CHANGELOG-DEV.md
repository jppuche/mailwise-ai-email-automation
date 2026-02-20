# Development Changelog — mailwise

> Append-only. Format: ## YYYY-MM-DD -- Brief description.
> Record WHAT was done, not HOW. The "how" goes in CLAUDE.md Learned Patterns.

## 2026-02-19 -- Initial setup

- Project structure created (.claude/, docs/, scripts/)
- CLAUDE.md configured with required sections
- Agents and rules defined

## 2026-02-20 -- Phase 1: Technical Landscape

- 15 technology decisions recorded in DECISIONS.md (FastAPI, PostgreSQL, SQLAlchemy, React+Vite+TS, Celery+Redis, LiteLLM, Gmail API, Slack SDK, HubSpot, JWT, Docker Compose, pytest, ruff+mypy, src layout)
- Ecosystem scan: 8 MCP/skill candidates cataloged (HubSpot Official MCP highest impact)
- CLAUDE.md updated with full stack, commands, architecture notes
- quality-gate.json updated with ruff, mypy, pytest gates
- Dual objective documented: portfolio (AI Engineer) + consultant showcase (replicable template + methodology)
- Phase order adjusted: 2→3→5→4 (agents inform spec writing)
- 8 known gotchas documented with mitigations for specific blocks

## 2026-02-20 -- Phase 2: Tooling & Security

- 8 ecosystem candidates evaluated via Cerbero (4 agents in parallel)
- mcp-scan APPROVED and installed (--opt-out, scan-only, isolated via uvx)
- claude-code-security-review APPROVED (trusted PRs only, pin commit SHA, never sole gate)
- honnibal/claude-skills APPROVED selectively (4 of 7 skills: tighten-types, try-except, contract-docstrings, pre-mortem)
- PostgreSQL MCP REJECTED (SQL injection confirmed by Datadog Security Labs, archived, unpatched)
- SAST MCP REJECTED (untrusted publisher, offensive tools, unauthenticated server)
- HubSpot MCP DEFERRED (beta, closed-source, SDK already selected)
- Slack MCP + Python code quality skill SKIPPED (redundant with existing stack)
- Hash verification rule added to CLAUDE.md Security section

## 2026-02-20 -- Phase 3: Strategic Review

- 20 Phase 1 decisions re-evaluated against Phase 2 tooling results using 7 analytical dimensions
- Skill methodologies applied as analytical lenses: tighten-types, try-except, contract-docstrings, pre-mortem, Cerbero
- 15 decisions confirmed, 6 adjustments documented (LiteLLM typing, Celery return types, Docker service count, CI security layer, no DB MCP shortcut, full CRM adapter required)
- Agent composition confirmed: Lorekeeper + Inquisidor + Sentinel + backend-worker + frontend-worker
- Skill-to-agent mapping defined: tighten-types+try-except→Inquisidor, contract-docstrings+pre-mortem+Cerbero→Sentinel
- 18 architecture directives documented for Phase 4 block specs (4 tighten-types, 2 contract-docstrings, 3 try-except, 6 pre-mortem, 3 security)
- 2 newly discovered honnibal skills (alignment-chart, concept-analysis) flagged for Phase 5 Cerbero evaluation

## 2026-02-20 -- Phase 5: Team Assembly

- 4 agent templates created: Inquisidor (sonnet), Sentinel (opus), backend-worker (sonnet), frontend-worker (sonnet)
- 6 honnibal skills installed to .claude/skills/honnibal/ (tighten-types, try-except, contract-docstrings, pre-mortem, alignment-chart, concept-analysis)
- Cerbero evaluation of alignment-chart: APPROVED (clean, markdown-only, 1 false positive scanner hit)
- Cerbero evaluation of concept-analysis: APPROVED (clean, forensic analysis cleared false positive from agent context boundary confusion)
- AGENT-COORDINATION.md Section 5 updated with mailwise-specific file ownership paths
- AGENT-COORDINATION.md Section 13 populated with 7 skill triggers and 5 agent assignments
- CLAUDE.md Skills section updated with 7 installed skills (cerbero + 6 honnibal)
- 18 architecture directives embedded in agent prompts per skill methodology source
- Forensic discovery: agent context boundary confusion can produce false positives when system-reminder tags are confused with file content — always verify with hex dump

## 2026-02-20 -- Phase 4: Architecture Blueprint

- 20 block specs written to docs/specs/ (block-00 through block-19)
- Skills applied as analytical lenses in specs: pre-mortem (fragility), try-except (exception strategy), tighten-types (type decisions), contract-docstrings (adapter contracts), alignment-chart (test categorization), concept-analysis (naming consistency)
- Sentinel security review: 0 critical, 3 warnings, 5 suggestions (docs/reviews/phase-4-security-review.md)
- Architecture directives from Phase 3 embedded in all specs (D1-D18 coverage, D15 minimal)
- Tier 2 features explicitly assigned to blocks
- Dependency DAG verified acyclic
- D16 discrepancy found: specs implement 5-layer prompt injection defense (not 4 as in DECISIONS.md) — pending correction
