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

## 2026-02-20 -- Phases 1-3 (consolidated)

### Key user preferences

- [user] Dual objective: portfolio + consultant showcase
- [user] Phase 5 before Phase 4: agents inform spec writing
- [user] All 20 specs upfront: spec set is a consultant deliverable
- [user] Prefers infrastructure (Celery+Redis) for professional appearance

### Active discoveries (not yet in code)

- [architecture] LiteLLM `ModelResponse` wraps dynamic JSON — typed extraction layer needed at adapter boundary
- [architecture] Celery `AsyncResult.get()` returns `Any` — use typed dataclasses via Redis/DB
- [tooling] `gh` CLI not installed on this machine — use WebFetch/WebSearch fallback

### Graduated to CLAUDE.md Learned Patterns

- Parallel agents, forensic verification, MCP servers-archived, Cerbero templates, hash verification, skills as lenses

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

---

## 2026-02-20 -- visual-explainer Cerbero eval + install [Lorekeeper]

### Security discoveries

- [security] nicobailon/visual-explainer: Cerbero eval APPROVED. 64 scanner findings across 12 files — ALL false positives (design instructions: "always use theme", "never use Inter"; HTML comments inside code blocks). Zero injection, zero encoding, zero zero-width chars.
- [security] Skill writes HTML to `~/.agent/diagrams/` and opens browser — expected behavior. Optional `surf-cli` dep NOT evaluated.
- [security] Scanner false-positive pattern: CSS/HTML skills trigger imperative word + html_comment checks heavily due to design instructions and code examples. Tier 3 semantic analysis essential for these skills.

### What worked well

- Parallel community intelligence (2 web searches) + skill content fetch completed eval context in one round
- Scanning all 12 referenced files (not just SKILL.md) caught the full attack surface
- visual-explainer reference templates absorbed before generating — output quality high

### User corrections

- [user] Font sizes too small in blueprint diagram — increased all sizes by 1-3px across the board
- [user] Section numbers colliding with left border — fixed with `border-left: none` on `.sec-head`

### Preferences discovered

- [user] Prefers larger, more readable text in visualizations over compact density
