# Cerbero Step 1: Source Code Review -- mcp-scan (snyk-agent-scan)

**Reviewer:** Sentinel
**Date:** 2026-03-02
**Package:** mcp-scan v0.4.2 (PyPI) / snyk-agent-scan v0.4.3 (GitHub)
**Repository:** https://github.com/invariantlabs-ai/mcp-scan
**Transport:** stdio (local CLI tool, not a server)
**Installation method:** `uvx mcp-scan@latest`
**Prior approval status:** APPROVED with conditions (DECISIONS.md, 2026-02-20)

---

## 1. Package Identity and Provenance

| Field | Value |
|-------|-------|
| PyPI name | `mcp-scan` |
| PyPI version | 0.4.2 (2026-02-18) |
| GitHub name | `snyk-agent-scan` (renamed in v0.4.3) |
| GitHub version | 0.4.3 |
| Publisher | invariantlabs (PyPI) / Invariant Labs AG, Zurich, Switzerland |
| Current owner | **Snyk** (acquired Invariant Labs, June 2025) |
| License | Apache-2.0 |
| Stars | ~1,700 |
| Last commit | 2026-02-18 |
| Language | Python 90.2% |
| Python requirement | >=3.10 |
| Build system | hatchling |
| Entry point | `snyk-agent-scan` -> `agent_scan.run:run` |
| Total releases | 60+ (since April 2025) |
| Yanked releases | 2 (v0.2.0 and v0.2.0.1, marked "broken") |

### CRITICAL FINDING: Package Name Divergence

| Severity | CRITICAL |
|----------|----------|

The PyPI package `mcp-scan` (v0.4.2) and the GitHub repository (v0.4.3, renamed to `snyk-agent-scan`) are **diverging**. The changelog entry for v0.4.3 states: "Rename to agent-scan." The `pyproject.toml` on `main` branch now declares `name: snyk-agent-scan` with console script `snyk-agent-scan`, not `mcp-scan`.

**Impact for mailwise:** We install via `uvx mcp-scan@latest` which pulls v0.4.2 from PyPI. This version still works but is the **last version published under the old name**. Future updates will be published as `snyk-agent-scan`. The installation command will need to change to `uvx snyk-agent-scan@latest` to receive future security patches.

**Action required:** Monitor PyPI for deprecation notice on `mcp-scan`. Plan migration to `snyk-agent-scan` when the old name is formally deprecated.

---

## 2. Ownership Transition Assessment

| Severity | WARNING |
|----------|---------|

Snyk acquired Invariant Labs in June 2025. This is a **material ownership change** since our original approval in February 2026 (the acquisition had already occurred but the rename had not).

**Positive signals:**
- Snyk is a well-known, established security company (not an unknown acquirer)
- The tool's core mission (MCP security scanning) aligns with Snyk's product portfolio
- Active development continues post-acquisition (commits through Feb 2026)
- Security policy now points to Snyk's formal vulnerability disclosure process (docs.snyk.io)

**Risk signals:**
- Default analysis endpoint changed from `https://mcp.invariantlabs.ai/api/v1/public/mcp-analysis` (hardcoded in `lib.py`) to `https://api.snyk.io/hidden/mcp-scan/analysis-machine?version=2025-09-02` (CLI default in `cli.py`)
- New Snyk Evo integration commands (`evo` subcommand) for pushing results to Snyk platform
- Terms of service (TERMS.md) are for "Invariant Labs AG" -- not yet updated to Snyk terms
- "All rights assigned" clause on user feedback in TERMS.md

**Verdict:** Ownership transition is neutral-to-positive for security posture. Snyk has stronger institutional security practices than a startup. However, the transition is incomplete (mixed branding, dual analysis endpoints, old terms).

---

## 3. Typosquatting Analysis

| Severity | INFO |
|----------|------|

**Package name:** `mcp-scan`

Checked against known patterns:
- `mcpscan` -- not found on PyPI as a distinct malicious package
- `mcp_scan` -- PyPI normalizes underscores to hyphens; points to same package
- `mcp-scanner` -- exists as `cisco-ai-defense/mcp-scanner` (legitimate, different tool)
- `mcp-scam` -- Levenshtein distance 1; not found on PyPI

