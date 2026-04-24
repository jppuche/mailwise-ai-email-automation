# CERBERO -- MCP EVALUATION REPORT: Playwright MCP

```
Package: @playwright/mcp@0.0.68
Approved SHA: 76048eaacbdfa38af328fc890d78180a8f80f643
Source: https://github.com/microsoft/playwright-mcp
Publisher: Microsoft Corporation | Trusted: NO (not in trusted-publishers.txt, but Fortune 10)
Date: 2026-03-02
Transport: stdio (default) / HTTP (optional, --port flag)
```

---

## STEP 1 -- SOURCE CODE

### Typosquat check: PASS
- Package `@playwright/mcp` is under the official `@playwright` npm scope, owned by Microsoft. No typosquat risk.
- Note: `playwright-mcp` (unscoped, by executeautomation) is a DIFFERENT package. Ensure correct scoped name.

### Supply chain integrity: PASS
- npm publisher is Microsoft. Package aligns with GitHub repo `microsoft/playwright-mcp`.
- 27,900 GitHub stars. 1,360,343 weekly npm downloads. Extremely high adoption.
- Apache-2.0 license. Active development (last publish ~14 days ago).
- Only 7 files in npm package -- extremely lean distribution.

### Package analysis

The npm package is a thin wrapper:
```javascript
// cli.js -- entry point
const { program } = require('playwright-core/lib/utilsBundle');
const { decorateMCPCommand } = require('playwright/lib/mcp/program');
```

```javascript
// index.js -- programmatic API
const { createConnection } = require('playwright/lib/mcp/index');
module.exports = { createConnection };
```

All MCP logic lives inside `playwright` and `playwright-core` (pinned at `1.59.0-alpha-1771104257000`). The `@playwright/mcp` package itself contains zero tool definitions -- it delegates entirely to the Playwright library.

### Dependencies: MINIMAL
```json
{
  "playwright": "1.59.0-alpha-1771104257000",
  "playwright-core": "1.59.0-alpha-1771104257000"
}
```
Only 2 direct dependencies, both official Playwright packages by Microsoft.

### Dangerous patterns: NONE in the wrapper

Since all logic is in `playwright-core`, dangerous patterns are evaluated at the capability level (see Capabilities below).

### Tool schemas: PASS

70+ tools organized in 7 capability groups. Three always-on, four opt-in:

| Capability Group | Default | Tools (examples) |
|-----------------|---------|------------------|
| **core** (always on) | YES | `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_fill`, `browser_select_option`, `browser_hover`, `browser_drag`, `browser_press_key`, `browser_wait`, `browser_close` |
| **core-tabs** (always on) | YES | `browser_tab_list`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close` |
| **core-install** (always on) | YES | `browser_install` |
| **vision** (opt-in) | NO | `browser_screen_capture`, `browser_screen_move_mouse`, `browser_screen_click`, `browser_screen_drag`, `browser_screen_type` |
| **pdf** (opt-in) | NO | `browser_pdf_save` |
| **testing** (opt-in) | NO | `browser_generate_playwright_test`, `browser_assert_snapshot` |
| **tracing** (opt-in) | NO | `browser_save_as_trace` |

Tool descriptions are clean, declarative, appropriately sized. No injection patterns detected in any tool schema field.

### Auth check: N/A (stdio transport default)
- HTTP mode (`--port`) available but requires explicit opt-in.
- As of v0.0.40+, Origin header validation is enforced in HTTP mode (CVE-2025-9611 fix).

---

## STEP 2 -- REPUTATION & COMMUNITY

- **Stars:** 27,900 | **Downloads/week:** 1,360,343 | **Last updated:** ~14 days ago
- **Publisher:** Microsoft Corporation -- NOT in trusted-publishers.txt but is a Fortune 10 company with established security practices (MSRC, bug bounty program)
- **Security policy:** Vulnerabilities reported via MSRC (https://msrc.microsoft.com/create-report)
- **Web research findings:** 1 CONFIRMED VULNERABILITY (patched)

### CVE-2025-9611: DNS Rebinding (PATCHED)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-9611 |
| **GHSA** | GHSA-8rgw-6xp9-2fg3 |
| **CVSS** | 7.2 (HIGH) -- CVSS 4.0 |
| **Affected** | @playwright/mcp < 0.0.40 |
| **Fixed** | @playwright/mcp >= 0.0.40 |
| **Published** | 2026-01-07 |
| **CWE** | CWE-749 (Exposed Dangerous Method or Function) |

**Description:** Versions prior to 0.0.40 failed to validate the Origin header on incoming HTTP connections, allowing DNS rebinding attacks from malicious websites to invoke MCP tool endpoints via the victim's browser.

**Current status:** PATCHED in v0.0.40. Current version is 0.0.68 -- well past the fix. This vulnerability only affected HTTP transport mode (`--port`), not stdio.

**Note:** The MCP TypeScript SDK itself had the same class of vulnerability (CVE-2025-66414, GHSA-w48q-cv73-mx4w). Both are fixed in current versions.

### Indirect prompt injection risk (COMMUNITY CONCERN)

Multiple security researchers have documented that browser automation MCP servers are inherently vulnerable to indirect prompt injection:
- Malicious content on web pages is captured in accessibility snapshots
- The LLM processes this content and may follow injected instructions
- This is a fundamental limitation of browser automation, not specific to this implementation

**Mitigation:** Use only on trusted/controlled pages (localhost, staging environments). Do not browse arbitrary user-generated content.

---

## STEP 3 -- DEPENDENCIES

```
npm audit: 0 vulnerabilities (3 packages audited)
npm provenance: 2 packages verified signatures, 2 verified attestations
```

- Only 2 transitive dependencies (playwright + playwright-core), both from Microsoft
- No deprecated packages
- Signature verification: PASSED

---

## STEP 4 -- AUTOMATED SCAN

mcp-scan: SKIPPED (not run in this evaluation -- available if requested)

---

## STEP 4b -- SEMANTIC ANALYSIS

**Status:** PERFORMED

**Tier 1-2 findings:** CLEAN
- No `eval`, `exec`, `spawn` with user-controlled arguments in the wrapper
- No hardcoded external domains (all browser navigation is user-directed)
- No telemetry or phone-home code in the wrapper
- Tool descriptions are declarative and clean

**Tier 3 (semantic) findings:** CLEAN
- No prompt injection patterns in tool schemas
- No encoded content or hidden directives
- Capability group system provides defense-in-depth (vision, pdf, testing, tracing require explicit opt-in)

---

## STEP 5 -- RISK CLASSIFICATION

| Capability | Present | Risk |
|-----------|---------|------|
| Network outbound (browser navigates to any URL) | YES | HIGH |
| Filesystem write (screenshots, PDFs, traces, videos) | YES (opt-in) | HIGH |
| Browser binary installation (`browser_install` tool) | YES | HIGH |
| Shell execution | NO (browser subprocess, not arbitrary shell) | -- |
| Sampling/bidirectional LLM | NO | -- |

**Overall risk: HIGH** -- Network outbound (arbitrary URLs) + filesystem write (output files) + browser binary download.

### Key security controls already in place

1. **Capability opt-in system:** Vision, PDF, testing, tracing capabilities require explicit `--caps` flag. Only core navigation/interaction tools are enabled by default.
2. **Host allowlisting:** `--allowed-hosts` flag restricts which domains the browser can navigate to.
3. **Origin allowlisting:** `--allowed-origins` flag restricts which origins can connect in HTTP mode.
4. **Output directory control:** `--output-dir` controls where screenshots/PDFs/traces are saved.
5. **Secrets masking:** `--secrets` flag prevents sensitive data from appearing in snapshots.
6. **DNS rebinding protection:** Enabled by default since v0.0.40.

---

## VERDICT: REQUIRES HUMAN REVIEW

**REASON:** Publisher (Microsoft) is not in trusted-publishers.txt. Risk is HIGH due to browser automation scope (arbitrary URL navigation, browser binary installation, filesystem write for outputs). CVE-2025-9611 is patched in current version. Indirect prompt injection via web content is an inherent class-level risk.

### Recommendation: APPROVE WITH CONDITIONS

Despite the REQUIRES HUMAN REVIEW verdict (due to publisher not being in trusted list), Sentinel recommends approval based on:

1. Microsoft is the publisher with 27.9k stars and 1.36M weekly downloads
2. The package is a 7-file thin wrapper over official Playwright (no custom code)
3. npm audit is clean, provenance is verified, dependency count is minimal (2)
4. CVE-2025-9611 is patched; no active vulnerabilities
5. Built-in capability opt-in system provides granular permission control
6. Host allowlisting provides network scoping

### CONDITIONS (if approved)

1. **Pin version:** Install `@playwright/mcp@0.0.68`, not `@latest`. The `@latest` tag in the suggested install command is a supply chain risk -- a compromised future version would auto-install.

2. **Restrict hosts to localhost:** Configure with `--allowed-hosts "localhost,127.0.0.1"` for UI redesign validation. Only expand if explicitly needed.

3. **Do NOT enable vision, pdf, testing, or tracing capabilities** unless specifically needed. Default core capabilities are sufficient for accessibility-tree-based validation.

4. **Output directory:** If screenshots are needed (vision opt-in), configure `--output-dir` to a dedicated directory outside the project source tree.

5. **Never browse untrusted URLs:** Indirect prompt injection via web content is a known class-level risk. Restrict usage to localhost dev server and known staging URLs.

6. **Add Microsoft to trusted-publishers.txt** for this project (human decision).

### Recommended install command

```bash
claude mcp add playwright -- npx @playwright/mcp@0.0.68 --allowed-hosts "localhost,127.0.0.1"
```

---

*Evaluated by: Sentinel (Cerbero framework v1.0)*
*OWASP MCP coverage: MCP01 (no tokens required), MCP02 (capability opt-in system), MCP03 (tool poisoning -- clean), MCP04 (supply chain -- minimal deps, verified), MCP05 (command injection -- no shell), MCP06 (prompt injection -- inherent browser risk, documented), MCP08 (MSRC security policy)*
