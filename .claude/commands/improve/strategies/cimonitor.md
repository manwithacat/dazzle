# Strategy: cimonitor (driver-level CI badge gate)

Keeps the README CI badge on `main` from rotting while `/improve` runs on a
cadence (e.g. `/loop 6m /improve`). Local preflight (Step 0b) only proves a
slice of the tree; the badge is the fleet-visible truth.

**Driver step:** Step 0c in `improve.md`
**Skill body:** `.agents/skills/cimonitor/SKILL.md` (full diagnose/fix/push loop)
**Force path:** `/improve cimonitor`

`budget_consumed: 0` — operations / verification, not exploration.

## Snapshot (always — cheap)

```bash
gh run list --workflow ci.yml --branch main --limit 1 \
  --json status,conclusion,databaseId,url,displayTitle,updatedAt
```

Optional second glance (branch tip, not the badge):

```bash
gh run list --branch "$(git branch --show-current)" --limit 3 \
  --json status,conclusion,name,url,databaseId,workflowName
```

Do **not** enter the cimonitor long poll loop (15s × 20) inside a normal
improve cycle when status is `in_progress` / `queued` — log and continue. The
next scheduled `/improve` will re-snapshot. Only poll when this cycle is
already in **repair mode** after a push, and then cap polls so the lock TTL
(15 min) is not exceeded.

## Decision table

| Latest `main` + `ci.yml` | Mode | Next |
|--------------------------|------|------|
| `completed` + `success` | observe | Log `ci: green (run <id>)`; return to driver for Step 0d+ |
| `completed` + `failure` / badge-red terminal state | **repair** | Full cimonitor skill; this cycle ends after log/mark_run/unlock |
| `in_progress` / `queued` | observe | Log `ci: in_progress (run <id> url)`; continue driver |
| `gh` error / empty | observe | Log `ci: unavailable (<error>)`; continue driver |

## Repair mode (red badge)

1. **Job table** — `gh run view <id> --json jobs` → name / conclusion / duration.
2. **Failed logs** — `gh run view <id> --log-failed` (tail enough to see root assert/mypy/ruff).
3. **Local mirror first** — map log signature → command from cimonitor skill table
   (`make ship-surface`, `make preflight-surface`, targeted pytest). Reproduce
   locally before wide edits.
4. **Categorize + fix** — mypy, ruff, pytest, bandit, flaky/infra. Fix **all**
   errors including pre-existing; goal is green badge, not "only my commit."
5. **Close the loop (mandatory)** — if Tier 0 / ship-surface would **not** have
   caught this class, promote it into `scripts/ship_surface.py` or
   `scripts/preflight_surface.py` (and `scripts/ci_changed.py` if path-specific)
   in the same or immediately following commit. Log
   `ci_gap: <class> | promoted to ship-surface|preflight|n/a`.
6. **Commit** — product fix: conventional message (`fix: …` / `test: …`). Prefer one focused commit; if pre-existing debt is unrelated, a separate `fix: resolve pre-existing …` commit is fine.
7. **Push** — `git push` to the branch that feeds `main` CI (usually `main` on this repo). Confirm with the user only if push is blocked or the branch is protected in a way that needs a PR (default: push when the improve session already has push authority on main).
8. **Re-check** — snapshot again (or short poll). If still red and time remains under lock TTL, continue diagnosis; else log partial progress and leave the next cycle to resume.
9. **Log** — append improve-log as `lane: cimonitor`:

```
## Cycle N — YYYY-MM-DD — lane: cimonitor — outcome: PASS|FAIL|BLOCKED

- **preflight:** PASS
- **ci:** red → repair (run <id> <url>)
- **jobs failed:** …
- **root cause:** …
- **local_mirror:** make ship-surface | make preflight-surface | …
- **ci_gap / promote:** n/a (already covered) | promoted to ship-surface | TODO
- **fix:** … (commits …)
- **badge after:** green | still red | in_progress
- **budget_consumed:** 0 → explore budget **X/100**
- **next:** re-check CI if still red; else normal lane pick
```

Outcomes:
- `PASS` — badge green after this cycle's fix (or confirmed already fixed by a concurrent push) **and** gate gap closed or marked n/a.
- `FAIL` — still red after a honest fix attempt (or fix merged but CI still failing for a new reason).
- `BLOCKED` — cannot act (no `gh` auth, push rejected, needs human secrets/infra).

## Observe mode (green / in-progress / unavailable)

Do not open a full cimonitor investigation. One line in the eventual cycle log is enough:

```
- **ci:** green (run 123456) | in_progress (run 123456) | unavailable (gh: …)
```

## Hard rules

- **Red badge owns the cycle.** No TR drain, capability stamp, or explore after repair starts.
- **Fix-only is incomplete.** Promote new recurrent classes into `ship-surface` /
  `preflight-surface` so the next Tier 0 ship catches them without a full matrix.
- **No silent skip.** Every cycle must record a ci: line (or a full cimonitor log entry).
- **Don't burn explore budget** on CI repair.
- **Flaky/infra** — if the only failure is timeouts/runners, prefer `gh run rerun <id> --failed` once, log it, and leave product code alone unless rerun stays red with a real assert.
- **Lanes do not re-implement this.** Product lanes assume Step 0c already ran; they may still run local tests for their own changes.
