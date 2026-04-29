# Strategy: api_surface_audit

**Lane:** framework-ux

The 1.0-prep walkthrough as a recurring exercise (closes the loop on #961 cycle 6). Each invocation: pick one of the five committed API-surface baselines, walk a chunk of un-audited entries, ask "is this what we'd design today?", file proposals for any "no". This is qualitative review work — the drift gate (`tests/unit/test_api_surface_drift.py`) already catches accidental change; this strategy hunts for *intentional* change that's overdue.

## Surfaces

| Baseline | Source | Entries |
|----------|--------|---------|
| `docs/api-surface/dsl-constructs.txt` | parser dispatch + ModuleFragment | ~51 constructs |
| `docs/api-surface/ir-types.txt` | dazzle.core.ir.__all__ | ~485 types |
| `docs/api-surface/mcp-tools.txt` | get_all_consolidated_tools() | ~32 tools |
| `docs/api-surface/public-helpers.txt` | top-level __init__ exports | ~17 helpers |
| `docs/api-surface/runtime-urls.txt` | AST walk of *_routes.py | ~45 routes |

## State

- **Audit log:** `dev_docs/api-surface-audit-log.md` — append-only one-line-per-cycle ledger:
  `## Cycle N — YYYY-MM-DD — surface: <name> — entries: <count> — proposals: <count>`
- **Per-entry audit timestamps:** *not* tracked — the audit log is the cycle-grain ledger; per-entry would create stale-state churn faster than it'd add value.
- **Backlog rows:** filed under `## Lane: framework-ux` in `improve-backlog.md` with prefix `API-NNN` (next free number, do not collide with existing PROP/EX prefixes).

## When to pick

Pick this strategy when:
- Last `api_surface_audit` cycle was ≥7 cycles ago
- A `dazzle-updated` signal fired since last audit (new release shipped — surfaces may have grown)
- No fresher candidate sub-strategy is biased by signals

Skip if:
- Backlog already has ≥3 OPEN `API-NNN` rows that haven't been resolved (consolidate before adding more)
- Approaching 1.0 release freeze (then this becomes a *daily* exercise, not opportunistic)

## Playbook

### 1. Read the audit log

```bash
ls -la dev_docs/api-surface-audit-log.md 2>/dev/null
tail -10 dev_docs/api-surface-audit-log.md 2>/dev/null
```

If the file doesn't exist: this is the first audit cycle. Pick `dsl-constructs` (smallest surface, gives momentum).

If it does: pick the surface with the oldest last-audit cycle. Tie-break by surface size (smaller first — more chance of completing in one cycle).

### 2. Verify drift gate is green

```bash
pytest tests/unit/test_api_surface_drift.py -q
```

If red: this strategy cannot run. Mark `BLOCKED` and return — fix the drift first via `dazzle inspect-api <surface> --write` and a CHANGELOG entry, then come back.

### 3. Read the chosen baseline

```bash
cat docs/api-surface/<surface>.txt
```

The baseline IS the source of truth for what to audit. Do **not** re-derive from code; the baseline is what's pinned.

### 4. Walk a chunk

For each entry (construct, IR type, MCP tool, helper, or route), ask:

| Question | If "no" → file because |
|----------|------------------------|
| **Naming**: would we still pick this name today? | Renaming is cheap pre-1.0, expensive after |
| **Required vs optional**: is the required-set right? Are we forcing fields users don't have? | Required-field changes are breaking |
| **Type choice**: is `str` where it should be an enum? `dict` where a typed model would prevent bugs? | Type tightening is breaking |
| **Default**: is the default the *right* answer for the median user? | Default changes are breaking |
| **Granularity**: should two constructs be one (or one be two)? | Construct merges/splits are breaking |
| **Removal**: is this still earning its keep? | Removing in 2.0 is more painful than removing now |

How big is "a chunk"? Aim for 15-30 minutes of audit — typically 10-20 entries on a small surface, 5-10 on a complex one (e.g. EntitySpec with 20+ fields counts as one entry but takes longer than ten enums).

### 5. File proposals

For each "no": add a row to `improve-backlog.md` under `## Lane: framework-ux`:

```
| API-NNN | <surface>: <entry-name> — <one-line proposal> | PENDING | <today> | qa: N/A | contract: N/A |
```

The `notes` column should reference the specific line in the baseline file (so reviewers can see the exact current state) and the proposed change.

If the proposal is large enough to need its own GitHub issue (cross-cutting, requires user input), file the issue directly via `gh issue create` — don't load up the backlog with multi-paragraph entries.

### 6. Append to the audit log

```
## Cycle N — YYYY-MM-DD — surface: <name> — entries: <count> — proposals: <count>
- <surface>:<entry> → API-NNN
- <surface>:<entry> → API-NNN
```

Even when zero proposals fire (most cycles, hopefully): record the surface + entry count audited so the next cycle's surface-pick rotation works.

### 7. Return outcome

```
{
  status: "EXPLORED",
  summary: "audited <count> entries on <surface>; filed <N> proposals",
  signals_to_emit: [
    # if any proposals filed:
    {kind: "ux-gap-analysis", payload: {cycle: N, surface, proposals_count}}
  ],
  budget_consumed: 1
}
```

Counts against the shared explore budget — cap 100, same as other framework-ux explore sub-strategies.

## Hard rules

- **Audit one surface per cycle.** Don't try to walk all five — the value is in qualitative depth, not coverage.
- **Drift gate must be green at start.** A red gate means there's *unintentional* drift to resolve before *intentional* review makes sense.
- **Proposals are pre-1.0 only.** After 1.0 release, this strategy is repurposed: audit becomes diff-against-last-baseline rather than walk-current-baseline. The 1.0 commit freezes the surface; ongoing changes route through ADR + CHANGELOG.
- **Don't chase ghosts.** If you're tempted to file "we should consider whether..." — that's a research task, not a backlog row. Either commit to filing a concrete proposal (with the rename/removal/change spelled out) or drop it.

## See also

- `dev_docs/improve-backlog.md` — `## Lane: framework-ux` is where API-NNN rows land
- `dev_docs/api-surface-audit-log.md` — append-only ledger of audit cycles
- `docs/api-surface/*.txt` — the five committed baselines
- Issue [#961](https://github.com/manwithacat/dazzle/issues/961) — the breaking-change pass tooling that enables this strategy
