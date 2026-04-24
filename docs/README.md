# About This Documentation

This directory captures the documentation artifacts from the mailwise development process.

## Contents

- **methodology/** — Engineering practices, agent team composition, and security framework
- **specs/** — Block-by-block technical specifications (B00 through B19)
- **handoffs/** — Context documents passed between agent work sessions
- **reviews/** — Domain-expert audits (AI/ML, architecture, auth-security, infra-devops, phase-4 security) plus MCP/skill evaluations via the Cerbero framework
- **DECISIONS.md** — Architectural decisions log with alternatives considered
- **FOUNDATION.md** — Product requirements document (PRD)
- **adapter-guide.md** — Adapter pattern usage guide for extending integrations
- **deployment.md** — Deployment guide

## A note on internal references

Some documents here reference files such as `SCRATCHPAD.md`, `CLAUDE.md`, `STATUS.md`, `CHANGELOG-DEV.md`, and `LESSONS-LEARNED.md`. These are internal session logs and living reference documents maintained during development — meta-project artifacts that record compound-engineering patterns and session-by-session discoveries. They are kept locally by design and are not included in this repository. References and line-numbered citations to these files throughout methodology, handoffs, and reviews are trace information from the development process, not pointers the reader needs to resolve.

## A note on numbers

Per-block handoffs and domain reviews contain test counts, coverage percentages, and other metrics valid at their publication date. The project is a living codebase: the test suite grew from ~1,600 passing tests at block B18 completion to the current total of 2,100+ (1,856 backend + 342 frontend) after the cleanup and polish phases. When numbers in older docs appear to conflict with current figures, the difference is timeline, not inconsistency.

## A note on the review coverage

Per-block reviews under `reviews/` were applied selectively to blocks that introduced novel risk surfaces: B01 (data models and persistence), B02 (authentication and authorization), B04 (LLM adapter and prompt injection defense). Other blocks relied on the cross-cutting Phase-4 security review, the domain-wide architecture and AI/ML reviews, and the Inquisidor test-gate discipline. The twelve review documents together form the multi-layered audit, not twelve per-block audits.

What is published here is the substantive documentation of how mailwise was built: the methodology, the specifications, the cross-block handoffs, and the expert reviews that validated the architecture.
