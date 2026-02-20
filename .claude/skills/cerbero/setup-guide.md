# Cerbero — Phase A: Setup Guide (Human Only)

This document is for human configuration. Do not load in agent context.

## Prerequisites

- Node.js 18+
- Python 3.10+
- uv: https://docs.astral.sh/uv/ (for uvx commands)
- Claude Code updated to latest stable (`/status` to check)

## A.1 — Install Primary Security Tooling

### mcp-scan (Invariant Labs / Snyk)

The most established MCP security scanner (~1.1K stars). Scans tool descriptions against prompt injection, tool poisoning, rug pulls, and cross-origin escalation.

```powershell
# Verify it runs (no global install needed, uvx runs it on demand)
uvx mcp-scan@latest scan --help
```

> **PRIVACY NOTE:** By default, mcp-scan sends tool names and descriptions to Invariant Labs/Snyk API for analysis. Options:
> - `--opt-out` — Disable telemetry (recommended default)
> - `--local-only` — Fully local analysis (requires `OPENAI_API_KEY`, less precise results)
>
> **NOTE:** Invariant Labs was acquired by Snyk (Jan 2026). The mcp-scan repo remains active but monitor its continuity.

### Optional: Lasso Prompt Injection Defender

PostToolUse hook that scans tool outputs against 50+ detection patterns before Claude processes results. Injects warnings into context instead of blocking (avoids false positives).

> **STATUS:** Low community adoption (~30 stars). Legitimate company (Lasso Security) with solid technical blog on indirect prompt injection. **Audit the code before installing** — this is exactly what Cerbero would recommend for any hook.

```powershell
git clone https://github.com/lasso-security/claude-hooks.git
Set-Location claude-hooks
# Review code before running install
# Follow install instructions for your project
```

## A.1b — Alternative / Complementary Tools

These tools can complement or replace mcp-scan depending on your needs:

| Tool | Author | Strength | Install |
|------|--------|----------|---------|
| **Proximity** | Thomas Roccia | NOVA rule engine for prompt injection/jailbreak detection. Open-source. Covered by Help Net Security. | `github.com/fr0gger/proximity` |
| **MCPGuard** | Virtue AI | Scanned 700+ MCP servers. First MCP Security Leaderboard. 45 vulnerabilities responsibly disclosed. | `virtueai.com` |
| **Cisco MCP Scanner** | Cisco | AST + dataflow analysis. Offline mode for CI/CD. Custom YARA rules. | `github.com/cisco-ai-defense/mcp-scanner` |
| **MCPShield** | — | Typosquat detection, SHA-512 hashing, namespace validation, zero-config. | `mcpshield.vercel.app` |

### Anthropic Sandbox Runtime (beta)

OS-level sandboxing for Claude Code. Restricts filesystem and network access per session.

```powershell
claude --sandbox
```

> Recommended for first session with any HIGH-risk MCP server.

## A.2 — Install Cerbero Skill

Copy the `cerbero/` directory to your preferred skills location:

**Personal (all projects):**
```powershell
Copy-Item -Recurse cerbero/ ~/.claude/skills/cerbero/
```

**Per-project:**
```powershell
Copy-Item -Recurse cerbero/ .claude/skills/cerbero/
```

Then create the runtime security directory:
```powershell
New-Item -ItemType Directory -Force .claude/security
```

Copy the default trusted publishers list to the project:
```powershell
Copy-Item ~/.claude/skills/cerbero/trusted-publishers.txt .claude/security/trusted-publishers.txt
```

## A.3 — Define Permission Policy

File: `.claude/settings.local.json`

```jsonc
{
  "enabledMcpjsonServers": [],
  "disabledMcpjsonServers": ["filesystem"],

  "permissions": {
    "allow": [
      "Bash(pwd)",
      "Bash(echo:*)",
      "Bash(cat:*)",
      "Bash(ls:*)"
    ],
    "ask": [
      "Bash(git push:*)",
      "Bash(npm run:*)",
      "Bash(docker run:*)"
    ],
    "deny": [
      "Bash(curl:*)",
      "Bash(wget:*)",
      "Bash(rm -rf:*)",
      "Read(./.env)",
      "Read(./secrets/**)",
      "Read(~/.ssh/**)",
      "WebFetch"
    ]
  }
}
```

Add each MCP server to `enabledMcpjsonServers` only after it passes Cerbero evaluation.

## A.4 — Configure Security Hooks

Add to `.claude/settings.local.json`:

```jsonc
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/validate-prompt.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/pre-tool-security.py"
          }
        ]
      },
      {
        "matcher": "^mcp__",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/mcp-audit.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/prompt-injection-defender/post-tool-defender.py"
          }
        ]
      }
    ]
  }
}
```

