<!-- Editing guide: @_workflow/guides/Referencia-edicion-CLAUDE.md -->

# mailwise

Intelligent Email Classification and Routing System

## Stack

- **Backend:** Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Alembic / Celery + Redis
- **Frontend:** React + Vite + TypeScript
- **Database:** PostgreSQL (JSONB + pg_trgm)
- **LLM:** LiteLLM (OpenAI / Anthropic / Ollama)
- **Integrations:** Gmail API, Slack SDK, HubSpot API
- **Auth:** JWT (python-jose) + passlib[bcrypt] + Redis refresh tokens
- **Infra:** Docker Compose (api + worker + scheduler + db + redis + frontend)

## Project state

@docs/STATUS.md

## Style

- snake_case for files, variables, and functions
- PascalCase for classes
- Type hints on public functions

## Commands

- Test: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`
- Typecheck: `mypy src/`
- Docs check: `bash scripts/validate-docs.sh`
- Build: `docker compose build`

## Skills (CHECK BEFORE each task)

- `cerbero` -- Security evaluation of MCPs/Skills before installation

## Rules

- **BEFORE each task: check which skills apply** (see Skills above)
- Use skills as specialized knowledge -- consult when trigger matches
- **ALWAYS search codebase before creating something new**
- Individual tests, not full suite (except block validation)
- Scratchpad: read docs/SCRATCHPAD.md at start, append with [agent] tag at close
- **Persist discoveries to SCRATCHPAD.md immediately** -- don't wait for session close
- Post-mortems go to docs/LESSONS-LEARNED.md (append-only)
- Docs check: `bash scripts/validate-docs.sh` at session/block close

### Lorekeeper Protocol (MANDATORY)

**Session start:**
1. Read and ACT on SessionStart hook items (REQUIRED ACTIONS)
2. If SCRATCHPAD > 100 lines: graduate repeated patterns to Learned Patterns
3. If no today entry in SCRATCHPAD: create section

**During session:**
4. Update SCRATCHPAD with errors/corrections/discoveries on the spot
5. Run `bash scripts/validate-docs.sh` before each commit

**Session close:**
6. Verify SCRATCHPAD entry with [agent] tag
7. Update CHANGELOG-DEV.md if significant changes
8. Run `bash scripts/validate-docs.sh` -- 0 errors mandatory

## Architecture

- Adapter pattern for all external integrations (Sec 9): email/, channel/, crm/, llm/
- Services layer for business logic; API layer is thin (routers → services → adapters)
- Celery tasks for async pipeline: ingest → classify → route → CRM sync → draft
- Dedicated scheduler container (APScheduler) — never in API process
- Dual session factories: async (FastAPI) + sync (Celery tasks)
- Decisions: @docs/DECISIONS.md | Block specs: @docs/specs/

## Conventions

- Commits: type(scope): description (e.g., feat(auth): add login flow)
- Branches: feature/block-N-name
- Block specs in docs/specs/

## Hooks

Configured in .claude/settings.local.json (do not commit).

- `lorekeeper-session-gate.py` (SessionStart) — context + REQUIRED ACTIONS + version check
- `lorekeeper-commit-gate.py` (PreToolUse:Bash) — blocks commit if docs stale
- `lorekeeper-session-end.py` (SessionEnd) — checkpoint + graduation candidates
- `code-quality-gate.py` (PreToolUse:Bash) — quality checks (pytest)
- `validate-prompt.py` (UserPromptSubmit) — prompt injection defense
- `pre-tool-security.py` (PreToolUse:Bash) — blocks dangerous commands
- `mcp-audit.py` (PreToolUse:mcp) — audits MCP tool calls
- `cerbero-scanner.py` (PreToolUse) — security scanner

## Security

- Secrets ALWAYS as env vars -- real values in `.env` (gitignored). Never hardcoded
- Sensitive files in `secrets/` (gitignored)
- MCP tools: least privilege -- explicit deny in `permissions.deny`
- **ALWAYS verify hashes** when downloading packages, binaries, or dependencies
- mcp-scan: ALWAYS run with `--opt-out` flag (approved with conditions, see DECISIONS.md)

## Scratchpad

@docs/SCRATCHPAD.md -- read at start, append at close

## Learned Patterns (compound engineering -- update at block close)

- MCP servers from `modelcontextprotocol/servers`: always check `servers-archived` repo first — many are archived/unmaintained
- Cerbero agent evaluations: use structured report templates (SUMMARY, PUBLISHER, CAPABILITIES, RISK, VERDICT, CONDITIONS)
- Vendor MCP tools: check closed-source status, language stack compatibility, compare against vendor's own SDK before adopting