**Verdict:** No typosquatting risk detected for the `mcp-scan` package name. The Cisco tool `mcp-scanner` is a legitimate separate project.

---

## 4. Repository Structure Analysis

```
.circleci/              CI/CD configuration
.github/                GitHub workflows and reports
demoserver/             Vulnerable MCP server demonstration (for testing)
src/
  analyze.py            Standalone analysis module
  agent_scan/           Core package (24 files)
    MCPScanner.py       Main scanner orchestrator
    Storage.py          Local state persistence (~/.mcp-scan/)
    cli.py              CLI entry point and argument parsing
    direct_scanner.py   Package/URL/tool scanning
    identity.py         UUID-based anonymous identity management
    inspect.py          MCP server inspection
    lib.py              High-level scan/inspect API
    mcp_client.py       MCP protocol client (stdio/SSE/HTTP)
    mcp_server.py       MCP server mode (for integration)
    models.py           Pydantic models for all data structures
    pipelines.py        inspect -> redact -> analyze -> push pipeline
    policy.gr           Policy grammar file (lark parser)
    printer.py          Console output formatting
    redact.py           Secret/path redaction before upload
    run.py              Entry point bootstrap
    signed_binary.py    macOS codesign verification
    skill_client.py     Skill file scanning
    traffic_capture.py  MCP traffic logging (in-memory)
    upload.py           Results upload to control servers
    utils.py            Command resolution, temp files, headers
    verify_api.py       Analysis API client with retry logic
    version.py          Version constant
    well_known_clients.py  Client discovery (Claude, Cursor, VSCode, etc.)
tests/                  Test suite
```

**Verdict:** Structure is clean and well-organized. No unexpected files, no binary blobs, no obfuscated modules.

---

## 5. Dangerous Code Pattern Analysis

### 5.1 eval() / exec() / compile() / __import__()

| Severity | INFO |
|----------|------|

**None detected** across all 24 source files reviewed. The codebase uses JSON parsing (pyjson5), regex, and Pydantic validation -- no dynamic code execution.

### 5.2 subprocess usage

| Severity | INFO |
|----------|------|

Found in two locations, both **legitimate for the tool's purpose**:

1. **`signed_binary.py`**: `subprocess.run(["codesign", "-dvvv", command])` -- macOS-only binary signature verification. Input is the resolved server command path, not user-controlled arbitrary strings.

2. **`direct_scanner.py`**: Generates subprocess configs for `npx`, `uvx`, and `docker` to scan npm/PyPI/OCI packages. These commands use package names from the user's own CLI arguments, not from external/untrusted input.

3. **`mcp_client.py`**: Spawns MCP servers via `StdioServerParameters(command, args, env)` from the user's local MCP configuration files. This is the tool's core function -- it must start MCP servers to inspect them.

**Verdict:** All subprocess usage is inherent to the scanner's purpose. No arbitrary command injection vectors detected. The tool executes commands already present in the user's MCP configuration (which the user already trusts enough to have configured).

### 5.3 Hardcoded external domains / data exfiltration endpoints

| Severity | WARNING |
|----------|---------|

Two distinct external endpoints identified:

| Endpoint | Location | Purpose |
|----------|----------|---------|
| `https://mcp.invariantlabs.ai/api/v1/public/mcp-analysis` | `lib.py` (default) | Legacy analysis API |
| `https://api.snyk.io/hidden/mcp-scan/analysis-machine?version=2025-09-02` | `cli.py` (default) | Current analysis API |
| `https://api.snyk.io/hidden/mcp-scan/push?version=2025-08-28` | `cli.py` | Snyk Evo push endpoint |
| `https://api.snyk.io/hidden/tenants/{tenant_id}/mcp-scan/push-key?version=2025-08-28` | `cli.py` | Snyk Evo key management |

**What is sent to the analysis endpoint (always, even with --opt-out):**
- Tool names and descriptions from scanned MCP servers
- Server names and types
- Scan metadata (CLI version)
- Anonymous UUID identifier

