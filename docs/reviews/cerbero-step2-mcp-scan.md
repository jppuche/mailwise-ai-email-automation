# Cerbero Step 2: Reputation and Community Intelligence -- mcp-scan

**Date:** 2026-03-02
**Analyst:** Sentinel (opus)
**Package:** mcp-scan (PyPI) / invariantlabs-ai/mcp-scan (GitHub)
**Publisher:** invariantlabs-ai (Invariant Labs AG, acquired by Snyk June 2025)
**Trusted publisher list status:** NOT in trusted-publishers.txt (list contains: anthropic, trailofbits)

---

## 1. Package Identity

| Field | Value |
|-------|-------|
| PyPI name | `mcp-scan` |
| GitHub repo | `invariantlabs-ai/mcp-scan` (redirects to `snyk/agent-scan`) |
| Current version | 0.4.2 (released 2026-02-18) |
| First published | 2025-04-07 (v0.1.2) |
| Package age | ~11 months |
| Stars | 1,700+ |
| Forks | 162 |
| Open issues | 11 |
| Total commits | 345 (main branch) |
| License | Apache-2.0 |
| Language | Python (90.2%) |
| Python requirement | >=3.10 |
| SECURITY.md | Present (points to Snyk vulnerability reporting) |
| Published advisories | None |
| Contributions | CLOSED ("Agent Scan is closed to contributions") |

## 2. Publisher Profile

### Invariant Labs AG

- **Origin:** ETH Zurich spin-off (Department of Computer Science)
- **Founded:** 2024
- **Co-founders:** Professors Martin Vechev and Florian Tramer (ETH Zurich) + three graduates
- **Specialization:** AI security research -- guardrails, runtime detection, MCP vulnerability research
- **Acquisition:** Snyk acquired Invariant Labs on 2025-06-24 for undisclosed price
- **Post-acquisition:** Team integrated into Snyk Labs research division
- **Notable research:** First to disclose GitHub MCP vulnerability (May 2025) where attackers embedded malicious commands in public Issues to hijack locally running AI Agents

### Snyk (Parent Company)

- **Industry position:** Leading developer security platform
- **Relevance:** Series G funded, well-known in CVE/vulnerability database space
- **MCP strategy:** Launched "AI Trust Platform" incorporating Invariant Labs technology
- **Repository rename:** `invariantlabs-ai/mcp-scan` now redirects to `snyk/agent-scan`

### Publisher Risk Assessment

The publisher has strong academic credentials (ETH Zurich) and is now owned by an established security company (Snyk). However:
- Invariant Labs is NOT in our trusted-publishers.txt
- Snyk is NOT in our trusted-publishers.txt
- The project is closed to external contributions (limits community audit)
- Post-acquisition governance is fully under Snyk corporate control

## 3. Search Results Classification

### Search 1: "mcp-scan" vulnerability OR "prompt injection" OR "security"

**Classification: NO FINDINGS (for mcp-scan itself)**

No confirmed vulnerabilities were found IN mcp-scan. Search results extensively cover MCP ecosystem vulnerabilities that mcp-scan is designed to detect (tool poisoning, prompt injection, rug pulls). The tool is consistently referenced as a defensive scanner, not as a vulnerable component. Key ecosystem context:

- 8,000+ MCP servers exposed (Feb 2026)
- 7 MCP CVEs in February 2026 alone
- CVE-2025-6514 (mcp-remote OAuth proxy) -- 437,000 environments compromised
- CVE-2025-49596 (MCP Inspector RCE, CVSS 9.4)
- Multiple CVEs in Anthropic's own mcp-server-git

None of these CVEs involve mcp-scan.

### Search 2: "mcp-scan" MCP site:github.com/issues

**Classification: COMMUNITY CONCERN (minor)**

Issues found in `snyk/agent-scan` repository:

| Issue | Title | Status | Severity |
|-------|-------|--------|----------|
| #125 | `--local-only` flag not supported for scan command | Open | LOW -- documentation/functionality mismatch |
| #75 | External analysis server returning 500 Internal Server Error | Open | MEDIUM -- external dependency failure |
| #21 | What is the most common threat in mcp development? | Open | INFO -- question, not vulnerability |
| #7 | Enhancement: Scan MCP Servers Independently | Open | INFO -- feature request |

No security vulnerabilities reported by users. Issue #75 (server 500 errors) indicates a dependency on Invariant Labs external API for analysis, which is a reliability concern but not a security vulnerability.

### Search 3: "mcp-scan" site:snyk.io OR site:lasso.security

**Classification: NO FINDINGS**

Snyk's own documentation references mcp-scan/agent-scan as a legitimate product. Snyk Labs publishes research on tool poisoning detection using this scanner. No self-reported vulnerabilities or concerns found on snyk.io. No results found on lasso.security.

### Search 4 (additional): CVE databases

**Classification: NO FINDINGS**

