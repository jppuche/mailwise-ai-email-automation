# Development Process & Engineering Practices

mailwise was built using a systematic, repeatable process designed to produce
production-quality software at each step. Every phase combines structured
planning, automated quality gates, disciplined debugging, and a living knowledge
base that grows incrementally across the full development lifecycle.

---

## Block-Based Development

The project is organized into 20 discrete blocks (B00 through B19, where B00
is the scaffolding foundation). Each block follows the same four-step cycle:

1. **Spec** — A written specification defines scope, interfaces, exit criteria,
   and test count target before any code is written.
2. **Implement** — Code is written to satisfy the spec. Adapters, services, and
   API layers are kept in separate concerns.
3. **Test** — Unit tests cover all business logic; integration tests cover all
   API endpoints; E2E tests cover critical user flows. External services are
   mocked at the boundary — the database is never mocked in integration tests.
4. **Review** — The block closes only when all quality gates pass and the commit
   is clean. A handoff document is written for the next block.

This cycle keeps scope bounded, progress measurable, and every commit
deployable.

---

## Quality Gates

Every commit must pass four automated checks before it is accepted:

| Check | Tool | Purpose |
|-------|------|---------|
| Lint | `ruff check .` | Enforce style rules and catch common errors |
| Format | `ruff format --check .` | Consistent code formatting across the codebase |
| Type check | `mypy src/` | Verify type annotations on all public functions |
| Test suite | `pytest` | Confirm no regressions; enforce coverage targets |

These checks run within a 120-second timeout via an automated pre-commit hook.
A failing commit is blocked at the gate — not reviewed, not merged. Quality
enforcement is structural, not aspirational.

---

## Debugging Protocol

When a bug is encountered, the team follows a mandatory five-step Prediction
Protocol. It prevents the most common form of wasted debugging time: changing
things without a hypothesis.

### The five steps

1. **Predict** — State a hypothesis before looking at any code. What is the
   current behavior? What should it be? Where is the likely origin?
2. **Observe** — Read the actual error message, stack trace, or log output.
   Reproduce the issue with minimal steps. Never skip this step.
3. **Compare** — Explicitly compare prediction to observation. Where did they
   diverge? What does the divergence reveal?
4. **Explain** — Form a root-cause explanation. Is this a symptom of something
   deeper? What is the minimal fix?
5. **Verify** — Confirm the fix addresses the root cause, not just the symptom.
   Run the relevant tests. Check for regressions.

### Anti-patterns (explicitly prohibited)

- **Shotgun debugging** — changing multiple things at once without a hypothesis
- **Unverified fixes** — assuming the fix worked without running tests
- **Dismissing failures** — labeling test failures as "flaky" without
  investigation
- **Skipping reproduction** — claiming "it works on my machine"
- **Ignoring history** — not checking `docs/LESSONS-LEARNED.md` for similar
  past incidents before diving in

---

## Compound Engineering

Knowledge from each block is systematically captured and made available to all
future blocks — an engineered feedback loop that makes every subsequent block
faster and more reliable.

### How it works

1. **Capture** — Discoveries, errors, and corrections are written immediately to
   `docs/SCRATCHPAD.md` with an agent tag. Nothing is deferred to session close.
2. **Graduate** — Any pattern appearing three or more times, or judged critical,
   is promoted to the permanent `Learned Patterns` section of `CLAUDE.md`. The
   scratchpad entries are removed. The pattern becomes institutional memory.
3. **Apply** — Every session begins by reading the scratchpad and learned
   patterns before writing any code. Graduated patterns are treated as
   invariants: they are applied, not rediscovered.

### Real examples from this project

**SQLAlchemy Enum values mapping** — Early in development it was discovered
that `sa.Enum(StrEnum)` stores the `.name` attribute (uppercase) rather than
the `.value` attribute (lowercase), causing mismatches with Alembic-created
PostgreSQL enum values. After this was hit once and documented, a
`values_callable=lambda e: [m.value for m in e]` fix was applied to all StrEnum
columns from that point forward. No subsequent block hit the same bug.

**Celery task retry testing** — Testing Celery's retry mechanism requires
`self.retry.side_effect = celery.exceptions.Retry()` so that the mock raises
the real exception class, matching production behavior. Once graduated, this
pattern was applied consistently across all retry-related tests in blocks B09
through B18.

**Frontend hook CWD issue** — Running `cd frontend && npm install` permanently
changes the shell working directory for subsequent hook scripts, causing path
resolution failures. The graduated pattern documents the fix (temporary
pass-through stub scripts in `frontend/.claude/hooks/`) and prevented the issue
from consuming time in blocks B16 and B17 after it was first encountered in B15.

---

## Documentation Governance

Documentation is a first-class engineering artifact. A dedicated Lorekeeper
role maintains five documents across the full project lifecycle.

### Documents and their contracts

| File | Type | Rule |
|------|------|------|
| `CLAUDE.md` | Living reference | Maximum 200 lines; every line must pass the relevance test |
| `docs/STATUS.md` | Current state | Rewritten at each block close; never exceeds 60 lines |
| `docs/DECISIONS.md` | Decision log | Append-only; one row per architectural decision; never deleted |
| `docs/CHANGELOG-DEV.md` | Change log | Append-only; significant changes recorded same day |
| `docs/SCRATCHPAD.md` | Session log | Maximum 150 lines; pruned as patterns graduate |

### Session protocol

- **Start** — Read the scratchpad for context. Act on any required items from
  the session-start hook before other work begins.
- **During** — Update the scratchpad on the spot when errors, corrections, or
  new patterns are found. Do not defer to session close.
- **Close** — Verify the scratchpad has a tagged entry for the session. Update
  the changelog if significant changes were made. Run
  `bash scripts/validate-docs.sh` and resolve all errors before committing.

### Docs validation

A validation script (`scripts/validate-docs.sh`) checks line-count limits,
required sections, and document freshness. It runs as a pre-commit gate: a
commit is blocked on any `[FAIL]`. Warnings surface as context but do not block.
Documentation drift is a build failure, not a review comment.