**What is sent only WITHOUT --opt-out:**
- Hostname
- Username
- Non-anonymous identifier (if provided via `--control-identifier`)

**What is NEVER sent (redacted before upload):**
- Environment variable values (redacted to `**REDACTED**`)
- Command-line argument values for flags
- HTTP header values
- Absolute file paths
- URL query parameter values

**Verdict:** The analysis endpoint call is **always made** during scan operations (it is the verification backend). The `--opt-out` flag only controls identity-related fields, not the transmission of tool descriptions. This was documented in our original approval but bears re-emphasis: **tool descriptions from your MCP servers are always sent to Snyk's API for analysis**.

### 5.4 File system access

| Severity | INFO |
|----------|------|

**Read locations:**
- `~/.mcp-scan/` -- local state storage (identity, scan history)
- MCP configuration files at well-known paths for: Claude, Claude Code, Cursor, VSCode, Windsurf, Gemini CLI, Kiro, Opencode, Antigravity, Codex (11 clients)
- Skill directories (e.g., `~/.claude/skills/`)

**Write locations:**
- `~/.mcp-scan/identity.json` -- anonymous UUID
- `~/.mcp-scan/` -- scan results storage
- Temporary files via `tempfile.NamedTemporaryFile()` (cleaned up in `__exit__`)

**Verdict:** File access is scoped to expected locations. No writes outside the user's home directory. No access to project source code or secrets directories.

---

## 6. Permissions and Capabilities

| Capability | Required | Justification |
|------------|----------|---------------|
| Read MCP configs | Yes | Core function: discover MCP servers |
| Spawn subprocesses | Yes | Core function: start MCP servers to inspect them |
| Network outbound (Snyk API) | Yes | Analysis/verification backend |
| Read skill files | Yes | Skill scanning feature |
| Write to ~/.mcp-scan/ | Yes | Persist scan state and identity |
| macOS codesign (optional) | No | Binary signature verification, macOS only |

**Risk classification per Cerbero:** HIGH (network outbound + subprocess execution). However, both capabilities are inherent to the tool's stated purpose as a security scanner.

---

## 7. PyPI-to-GitHub Version Mismatch

| Severity | WARNING |
|----------|---------|

| Source | Package name | Version |
|--------|-------------|---------|
| PyPI | `mcp-scan` | 0.4.2 |
| GitHub main | `snyk-agent-scan` | 0.4.3 |
| PyPI | `snyk-agent-scan` | Not yet published (or page failed to load) |

The GitHub `main` branch is one version ahead of the PyPI `mcp-scan` package. The v0.4.3 rename means future PyPI publications will likely be under `snyk-agent-scan`, not `mcp-scan`.

**Action required:** Pin to `mcp-scan==0.4.2` in our usage until migration path is confirmed.

---

## 8. Dependency Analysis

Core dependencies from `pyproject.toml`:

| Dependency | Version | Risk Notes |
|------------|---------|------------|
| rich | 14.2.0 | Console formatting, low risk |
| pydantic | >2.11.2 | Data validation, low risk |
| fastapi | >0.115.12 | Used for proxy mode only |
| aiohttp | >3.11.16 | HTTP client, moderate (network) |
| pyyaml | >6.0.2 | YAML parsing, low risk |
| mcp[cli] | 1.25.0 | MCP protocol client, moderate |
| lark | -- | Grammar parser (policy.gr), low risk |
| psutil | -- | Process management, low risk |
| pyjson5 | -- | JSON5 parsing, low risk |
| rapidfuzz | -- | Fuzzy string matching, low risk |
| filelock | -- | File locking, low risk |
| truststore | -- | System trust store for TLS, low risk |
| regex | -- | Extended regex, low risk |

**Notable:** `fastapi` is listed as a core dependency but is only used for proxy mode. This adds unnecessary attack surface for CLI-only usage.

---

## 9. Redaction Thoroughness Assessment

| Severity | SUGGESTION |
|----------|------------|

The `redact.py` module provides reasonable coverage:

**Redacted:** env var values, CLI flag values, HTTP headers, URL query params, absolute paths (Unix, Windows, home dir)

