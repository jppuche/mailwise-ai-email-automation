# Agent Coordination and Orchestration Architecture

> Operational guide for Agent Teams in mailwise.
> Sources: [Claude Code Agent Teams Docs](https://code.claude.com/docs/en/agent-teams),
> [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system),
> [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/)

---

## 1. Orchestration Model

**Pattern: Orchestrator-Worker (Lead + Teammates)**

```
User
  |
  v
Lead (Delegate Mode — does NOT implement, only coordinates)
  |
  +---> backend-worker   (logic, API, DB, shared types)
  +---> frontend-worker  (components, pages, styles, assets)
  +---> Inquisidor        (unit tests, integration, E2E)
  +---> Lorekeeper        (docs/, CLAUDE.md)
  +---> Sentinel          (read-only audit, security)
```

**Fundamental rule:** The Lead coordinates, does NOT implement. Activate Delegate Mode (Shift+Tab x4).

---

## 2. Execution Types

### Subagents (Task tool)
- Own context, result returns to caller
- For focused tasks where only the result matters
- Lower token cost
- **Use for:** research, searches, quick validations

### Agent Teams (TeamCreate)
- Independent teammates with inter-communication
- Shared task list with auto-coordination
- Higher token cost
- **Use for:** development blocks (frontend + backend + tests in parallel)

### When to use each

| Situation | Use |
|-----------|-----|
| Web research | Subagent or main thread |
| Codebase search | Explore subagent |
| Block planning | Plan subagent |
| Block implementation | Agent Team or sequential subagents (see note) |
| Security review | Sentinel subagent (security) |
| Skill/MCP evaluation | Sentinel subagent (sandboxed) |
| Simple single-file task | Inline (no agent) |

**Note:** For blocks with strong phase dependencies (schema → types → client → routes → frontend), sequential subagents are more efficient than Agent Teams (avoid idle time). Agent Teams are better when there's real parallelizable work (independent frontend + backend).

---

## 3. Coordination Rules

### 3.1 Foreground vs Background
- **Foreground** when waiting for result to continue
- **Background** ONLY when you have your own parallel work
- Background agents do NOT wake the lead on completion — user must write

### 3.2 Pre-flight Permissions
Before each block, run per agent:
1. List required permissions (WebSearch, Bash, Write, Edit, Read, Glob, Grep)
2. Innocuous test per tool (e.g., `echo "test"` for Bash)
3. If fails: request user approval

### 3.3 Verify Capabilities before Delegating
- Confirm the agent has the tools it needs
- If it needs WebSearch, do it on main thread (has access)
- Don't assume subagents have the same permissions as the lead

### 3.4 Don't Promise Impossible Notifications
- Don't say "I'll notify you when done" if you depend on the user writing
- Be transparent: "agents are working, ask me when you want status"

### 3.5 Agent Output is Ephemeral
- Read results immediately on completion
- If lost, use `resume` with the agentId to recover

---

## 4. Communication Protocol

### Lead → Teammates
| Event | Destination | Content |
|-------|-------------|---------|
| Types available | frontend-worker | "Types ready. You can consume." |
| Routing error | Responsible worker | "Error in your domain: [detail]" |
| Validation started | All | "Validation in progress. Don't edit files." |
| Validation passed | Lorekeeper | "Block passed. Update docs + CLAUDE.md." |
| Pre-shutdown | All | "Prepare shutdown. Commit + send patterns." |

### Teammates → Lead
| Event | When | Content |
|-------|------|---------|
| Task start | On begin | "Starting [task]. Files: [list]" |
| Types ready | backend creates/modifies types | "Types updated: [files]" |
| Milestone 50% | At midpoint | "50% complete. Gotchas: [if any]" |
| Task completed | On finish | "Completed [task]. Pattern: [if applicable]" |
| Blocker | Cannot advance | "Blocked on [problem]. Need [what]" |

### Teammates → Lorekeeper
| Event | Content |
|-------|---------|
| Pattern discovered | "Pattern: [description]. For CLAUDE.md" |
| Gotcha | "Gotcha: [description]. Avoid in future." |
| Technical decision | "Decision: [chosen] over [alternative]" |

---

## 5. Strict File Ownership

<!-- CUSTOMIZE: adapt to your project structure -->

| Worker | Exclusive | Forbidden | Reads without modifying |
|--------|-----------|-----------|------------------------|
| frontend-worker | components, pages, styles, assets | backend logic, API, DB, tests, docs | shared types |
| backend-worker | logic, API, DB, shared types | components, pages, styles, tests, docs | — |
| Inquisidor (tests) | tests, test config | production code, docs | all src/ |
| Lorekeeper (docs) | docs/, CLAUDE.md | all source code | — |
| Sentinel (security) | .claude/hooks/, .claude/security/ | everything except hooks and security | all |

**Golden rule:** Two workers NEVER edit the same file. Conflict = Lead reassigns.

---

## 6. Spawn Order (mandatory)

```
1. backend-worker FIRST — creates shared types and defines API contracts
2. Inquisidor (tests) IN PARALLEL with backend — writes tests from spec
3. When backend notifies "types ready" → spawn frontend-worker + Lorekeeper
```

### Type Freeze
- Backend finalizes shared types in first phase
- After that, types are READ-ONLY for the rest of the block
- If backend needs new types: new file, don't modify existing ones

---

## 7. Shutdown Sequence (mandatory)

```
1. Inquisidor (tests) confirms: typecheck + lint + test + build pass
2. Sentinel runs final security verification (secrets check, hook integrity)
3. Lead announces pre-shutdown to all
3.5. ALL workers append to SCRATCHPAD.md with [agent-name] tag (MANDATORY — SessionEnd hook checks this)
4. Workers send final patterns to Lorekeeper
5. Lorekeeper updates CLAUDE.md + STATUS.md + CHANGELOG-DEV.md
6. Lorekeeper confirms to Lead ← GATE (don't advance until here)
7. Lead merges to main + version tag
8. Lead shutdown in order: frontend → backend → Inquisidor → Sentinel → Lorekeeper (LAST)
9. Lead verifies: git log shows merge + correct tags
10. /clear — clean context for next block
```

---

## 8. OWASP MCP Top 10 Security

| OWASP Risk | Mitigation |
|------------|------------|
| Tool Poisoning | Only skills/MCPs from verified publishers |
| Supply Chain Attack | Verify npm/GitHub match, don't install from unknown publishers |
| Command Injection | Don't auto-approve tool calls, manual review |
| Context Over-Sharing | Don't share .env, minimum scope per agent |
| Token Mismanagement | Never hardcode secrets in .mcp.json, use ${VARIABLE} |
| Privilege Escalation | Minimum permissions per agent, strict file ownership |

---

## 9. Sandboxed Evaluation of Skills/MCPs

When evaluating a new skill or MCP:

**Isolated review protocol:**
1. Spawn `Sentinel` agent (read + Bash permissions only)
2. Agent downloads/accesses the skill/MCP source code
3. Searches for: `eval()`, `exec()`, `fetch` to external domains, filesystem access, prompt injection
4. Reports findings to lead WITHOUT including suspicious content
5. Lead does NOT read source code directly (prevents context contamination)
6. Only after agent approval proceed to install

**Approval criteria:**
- No executable code in prompt-only skills
- No undeclared filesystem/network access in MCPs
- No prompt injection attempts in text files
- Verified publisher (Layer 2)
- Clean dependencies (Layer 3)
- Acceptable risk matrix (Layer 4)

---

## 10. Anthropic Best Practices (8 principles)

1. **Think Like Your Agents** — Observe failure modes, develop mental model
2. **Teach Delegation** — Clear objectives, output formats, explicit limits
3. **Scale Effort** — Simple queries: 1 agent. Complex: multiple subagents
4. **Tool Design Matters** — Agent-tool interfaces are critical
5. **Agent Self-Improvement** — Models can diagnose failures and suggest improvements
6. **Search Strategy** — Broad queries first, then progressive focus
7. **Guide Thinking** — Extended thinking improves reasoning
8. **Parallelize** — 3-5 subagents in parallel reduces time

---

## 11. Known Limitations

- No session resumption with in-process teammates
- Only one team per session
- No nested teams (teammates can't create sub-teams)
- Lead is fixed (leadership can't be transferred)
- Permissions are set at spawn, can't be changed after
- Task status may lag — verify manually if it seems stuck

---

## 12. Pre-Block Checklist

```
[ ] Block spec exists in docs/specs/
[ ] Branch created: feature/block-N-name
[ ] Pre-flight permissions executed (Section 3.2)
[ ] File ownership assigned (Section 5)
[ ] Spawn order planned (Section 6)
[ ] Skills reviewed per agent (Section 13)
[ ] Delegate Mode activated (Shift+Tab x4)
[ ] SCRATCHPAD.md read for prior context
```

---

## 13. Skills-to-Agent Block Mapping

### CROSS-CUTTING RULE: Before starting any task, review which skills apply.

Installed skills are specialized knowledge. Use in planning, implementation AND review.

### Installed Skills

<!-- These tables are filled in Phase 4-5 of the workflow when skills are installed and assigned to agents.
     During setup (Phase 0) they remain empty. -->

| Skill | Trigger (when to use) | Publisher |
|-------|----------------------|-----------|
| <!-- skill-name --> | <!-- when to use --> | <!-- publisher --> |

### Assignment per Agent

<!-- CUSTOMIZE: assign skills to agents -->

| Agent | Skills to CONSULT |
|-------|-------------------|
| **frontend-worker** | <!-- frontend skills --> |
| **backend-worker** | <!-- backend skills --> |
| **Inquisidor** (tests) | <!-- testing skills --> |
| **Sentinel** (security) | <!-- security skills --> |
| **Lorekeeper** | (no specific skills) |

### Pre-Task Protocol

```
BEFORE implementing any task:
1. Identify skills relevant to the specific task
2. Consult skill DURING planning, implementation, and review
3. If no skill was used, document why it doesn't apply
4. Don't use skills "just in case" — only when the trigger matches
```
