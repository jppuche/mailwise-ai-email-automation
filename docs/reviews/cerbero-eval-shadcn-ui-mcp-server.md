# CERBERO -- MCP EVALUATION REPORT: shadcn-ui-mcp-server

```
Package: @jpisnice/shadcn-ui-mcp-server@2.0.0
Approved SHA: 7492aa2acf260f44d277063c41493832c49bf48e
Source: https://github.com/Jpisnice/shadcn-ui-mcp-server
Publisher: Janardhan Pollle (jpisnice) | Trusted: NO
Date: 2026-03-02
Transport: stdio (default) / SSE (optional, port 7423)
```

---

## STEP 1 -- SOURCE CODE

### Typosquat check: PASS
- Package name `@jpisnice/shadcn-ui-mcp-server` is scoped under author's npm namespace. No collision with other known packages. Note: an unscoped `shadcn-ui-mcp-server` also exists (different publisher `heilgar`), but the scoped variant is the one linked from official shadcn docs.

### Supply chain integrity: PASS (with notes)
- npm version 2.0.0 matches GitHub repository HEAD. GitHub has 2.6k stars, 284 forks.
- npm publish date: recent (within last month). Active release cadence.
- Version 2.0.0 is a major bump from 1.1.0 -- introduced the TweakCN theme tools including filesystem write.

### Dangerous patterns: 3 CRITICAL FINDINGS

**FINDING C-01: `new Function()` (equivalent to eval) in fetch-presets.js**
```javascript
// build/tools/tweakcn/fetch-presets.js
const obj = new Function(`return (${sanitized})`)();
```
- This parses theme preset data fetched from `https://raw.githubusercontent.com/jnsahaj/tweakcn/main/utils/theme-presets.ts` by constructing a JavaScript function from the raw string content.
- The data comes from a THIRD-PARTY GitHub repository (`jnsahaj/tweakcn`) -- not from shadcn-ui/ui.
- If the `tweakcn` repo is compromised, arbitrary JavaScript code would execute in the MCP server process.
- **Severity: CRITICAL** -- remote code execution via supply chain.

**FINDING C-02: Filesystem write in locate-and-write.js**
```javascript
// build/tools/tweakcn/locate-and-write.js
await fs.promises.writeFile(filePath, out, "utf8");
await fs.promises.mkdir(path.dirname(filePath), { recursive: true });
```
- The `apply_theme` tool writes CSS content to the user's project files.
- Target path is determined by `locateGlobalCss(process.cwd())` or defaults to `src/styles/globals.css`.
- Creates backup files (`.mcp-backup-*`).
- Write scope is NOT sandboxed -- writes to `process.cwd()` which is the project root.
- **Severity: HIGH** -- filesystem write access to project directory.

**FINDING C-03: DNS rebinding protection disabled in SSE mode**
```javascript
// build/server/sse.js
const transport = new SSEServerTransport('/message', res, {
    enableDnsRebindingProtection: false
});
```
- When running in SSE mode (multi-client), DNS rebinding protection is explicitly disabled.
- This is the same class of vulnerability as CVE-2025-9611 in Playwright MCP (CVSS 7.2).
- Default host is `0.0.0.0` (all interfaces), making this exploitable from any network.
- **Severity: HIGH** (only applies to SSE mode, not default stdio mode).

### Additional findings

**FINDING W-01: Arbitrary GitHub repository access via get_directory_structure**
```javascript
// build/tools/repository/get-directory-structure.js
const directoryTree = await axios.buildDirectoryTree(
    owner || axios.paths.REPO_OWNER,
    repo || axios.paths.REPO_NAME, ...
);
```
- The `owner` and `repo` parameters allow browsing ANY public GitHub repository, not just shadcn-ui/ui.
- Risk: information disclosure, SSRF via GitHub API proxy.
- **Severity: MEDIUM** -- read-only, but scope exceeds stated purpose.

**FINDING W-02: GitHub Personal Access Token in environment**
- Reads `GITHUB_PERSONAL_ACCESS_TOKEN` from environment.
- Used only for rate limiting (60 req/h unauthenticated, 5000 req/h authenticated).
- Token scopes are not validated -- a token with `repo` scope would grant the server access to private repos.
- **Severity: LOW** -- optional, but users should create a minimal-scope token.

### Tool schemas: PASS (no injection patterns)
All 10 tool descriptions are declarative, under 200 characters, no imperative language targeting the model.

| Tool | Description | Schema |
|------|-------------|--------|
| `get_component` | Get source code for a shadcn/ui v4 component | PASS |
| `get_component_demo` | Get demo code for component usage | PASS |
| `list_components` | Get all available components | PASS |
| `get_component_metadata` | Get metadata for a component | PASS |
| `get_directory_structure` | Get directory structure of repo | PASS (see W-01) |
| `get_block` | Get source code for a shadcn/ui v4 block | PASS |
| `list_blocks` | Get all available blocks | PASS |
| `apply_theme` | Apply a TweakCN theme preset | PASS (see C-01, C-02) |
| `list_themes` | List available tweakcn themes | PASS |
| `get_theme` | Get details of a specific theme | PASS |