No CVEs associated with mcp-scan or agent-scan. The tool has no published security advisories on its GitHub repository.

### Search 5 (additional): Telemetry and privacy concerns

**Classification: COMMUNITY CONCERN (documented, mitigated)**

| Data sent externally | Destination | Opt-out |
|---------------------|-------------|---------|
| Tool names and descriptions | invariantlabs.ai API | `--opt-out` flag |
| Persistent anonymous user ID | invariantlabs.ai | `--opt-out` flag |
| Scan results (redacted) | Control server(s) | `--control-server` to redirect |

Mitigations already in place:
- Sensitive data (file paths, env vars, HTTP headers, CLI args) redacted before upload
- Proxy mode guardrails evaluation is entirely local (no MCP traffic sent externally)
- `--opt-out` flag disables anonymous ID and external API calls
- `--local-only` flag prevents contributing to global whitelist (though Issue #125 reports this flag may not work)

**Our existing condition (from DECISIONS.md):** `--opt-out` is MANDATORY for our usage. This aligns with Cerbero Permanent Rule 9 (informed decisions on data collection).

## 4. Competitive Landscape

mcp-scan is not the only MCP security scanner. Alternatives discovered:

| Tool | Publisher | Notes |
|------|-----------|-------|
| cisco-ai-defense/mcp-scanner | Cisco | Security scanning for MCP servers |
| ressl/mcpwn | Independent | Tests prompt injection, tool poisoning, data exfiltration |
| highflame-ai/ramparts | Independent | Static analysis, cross-origin detection |
| sinewaveai/agent-security-scanner-mcp | Sinewave AI | Prompt injection firewall, package hallucination detection |
| kapilduraphe/mcp-watch | Independent | Security scanner for MCP implementations |

mcp-scan remains the most established (1.7K stars, Snyk backing, 11 months history, 345 commits).

## 5. Repository Transition Risk

**Classification: COMMUNITY CONCERN**

- `invariantlabs-ai/mcp-scan` redirects to `snyk/agent-scan`
- The hosted Invariant Explorer was shut down in January 2026
- The product has been rebranded from "MCP Scan" to "Agent Scan" with broader scope (agents, skills, MCP servers)
- The package name on PyPI remains `mcp-scan` (v0.4.2) but releases now dual-publish as "Agent Scan" snapshots

This creates uncertainty about:
1. Whether `mcp-scan` PyPI package will be deprecated in favor of a new `agent-scan` package
2. Whether the external API endpoint (invariantlabs.ai) will migrate to snyk.io
3. Long-term maintenance commitment to the open-source version vs. Snyk's commercial AI Trust Platform

## 6. Consolidated Findings

### CONFIRMED VULNERABILITY: None

No CVEs, no security advisories, no confirmed vulnerabilities in mcp-scan itself.

### COMMUNITY CONCERN: 3 findings

| ID | Finding | Severity | Source |
|----|---------|----------|--------|
| CC-01 | External API dependency for analysis (invariantlabs.ai server) -- Issue #75 reports 500 errors; single point of failure | MEDIUM | GitHub Issue #75 |
| CC-02 | Telemetry sends tool names/descriptions + anonymous UUID externally by default | MEDIUM | DeepWiki analysis, Snyk documentation |
| CC-03 | Repository transition (invariantlabs-ai -> snyk/agent-scan) creates package identity uncertainty; Invariant Explorer already shut down (Jan 2026); contributions closed | LOW | GitHub redirect, Snyk announcement |

### NO FINDINGS: 2 areas clear

| Area | Result |
|------|--------|
| CVE databases | No CVEs for mcp-scan or agent-scan |
| Prompt injection / tool poisoning in mcp-scan itself | No reports found |

## 7. Recommendations

1. **Maintain APPROVED status** -- No security findings warrant reclassification. The tool remains the most credible MCP scanner available.

2. **Enforce existing conditions** (from DECISIONS.md):
   - `--opt-out` flag MANDATORY (already enforced)
   - Scan-only mode (no proxy/intercept)
   - Monitor Snyk ownership transition

3. **Add new condition:** Monitor for PyPI package deprecation. If `mcp-scan` is discontinued in favor of `agent-scan`, evaluate the new package before switching.

4. **Add new condition:** If `--opt-out` flag stops working or behavior changes (ref: Issue #125 on `--local-only`), suspend usage until resolved.

5. **Do NOT add to trusted-publishers.txt** -- invariantlabs-ai/snyk does not meet our bar (reserved for anthropic, trailofbits). This is not a negative judgment; it means each update requires re-evaluation rather than auto-approval.

---

**Verdict: APPROVED (conditions unchanged, monitoring expanded)**

Previous conditions remain valid. No new security risks discovered. Community concerns are operational (API reliability, package transition) rather than security-critical. The Snyk acquisition is a net positive for long-term viability but introduces corporate governance uncertainty for the open-source version.
