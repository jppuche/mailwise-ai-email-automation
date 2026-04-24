# CERBERO -- Skill Evaluation Report (Dual)

**Date:** 2026-03-02
**Evaluator:** Sentinel (opus)
**Operation:** op-evaluate-skill.md (x2)
**Trigger:** UI/UX redesign skill installation request

---

## TOOL 1: Frontend Design Skill (Anthropic)

### CERBERO EVALUATION: frontend-design

```
CERBERO -- SKILL EVALUATION REPORT
====================================
File: SKILL.md
Author/Repo: anthropics/claude-code (plugins/frontend-design)
Size: 4,274 bytes
SHA-256: d39adf3a983de7dafc75991590d54f091755f7e4163d5a5ed085ecd719157184
Date: 2026-03-02

STEP 1 -- FILE TYPE: PASS (.md)

STEP 2 -- COMMUNITY INTELLIGENCE
  Findings: NONE
  Sources: No vulnerabilities or security concerns found for this skill.
  Notes: Published within official anthropics/claude-code repo (72.4K stars).
         Authors: Prithvi Rajasekaran and Alexander Bricken (Anthropic employees).
         Also available at claude.com/plugins/frontend-design (first-party distribution).

STEP 3 -- CONTENT ANALYSIS
  HTML comments: 0
  Base64 strings: 0
  Zero-width chars: 0
  Invisible patterns: 0
  Injection phrases: 0
  Suspicious code blocks: 0
  Semantic analysis: PERFORMED -- see below

  cerbero-scanner.py: SUSPICIOUS (2 MEDIUM)
    - Line 36: "NEVER use generic AI-generated aesthetics..." -- imperative "never"
    - Line 38: "NEVER converge on common choices..." -- imperative "never"

  Forensic verification: Both instances are legitimate design directives
  targeting Claude's output style (font selection, color palette). They instruct
  the model about aesthetic choices, NOT about ignoring instructions, overriding
  prompts, or exfiltrating data. The word "NEVER" is used in design guidance
  context (avoid Inter/Roboto), not as a prompt injection vector.

  Classification: FALSE POSITIVE (narrative-context imperatives, same pattern
  as alignment-chart evaluation from 2026-02-20).

  Additional semantic notes:
    - Line 42 references "Claude" by name: "Claude is capable of extraordinary
      creative work." This is normal for an Anthropic-authored skill that
      targets Claude specifically.
    - No model-targeting manipulation language detected.
    - No data acquisition instructions (no curl, wget, fetch, exec, eval).
    - No code blocks contain shell commands or system calls.
    - Scope is strictly design aesthetics guidance -- no filesystem, network,
      or permission requests.

STEP 4 -- AUTOMATED SCAN
  mcp-scan: SKIPPED (not invoked -- markdown-only skill, Tier 1+2 clean)

VERDICT: APPROVED
REASON: Anthropic first-party (trusted publisher), markdown-only, 4.2KB,
        zero executable content, scanner findings are false positives
        (design-context imperatives, not prompt injection).
```

### SUMMARY

Markdown-only design aesthetics skill (240+ styles, 127 font pairings, anti-"AI slop" guidelines) published as an official Anthropic plugin within the claude-code repository.

### PUBLISHER

| Attribute | Value |
|-----------|-------|
| Name | Anthropic (anthropics/claude-code) |
| Trust level | HIGHEST -- in `trusted-publishers.txt` |
| Authors | Prithvi Rajasekaran, Alexander Bricken (Anthropic employees) |
| Repository | 72.4K stars, MIT license, actively maintained |
| Distribution | Official plugin directory at claude.com/plugins/frontend-design |
| Track record | Same repo hosts Claude Code itself |

### CAPABILITIES

- Provides design methodology guidance (typography, color, motion, spatial composition)
- Instructs model to avoid generic aesthetics and make bold design choices
- No file system access
- No code execution
- No network access
- No permissions needed beyond reading the markdown file
- Scope: purely prompt-level aesthetic guidance

### RISK ASSESSMENT

| OWASP MCP | Risk | Notes |
|-----------|------|-------|
| MCP01 Token Mismanagement | N/A | No tokens/credentials involved |
| MCP02 Privilege Escalation | NONE | No permissions requested |
| MCP03 Tool Poisoning | NONE | No tool definitions, no schema manipulation |
| MCP04 Supply Chain | LOW | First-party Anthropic, pinned by SHA-256 |
| MCP05 Command Injection | NONE | No commands, no shell access |
| MCP06 Prompt Injection | NONE | Scanner imperatives are design directives, not injections |
| MCP07 Insufficient Auth | N/A | No auth mechanisms |
| MCP08 Lack of Telemetry | N/A | Skill file, not a server |
| MCP09 Shadow MCP | NONE | Does not reference or install MCP servers |
| MCP10 Context Over-Sharing | NONE | No data collection or exfiltration paths |

