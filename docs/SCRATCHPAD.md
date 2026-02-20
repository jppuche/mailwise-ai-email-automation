# Learning Scratchpad — mailwise

Granular log of errors, corrections, and preferences. Updated each session.
Compound learning: each session reads this file before working.

## Rules

- Limit: 150 lines. If exceeded, prune old consolidated entries.
- Graduation: pattern repeats 3+ times or is critical → move to CLAUDE.md "Learned Patterns"
- When graduating, remove original entries from scratchpad
- All agents write with [agent-name] tag, Lorekeeper organizes and prunes

<!-- Session format: ## YYYY-MM-DD -- [description] / ### Mistakes made / ### User corrections / ### What worked well / ### What did NOT work / ### Preferences discovered -->

---

## 2026-02-19 -- Initial setup

### What worked well

- Project structure generated correctly

---

## 2026-02-20 -- Phase 1: Technical Landscape [Lorekeeper]

### What worked well

- FOUNDATION.md as single source of truth made tech decisions traceable
- Preproyecto reference files provided validated patterns: 2-layer classification, sanitization pipeline
- Plan critique cycle caught 8 edge cases early

### Preferences discovered

- [user] Dual objective: portfolio + consultant showcase (code as template + methodology as process)
- [user] Phase 5 before Phase 4: agents inform spec writing
- [user] Prefers infrastructure (Celery+Redis) for professional appearance
- [user] All 20 specs upfront: spec set is a consultant deliverable

---

## 2026-02-20 -- Phase 2: Tooling & Security [Lorekeeper]

### What worked well

- Parallel agent deployment (4 agents) completed 7 evaluations in ~5 min vs ~20 min sequential
- Cerbero structured templates produce high-quality evaluation reports from agents
- Multi-source research (repo + README + blog + independent audits) catches issues single-source misses

### What did NOT work

- `gh` CLI not installed on this machine — agents fell back to WebFetch/WebSearch successfully

### Security discoveries

- [security] Full evaluation details in DECISIONS.md Candidate Ecosystem Catalog
- [security] Only 8.5% of MCP servers use OAuth; 53% rely on static tokens (Astrix research)
- [quality] honnibal/claude-skills: .md.txt extension prevents hidden HTML comment injection — good practice

### Patterns graduated to CLAUDE.md

- MCP servers: check servers-archived first
- Cerbero: structured report templates
- Verify hashes when downloading
- Skills/MCPs as active analytical lenses (Phase 3 user correction)

---

## 2026-02-20 -- Phase 3: Strategic Review [Lorekeeper]

### What worked well

- Skill methodologies as analytical lenses produced concrete architecture directives, not just "confirmed" stamps
- pre-mortem 10 categories mapped directly to pipeline architecture — identified 6 fragility points (ordering, stringly-typed, unstated preconditions, non-atomic, load-bearing defaults, version coupling)
- Parallel agent deployment for research + analysis maintained speed

### Discoveries

- [architecture] LiteLLM `ModelResponse` wraps dynamic provider JSON — must define typed extraction layer at adapter boundary, not pass `ModelResponse` to services
- [architecture] Celery `AsyncResult.get()` returns `Any` — task chain results lose type info, need typed dataclasses via Redis/DB instead of result backend
- [architecture] Docker Compose has 6 services (not 5 as stated in Phase 1) — frontend was undercounted
- [tooling] 2 new honnibal skills discovered: `alignment-chart` (function categorization) and `concept-analysis` (naming consistency) — not in Phase 2 evaluation, flagged for Phase 5 Cerbero review
- [methodology] 18 architecture directives organized by skill source provide actionable spec requirements, not generic guidelines

### Preferences discovered

- [user] Use skill/MCP knowledge actively — graduated to CLAUDE.md Learned Patterns

---

## 2026-02-20 -- Phase 5: Team Assembly [Lorekeeper]

### What worked well

- Parallel skill download + Cerbero eval maintained speed
- Hex dump forensic analysis (xxd + grep) definitively resolved false positive in seconds
- Agent templates with embedded architecture directives create self-contained workers

### Security discoveries

- [security] Agent context boundary confusion: system-reminder tags injected into agent context can be confused with file content. Agent ad230da reported prompt injection in concept-analysis.md.txt that did not exist. Forensic (xxd hex dump, grep, byte-level inspection) confirmed 658-byte file is 100% clean. Root cause: system injects `<system-reminder>` between agent processing steps, agent naively reported it as file content.
- [security] Mitigation: ALWAYS verify agent security findings with forensic tools (hex dump, grep) before taking action. Never trust agent-reported injection findings without byte-level confirmation.
- [security] SHA-256 hashes recorded for all 6 honnibal skills for future integrity verification

### Discoveries

- [tooling] concept-analysis.md.txt frontmatter name is "conceptual-analysis" (not "concept-analysis") — minor naming inconsistency in honnibal repo
- [architecture] Sentinel on opus (security depth), all others on sonnet (cost/speed) — matches Preproyecto precedent
