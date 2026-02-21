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
- `tighten-types` -- Type precision at adapter boundaries, Pydantic models, no `Any` leakage
- `try-except` -- Exception handling audit: structured try/except for external ops, conditionals for local
- `contract-docstrings` -- Adapter boundary contracts: invariants, guarantees, errors, state transitions
- `pre-mortem` -- Fragility analysis: 10 categories (ordering, stringly-typed, preconditions, non-atomic, defaults, version-coupled)
- `alignment-chart` -- Function/test categorization by correctness and collaboration (D&D alignment model)
- `concept-analysis` -- Naming consistency, domain glossary, concept boundary clarity

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
- Skills/MCPs as analytical lenses: apply approved skill methodologies actively during planning, execution, and verification — not just as passive references
- Parallel agent deployment (3+ subagents) for independent tasks reduces elapsed time ~4x — use whenever tasks are independent
- Agent security findings require forensic verification (hex dump, grep) before action — context boundary confusion produces false positives
- pyproject.toml: build-backend is `setuptools.build_meta` (NOT `setuptools.backends._legacy`). For `from src.X` imports: `where = ["."]` + `include = ["src*"]`
- mypy type-ignore codes: structlog `get_logger()` returns `Any` — use `type: ignore[no-any-return]` not `[return-value]`
- Docker at block-00: worker/scheduler exit (no celery_app yet) — 4/6 services healthy is expected baseline
- Alembic enums: use `create_type=True` inline in `op.create_table`, NOT separate `.create()` calls — SQLAlchemy's `_on_table_create` ignores `create_type=False` from Alembic's DDL path
- Alembic env.py: sync driver (psycopg2), no Base import, `target_metadata=None` for hand-written migrations
- Test DB fixtures: NullPool mandatory, `migrated_db` upgrade-only (no teardown downgrade) — PostgreSQL blocks DDL while sessions hold connections
- passlib 1.7.4 unmaintained: incompatible with bcrypt>=4.2 on Python 3.14 (detect_wrap_bug failure). Use `bcrypt` directly for password hashing
- python-jose: `JWTClaimsError` NOT exported from top-level `jose` — always import `from jose.exceptions import JWTClaimsError`
- SQLAlchemy `sa.Enum(StrEnum)`: uses `.name` (UPPERCASE) not `.value` (lowercase) — add `values_callable=lambda e: [m.value for m in e]` on all StrEnum columns to match Alembic-created PostgreSQL enum values
- Redis async singleton in tests: function-scoped pytest-asyncio loops don't share singletons — reset `_redis_client = None` between test functions via autouse fixture
- litellm exceptions: use `import litellm.exceptions as litellm_exc` — `litellm.RateLimitError` direct access triggers mypy `attr-defined` even with `ignore_missing_imports = true`; exception is named `Timeout` (not `TimeoutError`)
