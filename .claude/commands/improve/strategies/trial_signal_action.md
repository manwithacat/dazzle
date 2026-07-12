# Strategy: trial_signal_action

Drain **one** autonomous-actionable TR row from `## Lane: trials` in
`dev_docs/improve-backlog.md`. Product signal over capability re-stamps.

**Force path:** `/improve trial-signals`
**Driver rule:** Step 1 rule 6 in `improve.md`
**Eligibility:** driver table "Autonomous TR eligibility"

## Playbook (one TR per cycle)

### 1. Select

From trials backlog, filter autonomous-actionable rows. Priority:

1. `FIXED-VERIFY` (close the loop — re-trial)
2. `OPEN_FRAMEWORK` severity `high` with concrete evidence
3. `OPEN_DSL` severity `high` / `medium` with named app surface
4. `OPEN_FRAMEWORK` / `OPEN` severity `medium` with clear mechanism
5. Already filed `→ #N` where issue is still open and a local fix is feasible

Skip rows that fail eligibility (unknown mechanism, needs design intent, pure aesthetic).

Log: `trial_signal_action: TR-N ({status}, {severity}) → lane {lane}`.

### 2. Reproduce (mandatory before fix)

| Kind | Repro |
|------|--------|
| Framework / UI bug | Minimal curl/Playwright or `dazzle serve` + browser path from the TR evidence URL |
| Seed / trial harness | `dazzle qa trial --scenario … --fresh-db` with subscription driver (`grok-cli` / `claude-cli` / auto) |
| DSL / demo | `dazzle validate` + open the named surface |
| FIXED-VERIFY | Full scenario trial only — do not "fix" |

If unreproducible on current main: set status `RESOLVED-STALE` or `NEEDS_REINFORCE`, note cycle, stop (no code change).

### 3. Act

| Status | Action |
|--------|--------|
| `OPEN_FRAMEWORK` | Fix in framework if root cause is local and tests can pin it. Prefer smallest patch + unit/contract test. If already `#N` and still broken, continue the issue; if fix ships, close with comment. |
| `OPEN_DSL` | Edit the named example app DSL/blueprint/seed; `validate` + `lint` green. |
| `FIXED-VERIFY` | Re-run scenario; if pass → `VERIFIED` / archive-eligible; if fail → reopen `OPEN_FRAMEWORK` or `OPEN_DSL` with new evidence. |
| Cannot fix without design | Leave status; add note `needs-human: <one line>`; do **not** invent product policy. |

### 4. Verify

- Framework: targeted pytest or `ux verify --contracts` on the affected app when relevant
- DSL: validate + lint on the app
- Trial path: trial report exists and exit 0 for FIXED-VERIFY closes

### 5. Backlog + signals

1. Update the TR row (status, seen, cycle, notes with commit SHA)
2. Emit `trial-friction` only if a **new** high-severity open remains after this cycle
3. Emit `app-fixed` when an example app was corrected
4. Return `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit, budget_consumed: 0 or 1}`
   - `budget_consumed: 1` if a full `qa trial` ran; else `0` for pure code/DSL fixes

## Hard rules

- **One TR per cycle.**
- **No speculative architecture.** If the fix is "redesign signing authority model", stop and mark `needs-human`.
- **Subscription trial drivers only** for re-trials in the default loop (no metered key required).
- **Do not mass-close ancient OPEN_*** rows** without repro — many predate current substrate.