**Gaps identified:**
- Relative paths (`./config`, `../secrets`) are NOT redacted
- URL path segments remain visible (e.g., `/home/user/` in a URL path)
- Tool description content is sent verbatim (by design -- this is what gets analyzed)

**Verdict:** Redaction is adequate for the tool's purpose. The gaps are minor and unlikely to leak secrets in normal usage. The fact that tool descriptions are sent unredacted is inherent to the analysis function.

---

## 10. Summary of Findings

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | CRITICAL | Package name divergence: PyPI `mcp-scan` v0.4.2 vs GitHub `snyk-agent-scan` v0.4.3. Future updates will not arrive under `mcp-scan`. | ACTION: Monitor, plan migration |
| 2 | WARNING | Ownership transition (Invariant Labs -> Snyk). Analysis endpoint migrating from invariantlabs.ai to api.snyk.io. | MONITOR |
| 3 | WARNING | Dual hardcoded analysis endpoints (legacy + current). Unclear which is used in v0.4.2 vs v0.4.3. | MONITOR |
| 4 | WARNING | PyPI version (0.4.2) lags GitHub main (0.4.3). Version mismatch during rename transition. | MONITOR |
| 5 | WARNING | Tool descriptions from scanned MCP servers are ALWAYS sent to Snyk API, even with `--opt-out`. The flag only suppresses identity fields. | ACCEPTED (known, documented in original approval) |
| 6 | SUGGESTION | FastAPI in core deps adds attack surface unused in CLI mode | LOW priority |
| 7 | SUGGESTION | Relative path redaction gap | LOW priority |
| 8 | INFO | No eval/exec/compile detected | CLEAN |
| 9 | INFO | Subprocess usage is legitimate and scoped | CLEAN |
| 10 | INFO | No typosquatting risk detected | CLEAN |
| 11 | INFO | File access scoped to ~/.mcp-scan/ and MCP config paths | CLEAN |
| 12 | INFO | Apache-2.0 license, active development, 1.7k stars | CLEAN |

---

## 11. Verdict

**APPROVED -- conditions updated**

The original approval (2026-02-20) remains valid. mcp-scan v0.4.2 is safe to use under the existing conditions. However, the Snyk acquisition and package rename introduce new operational considerations.

### Updated conditions (supersede original):

1. **`--opt-out` mandatory** (unchanged) -- suppresses hostname/username transmission
2. **Scan-only mode** (unchanged) -- no proxy/intercept mode in production
3. **Pin to `mcp-scan==0.4.2`** (NEW) -- until `snyk-agent-scan` PyPI package is confirmed available and reviewed
4. **Monitor Snyk package transition** (UPDATED from "monitor Snyk ownership transition") -- watch for:
   - `mcp-scan` PyPI deprecation notice
   - `snyk-agent-scan` PyPI publication
   - Changes to analysis endpoint or data collection scope
5. **Re-evaluate at migration** (NEW) -- when switching to `snyk-agent-scan`, perform a delta review of v0.4.3+ changes
6. **Accept that tool descriptions are transmitted** (EXPLICIT) -- this is inherent to the analysis function; do not scan MCP servers containing secrets in tool descriptions

---

## Sources

- [Snyk acquires Invariant Labs (official)](https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/)
- [Snyk Labs + Invariant Labs announcement](https://labs.snyk.io/resources/snyk-labs-invariant-labs/)
- [GitHub repository (invariantlabs-ai/mcp-scan)](https://github.com/invariantlabs-ai/mcp-scan)
- [PyPI mcp-scan](https://pypi.org/project/mcp-scan/)
- [Introducing MCP-Scan (original blog)](https://invariantlabs.ai/blog/introducing-mcp-scan)
- [Snyk Agent Scan documentation](https://docs.snyk.io/integrations/snyk-studio-agentic-integrations)
- [DeepWiki snyk/agent-scan](https://deepwiki.com/snyk/agent-scan)
- [SiliconANGLE acquisition coverage](https://siliconangle.com/2025/06/24/snyk-acquires-invariant-labs-expand-ai-agent-security-capabilities/)