### Auth check: N/A (stdio transport default)

---

## STEP 2 -- REPUTATION & COMMUNITY

- **Stars:** 2,600 | **Forks:** 284 | **Last updated:** within last month
- **Publisher:** jpisnice (Janardhan Pollle) -- NOT in trusted-publishers.txt
- **Official endorsement:** Listed on https://ui.shadcn.com/docs/mcp as the recommended MCP server
- **Web research findings:** Socket.dev reports 2 HIGH alerts on dependencies (not elaborated)
- **CVEs:** NONE specific to this package

---

## STEP 3 -- DEPENDENCIES

```
npm audit: 0 vulnerabilities (282 packages audited)
npm provenance: 281 packages verified signatures, 8 verified attestations
```

- **Deprecated packages:** glob@7.2.3, boolean@3.2.0, read-installed@4.0.3 (no security impact)
- **Dependency count:** 281 transitive dependencies (HIGH for an MCP server)
- **Notable dependencies:** express, axios, cheerio, winston, joi, zod, cors, uuid
- Express + cors included for SSE mode -- unnecessary weight for stdio usage

---

## STEP 4 -- AUTOMATED SCAN

mcp-scan: SKIPPED (not run in this evaluation -- available if requested)

---

## STEP 4b -- SEMANTIC ANALYSIS

**Status:** PERFORMED

**Tier 1-2 findings:**
- C-01: `new Function()` pattern detected -- equivalent to `eval()` (CRITICAL)
- C-02: `fs.writeFileSync` / `fs.promises.writeFile` outside read-only scope (HIGH)
- C-03: `enableDnsRebindingProtection: false` in SSE transport (HIGH)

**Tier 3 (semantic) findings:**
- Tool descriptions are clean -- no prompt injection patterns detected
- Prompt templates (5 prompts) contain instructional text but are user-facing, not model-targeting
- No encoded content, no zero-width characters, no hidden directives

---

## STEP 5 -- RISK CLASSIFICATION

| Capability | Present | Risk |
|-----------|---------|------|
| Network outbound (GitHub API, raw.githubusercontent.com, jnsahaj/tweakcn) | YES | HIGH |
| Filesystem write (CSS files in project) | YES | CRITICAL |
| Shell execution | NO | -- |
| `eval`/`new Function` (remote code) | YES | CRITICAL |

**Overall risk: CRITICAL** -- Filesystem write + network outbound + `new Function()` on remote data.

---

## VERDICT: REJECTED

**REASON:** `new Function()` on content fetched from third-party GitHub repository (`jnsahaj/tweakcn`) constitutes remote code execution risk. Combined with filesystem write access and 281 transitive dependencies, the attack surface is unacceptable. DNS rebinding protection explicitly disabled in SSE mode compounds the risk.

### Detailed rejection rationale

1. **C-01 is a dealbreaker.** The `fetch-presets.js` file downloads TypeScript source code from a third-party repo and executes it via `new Function()`. If `jnsahaj/tweakcn` is compromised (account takeover, malicious PR), arbitrary code runs in the MCP server context with full filesystem and network access. This is textbook supply chain RCE.

2. **C-02 is addressable but compounds C-01.** Filesystem write to project CSS files is a legitimate feature for theme application, but combined with the RCE in C-01, it becomes a write-anywhere primitive.

3. **The 7 read-only tools (get_component, list_components, etc.) are safe.** The security issues are concentrated in the 3 TweakCN theme tools added in v2.0.0.

### Path to approval

If the maintainer addresses these issues, re-evaluate:

1. **Replace `new Function()` with a proper JSON/TypeScript parser** -- no dynamic code execution
2. **Pin the tweakcn preset source** to a specific commit SHA, not `main` branch
3. **Enable DNS rebinding protection** in SSE transport
4. **Scope `get_directory_structure`** to shadcn-ui org repos only

### Alternative: Use v1.x (pre-TweakCN)

If version 1.1.0 does not contain the TweakCN tools, it may be safe. Requires separate evaluation.

### Alternative: Fork and strip TweakCN tools

Remove `apply_theme`, `list_themes`, `get_theme` and all `tweakcn/` code. The remaining 7 tools are read-only network fetches to GitHub API with no filesystem access.

---

*Evaluated by: Sentinel (Cerbero framework v1.0)*
*OWASP MCP coverage: MCP01 (token in env), MCP03 (tool poisoning -- clean), MCP04 (supply chain -- FAIL), MCP05 (command injection -- new Function), MCP06 (prompt injection -- clean)*
