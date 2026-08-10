# Strategy: Semgrep + Sentinel hygiene

**Force:** `/improve semgrep` or `/improve semgrep-hygiene`
**Class:** HYGIENE (security agent tooling)
**Budget:** `0` unless you also ship a true-positive fix (`1` then)

Re-exercises the Semgrep surfaces that Claude Code used more aggressively and
that Grok can run via CLI + MCP + product Sentinel. **Does not** replace CI
bandit or CodeQL DRIVER (Step 0c2).

## Preconditions

- `semgrep` on PATH (`semgrep --version`)
- Repo root; optional Dazzle MCP for `sentinel` tool

## Steps

### 1. Diff-scoped security packs

```bash
python scripts/semgrep_diff.py --base origin/main --limit 60
# if empty diff vs main (already pushed clean):
python scripts/semgrep_diff.py --all-src --limit 60
```

Capture summary JSON + top ERROR/WARNING rows.

### 2. Sentinel modernisation (product ruleset + PA agent)

```bash
# Framework tree (monorepo) — PA's rules file without app-only path filter
python scripts/semgrep_diff.py --sentinel --all-src --min-severity info --limit 40

# Example app (AgentId = PA; scans app/ + scripts/ only, not framework)
cd examples/support_tickets
python -m dazzle sentinel scan -a PA -f json
python -m dazzle sentinel findings -f table 2>/dev/null || true
```

Run **both** when time allows; at minimum the framework `--sentinel` pass so
`get_event_loop` / deprecated-stdlib debt in `src/dazzle` stays visible.

### 3. MCP probe (when available)

If Semgrep MCP is connected (`semgrep mcp` / config `[mcp_servers.semgrep]`),
invoke its scan tool on the same paths. If unavailable, log `mcp: unavailable`
and continue — CLI is authoritative.

### 4. Triage (this cycle)

| Priority | Action |
|----------|--------|
| ERROR/WARNING in **files this branch already touches** | Fix true positives; commit if clear |
| ERROR/WARNING only in unrelated legacy | Log top 5; **do not** mass-`# nosemgrep` |
| Sentinel-only modernisation hits | Prefer small modernisation fix if local; else log |
| Zero findings | Log clean; still stamp capabilities |

Do **not** claim a full product lane for registry-noise cleanup unless a finding
is a real exploitable bug with a tight fix.

### 5. Stamp + log

In `.claude/commands/improve/capability-map.md` set **last-exercised** for this cycle on:

- `dazzle sentinel scan` (HYGIENE)
- `/semgrep` / `scripts/semgrep_diff.py` (add row if missing; HYGIENE)
- Semgrep MCP if used

Log:

```
## Cycle N — YYYY-MM-DD — lane: framework-ux — outcome: HOUSEKEEPING
semgrep hygiene: packs=N findings, sentinel=M findings, mcp=used|unavailable
top: …
```

`budget_consumed: 0` for observe-only; `1` if you shipped a fix.

## Done when

- Both pack scan and sentinel scan ran (or explicit tooling error logged)
- Capability map stamped
- Any true-positive fix either shipped or filed with rule id + path