**Code execution risk:** NONE -- markdown only, no executable content.
**Data exfiltration risk:** NONE -- no network instructions, no data collection.
**Supply chain risk:** LOW -- Anthropic-authored, MIT, SHA-256 pinned.

### VERDICT: APPROVED (CLEAN)

### CONDITIONS

1. Pin to SHA-256 `d39adf3a983de7dafc75991590d54f091755f7e4163d5a5ed085ecd719157184` at install time.
2. Assign to `frontend-worker` agent.
3. Note: Skill explicitly discourages Inter font usage. mailwise frontend currently uses CSS variables with `[data-theme]`. If redesign adopts this skill's font recommendations, ensure the selected typefaces have adequate character coverage for any i18n requirements.
4. The skill's "NEVER use Inter" directive may conflict with Tailwind CSS v4 skill's `--font-family-sans: 'Inter'` example. Resolve by treating Tailwind config examples as templates to customize, not copy verbatim.

---

## TOOL 2: Tailwind CSS v4 Skill (blencorp)

### CERBERO EVALUATION: tailwindcss

```
CERBERO -- SKILL EVALUATION REPORT
====================================
File: SKILL.md
Author/Repo: blencorp/claude-code-kit (cli/kits/tailwindcss/skills/tailwindcss)
Size: 8,914 bytes
SHA-256: 233dadb5ad958d30a0fb8be6f6807ec04b1b7121eaaaeeaf09ec00b4d35a9ecf
Date: 2026-03-02

STEP 1 -- FILE TYPE: PASS (.md)

STEP 2 -- COMMUNITY INTELLIGENCE
  Findings: NONE
  Sources: No vulnerabilities or security concerns found for blencorp or
           claude-code-kit. No CVEs, no GitHub issues related to security.
  Notes: blencorp is a verified GitHub organization (BLEN Corp, Washington DC).
         49 repositories. 65 stars on claude-code-kit. MIT license.
         Also published: Lisa (111 stars), React Lighthouse Viewer (56 stars),
         healthcare.gov open source release.

STEP 3 -- CONTENT ANALYSIS
  HTML comments: 0
  Base64 strings: 0
  Zero-width chars: 0
  Invisible patterns: 0
  Injection phrases: 0
  Suspicious code blocks: 0
  Semantic analysis: PERFORMED -- see below

  cerbero-scanner.py: SUSPICIOUS (2 MEDIUM)
    - Line 155: "We'll never share your email." -- imperative "never"
    - Line 360: "Always consider mobile-first design" -- imperative "always"

  Forensic verification:
    - Line 155: This is INSIDE a TSX code block as placeholder UI text
      (`<p className="text-sm text-gray-500">We'll never share your email.</p>`).
      It is example component content, not an instruction to the model.
    - Line 360: This is a best practices bullet point about responsive design
      methodology. "Always consider mobile-first" is standard web development
      guidance, not a prompt manipulation directive.

  Classification: FALSE POSITIVE (both occurrences are in technical context --
  one is rendered UI text in a code example, the other is standard web dev
  best practice language).

  Additional semantic notes:
    - All code blocks contain standard TSX/CSS/JavaScript examples.
    - No references to Claude, system prompts, instructions, or context.
    - No shell commands beyond `npm install` for official Tailwind plugins.
    - `npm install` commands reference only official @tailwindcss/* packages.
    - No data acquisition instructions (no curl, wget, fetch, exec, eval).
    - References to external files (resources/utility-patterns.md, etc.)
      are relative links within the same kit -- not external URLs.
    - Scope is strictly Tailwind CSS utility patterns and configuration.

STEP 4 -- AUTOMATED SCAN
  mcp-scan: SKIPPED (not invoked -- markdown-only skill, Tier 1+2 clean)

VERDICT: APPROVED
REASON: Markdown-only, 8.9KB, zero executable content, scanner findings
        are false positives (UI text in code block + standard dev terminology).
        Publisher is verified organization with legitimate track record.
```

### SUMMARY

Markdown-only Tailwind CSS v4 development guidelines skill covering utility-first patterns, responsive design, dark mode, CSS-first `@theme` configuration, and component patterns. Published as part of a broader Claude Code kit collection.

### PUBLISHER

| Attribute | Value |
|-----------|-------|
| Name | BLEN Corp (blencorp) |
| Trust level | MEDIUM -- verified GitHub org, NOT in `trusted-publishers.txt` |
| Organization | Washington DC, verified domain (blencorp.com) |
| Repository | 65 stars, MIT license, 72 commits |
| Track record | 49 repos, healthcare.gov contributor, Lisa (111 stars) |
| Account type | Organization (not individual) |

### CAPABILITIES

- Provides Tailwind CSS v4 utility class reference and patterns
- Documents CSS-first `@theme` configuration approach
- Includes TSX code examples for common UI patterns (buttons, cards, forms)
- References official @tailwindcss/* plugins
- No file system access
- No code execution
- No network access
- No permissions needed beyond reading the markdown file
- Scope: purely CSS utility framework reference

### RISK ASSESSMENT

| OWASP MCP | Risk | Notes |
|-----------|------|-------|
| MCP01 Token Mismanagement | N/A | No tokens/credentials involved |
| MCP02 Privilege Escalation | NONE | No permissions requested |
| MCP03 Tool Poisoning | NONE | No tool definitions, no schema manipulation |
| MCP04 Supply Chain | LOW | Community publisher, but markdown-only limits blast radius |
| MCP05 Command Injection | NONE | `npm install` commands reference only official Tailwind plugins |
| MCP06 Prompt Injection | NONE | Scanner imperatives are code examples and dev best practices |
| MCP07 Insufficient Auth | N/A | No auth mechanisms |
| MCP08 Lack of Telemetry | N/A | Skill file, not a server |
| MCP09 Shadow MCP | NONE | Does not reference or install MCP servers |
| MCP10 Context Over-Sharing | NONE | No data collection or exfiltration paths |

**Code execution risk:** NONE -- markdown only, no executable content.
**Data exfiltration risk:** NONE -- no network instructions, no data collection.
**Supply chain risk:** LOW -- community publisher but markdown-only; content is standard Tailwind documentation. Rug pull risk is limited because the file is static text with no executable payload.

### VERDICT: APPROVED (CLEAN)

### CONDITIONS

1. Pin to SHA-256 `233dadb5ad958d30a0fb8be6f6807ec04b1b7121eaaaeeaf09ec00b4d35a9ecf` at install time.
2. Assign to `frontend-worker` agent.
3. **Do NOT add blencorp to `trusted-publishers.txt`** -- publisher trust is MEDIUM; approval is for this specific file at this specific hash.
4. The `--font-family-sans: 'Inter'` example in the configuration section is a template. Per the frontend-design skill's guidance, replace with a distinctive typeface during the mailwise redesign.
5. The skill references `resources/utility-patterns.md`, `resources/component-library.md`, and `resources/configuration.md` -- these companion files were NOT evaluated. If installed as part of the full kit, each additional file requires separate Cerbero evaluation before use.
6. mailwise uses React + Vite (not Next.js). The skill's examples use TSX which is compatible. No framework conflicts.
7. Re-verify SHA-256 hash if updating the skill in the future (rug pull detection).

---

## CROSS-SKILL COMPATIBILITY ANALYSIS

| Dimension | frontend-design | tailwindcss | Conflict? |
|-----------|----------------|-------------|-----------|
| Font guidance | "NEVER use Inter/Roboto" | `--font-family-sans: 'Inter'` example | MINOR -- Tailwind example is a template, not a mandate. Resolve by customizing `@theme` |
| Color approach | "CSS variables for consistency" | `@theme` CSS custom properties | COMPATIBLE -- both use CSS variables |
| Dark mode | "Vary between light and dark" | `dark:` variant classes documented | COMPATIBLE |
| Framework | Framework-agnostic (HTML/CSS/React/Vue) | TSX examples (React-compatible) | COMPATIBLE with mailwise React stack |
| Scope overlap | Design philosophy + aesthetics | Implementation patterns + utilities | COMPLEMENTARY -- minimal overlap |

**mailwise-specific notes:**
- Current frontend uses CSS variables with `[data-theme="dark"]` (B15-B17 pattern). Both skills are compatible with this approach.
- recharts components must continue using hex values for colors (known limitation from B16). Neither skill conflicts with this constraint.
- Both skills are prompt-only with no executable code, so they cannot interfere with security hooks or the Cerbero scanner.

---

## SUMMARY TABLE

| Skill | Publisher | Trust | Size | Scanner | Content Analysis | Verdict | SHA-256 |
|-------|-----------|-------|------|---------|-----------------|---------|---------|
| frontend-design | Anthropic | HIGHEST | 4,274 B | 2 MEDIUM (FP) | CLEAN | **APPROVED** | `d39adf3a...9157184` |
| tailwindcss | blencorp | MEDIUM | 8,914 B | 2 MEDIUM (FP) | CLEAN | **APPROVED** | `233dadb5...d35a9ecf` |

Both skills approved for installation. Neither contains executable code, prompt injection vectors, hidden content, zero-width characters, encoded payloads, or data acquisition instructions.
