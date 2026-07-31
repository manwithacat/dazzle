---
name: semgrep
description: >
  Diff-scoped Semgrep security scan (p/python, p/owasp-top-ten, p/security-audit)
  plus optional Sentinel modernisation rules and MCP scan path. Use when asked
  for Semgrep, SAST, security scan, nosemgrep triage, or /semgrep; also after
  substantial Python edits before ship when bandit alone is not enough.
---

# Semgrep (agent hygiene)

Three ways to exercise Semgrep in this monorepo. Prefer the **script** for
deterministic, reviewable output; use **MCP** when the Semgrep server is
connected; use **Sentinel** for the shipped modernisation ruleset.

## 1. Diff-scoped security packs (default)

```bash
# Working tree + staged (typical mid-edit)
python scripts/semgrep_diff.py

# Against main (PR / improve hygiene)
python scripts/semgrep_diff.py --base origin/main

# Full framework tree (slower)
python scripts/semgrep_diff.py --all-src --limit 80

# JSON for tooling
python scripts/semgrep_diff.py --base origin/main --json
```

Exit `1` = findings at/above `--min-severity` (default `warning`).
Exit `0` = clean or empty target set.
Exit `2` = tooling/config error.

**Do not** treat registry-pack noise as automatic ship blockers — this is
**agent hygiene**, not CI-hard (CI hard-fails **bandit** + **CodeQL**). Triage:

| Finding shape | Action |
|---------------|--------|
| True positive in code you touch | Fix + test; avoid `# nosemgrep` unless justified |
| Pre-existing outside your diff | Note; optional follow-up issue; do not drive-by suppress |
| False positive with safe pattern | Prefer code reshape; `# nosemgrep: rule.id` + one-line rationale only when reshape is worse |
| Secrets / supply-chain | Escalate; do not commit tokens |

## 2. Sentinel modernisation layer (product ruleset)

Shipped rules: `src/dazzle/sentinel/rules/python_audit.yml` (deprecated stdlib, etc.).

**Important scope split:**

| Path | What it scans |
|------|----------------|
| `python scripts/semgrep_diff.py --sentinel --all-src` | Framework `src/dazzle` (monorepo hygiene) |
| `dazzle sentinel scan -a PA` from an **example** | That app's `app/` + `scripts/` only — not the framework tree |

```bash
# Framework modernisation (preferred for monorepo improve hygiene)
python scripts/semgrep_diff.py --sentinel --all-src

# Product CLI on a consumer app (AgentId = PA)
cd examples/support_tickets
python -m dazzle sentinel scan -a PA -f json
python -m dazzle sentinel findings
```

MCP (Dazzle server): tool `sentinel` with `operation=scan` / `findings`.

Stamp improve capability **`dazzle sentinel scan`** when either path runs in a cycle.

## 3. Semgrep MCP (native)

When Grok has `[mcp_servers.semgrep]` (`semgrep mcp` stdio), discover tools via
`search_tool` / MCP list and call scan tools on paths of interest. Prefer the
same rule packs as the script when the server allows config selection.

If MCP is missing: still run `scripts/semgrep_diff.py` — CLI is the SSOT.

## When to run (habits)

| Context | Command |
|---------|---------|
| After editing `src/**/*.py` | `python scripts/semgrep_diff.py` |
| `/check` with `py_changed` | include semgrep_diff in the report |
| `/improve semgrep` | full hygiene playbook: `improve/strategies/semgrep_hygiene.md` |
| Pre-ship of auth/signing/SQL surfaces | `--paths` those dirs or `--all-src` |

## Report format

```
## Semgrep

| Layer | Status | Findings |
|-------|--------|----------|
| Diff packs (python/owasp/audit) | PASS/FAIL | N ≥ warning |
| Sentinel python_audit | PASS/FAIL/SKIP | N |
| MCP | USED/UNAVAILABLE | — |

Top findings: (rule, path:line, one-line message)
```