> **NOTE:** The PostToolUse hook for Lasso Defender is optional. If not installed, remove or comment out that section. Hook exit codes: 0 = allow, 1 = error, 2 = block operation.

## A.4b — Install Cerbero Hook Scripts

Copy the hook templates from the skill directory to your project:

**If skill is personal (~/.claude/skills/cerbero/):**
```powershell
New-Item -ItemType Directory -Force .claude/hooks
Copy-Item ~/.claude/skills/cerbero/hooks/validate-prompt.py .claude/hooks/
Copy-Item ~/.claude/skills/cerbero/hooks/pre-tool-security.py .claude/hooks/
Copy-Item ~/.claude/skills/cerbero/hooks/mcp-audit.py .claude/hooks/
```

**If skill is per-project (.claude/skills/cerbero/):**
```powershell
New-Item -ItemType Directory -Force .claude/hooks
Copy-Item .claude/skills/cerbero/hooks/validate-prompt.py .claude/hooks/
Copy-Item .claude/skills/cerbero/hooks/pre-tool-security.py .claude/hooks/
Copy-Item .claude/skills/cerbero/hooks/mcp-audit.py .claude/hooks/
```

Verify they run correctly:

```powershell
echo '{"prompt":"test"}' | python .claude/hooks/validate-prompt.py
echo '{"tool_input":{"command":"echo hello"}}' | python .claude/hooks/pre-tool-security.py
```

> **NOTE:** Hook scripts run with your user permissions, not the agent's. They are lightweight (~30-40 lines each) and auditable. Review them before installing.

## A.5 — Trusted Publishers List

### Default list

If you didn't copy the default in A.2, create `.claude/security/trusted-publishers.txt`:

```
anthropic
trailofbits
```

### Inclusion criteria

The trusted publishers list is intentionally minimal. A publisher on this list allows Cerbero to auto-approve their MCP servers/skills when all other checks pass. Every other publisher requires human review regardless of scan results.

**Requirements for inclusion (all three must be met):**

1. **Direct relevance to Claude Code security or runtime** — The publisher creates Claude Code itself or provides security tooling that Cerbero depends on.
2. **Established security track record** — Public security audits, responsible disclosure history, recognized by OWASP/CVE/industry bodies.
3. **No commercial conflict of interest** — Being a large or popular company is not sufficient. Trust is not reputation.

**Current entries and rationale:**

| Publisher | Rationale |
|-----------|-----------|
| `anthropic` | Creator of Claude and Claude Code. Runtime platform provider. |
| `trailofbits` | Security audit firm. Recognized by industry (DARPA, Ethereum Foundation, major tech companies). Authors of security research directly relevant to LLM tooling. |

### Adding a new publisher

1. Evaluate the MCP server/skill with Cerbero first (`/cerbero evaluate-mcp <pkg>`).
2. If APPROVED after full evaluation, verify the publisher meets **all three** criteria above.
3. Add to `.claude/security/trusted-publishers.txt` (one name per line).
4. Document the rationale in your project's `docs/DECISIONS.md`.

All other publishers (including vercel, microsoft, supabase, etc.) are evaluated case-by-case with Cerbero. Being a well-known company does not exempt from evaluation.

## A.6 — Generate Initial Baseline

```powershell
claude mcp list --json | Out-File -Encoding utf8 .claude/security/mcp-inventory.json
(Get-FileHash .claude/security/mcp-inventory.json -Algorithm SHA256).Hash | Out-File .claude/security/mcp-baseline.sha256
(Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") | Out-File .claude/security/baseline-date.txt
```

## A.7 — Add Cerbero Reference to CLAUDE.md

Add to your project's `CLAUDE.md`:

```markdown
## Security

Before installing any MCP server or Skill, execute Cerbero evaluation.

## Skills

- Cerbero -- Before installing any MCP server or Skill. Security audits.
```

## A.8 — Verification Checklist

- [ ] `uv` installed (for `uvx` commands)
- [ ] `mcp-scan` accessible via `uvx mcp-scan@latest scan --help`
- [ ] Cerbero skill installed (`~/.claude/skills/cerbero/` or `.claude/skills/cerbero/`)
- [ ] `.claude/security/` directory created
- [ ] `.claude/security/trusted-publishers.txt` exists
- [ ] Cerbero hook scripts installed in `.claude/hooks/` (A.4b)
- [ ] Baseline files generated (if MCPs already installed)
- [ ] `.claude/settings.local.json` has permissions and hooks
- [ ] `CLAUDE.md` references Cerbero
- [ ] Claude Code is latest stable version
- [ ] (Optional) Lasso Defender PostToolUse hook installed and code audited
- [ ] (Optional) Proximity, Cisco Scanner, or sandbox-runtime for additional coverage
