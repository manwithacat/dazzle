# Strategy: self_audit (driver-level)

Adversarial review of recent `improve:` commits against the claims their cycle
log entries and backlog transitions made. The driver otherwise **trusts lane
self-reports** — a lane can mark a row DONE, write a glowing log entry, and
nothing re-checks that the diff actually did what the entry says. This strategy
is the periodic counterweight.

Runs as its own cycle (`lane: self-audit` in the log). No backlog section of its
own — findings land in the *audited* lane's section. `budget_consumed: 0`
(verification, not exploration).

## Grok workflow (preferred multi-agent path)

When the host is Grok Build with workflows enabled, **prefer** the project
workflow over hand-rolled subagent fan-out:

```text
/workflow improve-self-audit
/workflow improve-self-audit {"apply":true}   # also write AUD/REGRESSION + log
```

| Path | Role |
|------|------|
| `.grok/workflows/improve-self-audit.rhai` | Sample window → parallel read-only skeptics (≤5) → fail-closed report |
| This playbook §4–5 | Driver apply if `apply` was false; always release lock + self-schedule |

Workflow hard-codes the shared-tree mutation ban (cycle 231 lesson). Result
includes `status` (`PASS`/`FAIL`), `verdicts`, `apply_hints`, `path` (scratch
markdown). Fall back to the numbered playbook below on hosts without workflows.

## Cadence (driver rule — Step 1)

Run when **≥15 cycles** have elapsed since the last `lane: self-audit` log entry
(or none exists). `REGRESSION` rows still preempt — shipped-broken beats
bookkeeping. Can be forced with `/improve self-audit`.

## Playbook

### 1. Window

Find the last self-audit log entry and the commit range it covered (each audit
records its end SHA). Audit window = that SHA (exclusive) → `HEAD`. If no prior
audit, window = the last 15 `improve:` commits.

```bash
# Window = last self-audit end SHA (exclusive) → HEAD
git log --oneline <last-audit-sha>..HEAD

# Improve-relevant commits (conventional subjects + legacy prefix):
#   - subject contains "cycle N" (primary 2026-08 tip: `fix: cycle 2126 …`)
#   - subject contains "(cycle N)" / "(cycle NNNN)" (older `feat/fix … (cycle 1889)`)
#   - subject matches '^improve:'                      ← legacy
#   - or the SHA is named in an improve-log Cycle entry inside the window
# Do NOT require '^improve: cycle' or only parenthesized `(cycle N)` — both
# miss `fix: cycle N` tips and falsely short-circuit the workflow (AUD-011/017).
git log --oneline --grep 'cycle [0-9]' <last-audit-sha>..HEAD
git log --oneline --grep '^improve:' <last-audit-sha>..HEAD
```

### 2. Sample

- ≤5 improve-commits in window → audit all of them.
- More → audit the 5 with the largest diffstat (most substantive claims), plus
  any commit whose log entry moved a row to `DONE`/`VERIFIED`.

### 3. Adversarial review (one subagent per commit)

Dispatch a reviewer subagent per sampled commit — judgment work runs at the
session tier (model-tiering). Give it: the commit
diff, the matching `improve-log.md` cycle entry, and the backlog row(s) that
cycle touched (grep the archive too — the row may have been compacted since).
Its brief is to **refute**, not summarise:

1. **Claim ↔ diff**: does the diff actually do what the log entry says it did?
2. **Verification honesty**: if the entry claims tests ran / QA passed, do the
   named tests exist, and do they pass now?
3. **Transition justification**: was a row moved to `DONE`/`VERIFIED` without
   the lane's own QA step (e.g. framework-ux Phase A/B) having run?
4. **Scope honesty**: does the commit change files the log entry doesn't
   mention, or omit files it claims?
5. **Oral handbook**: if the cycle added an oral, does it name the hole
   and point at Standing refusals — or reprint the ancestor *not leftover
   … / not Goal B coat* litany? The litany is apprentice instruction
   (`improve/oral-history.md`); recopying it every cycle is the finding
   (AUD), not the existence of a refusal list.
6. **No bump/tag**: improve commits must not have cut a `v*` tag or
   run `/bump`. Those are human-initiated release moves.

Verdict per commit: `CLEAN` | `DISCREPANCY` (with evidence: file:line, failing
command output, missing test).

### 3b. Dig contract check (story_walk / agent_acceptance)

When a sampled cycle log says `lane: example-apps` with strategy `story_walk`
or `agent_acceptance_panel` (or `force=example-apps story_walk` / acceptance):

1. Grep the cycle entry for `contract:` lines (`stories=`, `maps_cited=`,
   `walk_validate=` / `trial_ran=` / `live_run=`).
2. Prefer a dig receipt under `.dazzle/improve-digs/` matching app+strategy
   (`python scripts/improve_dig_receipt.py check --app … --strategy …`).
3. **DISCREPANCY** if the log claims PASS / residual reduced for that strategy
   but contract lines are missing **and** no receipt with `outcome=PASS` and
   `contract_ok`.
4. **DISCREPANCY** if receipt exists with `outcome=contract_incomplete` but the
   log claimed a clean PASS.

This enforces dig contracts without re-judging UX taste (design
`2026-07-21-improve-dig-contracts-and-process-sensors-design.md`).

### 4. Apply findings

- **Shipped-broken** (claimed fix doesn't work / test fails) → mark the affected
  backlog row `REGRESSION` in its lane section; the driver's rule 1 picks it up
  next cycle.
- **Bookkeeping discrepancy** (over-claimed QA, undeclared scope, wrong status)
  → add an `AUD-NNN` row to the affected lane's section: `| AUD-NNN | <commit>
  | <claim> | <what was actually true> | OPEN |`, for the lane to resolve.
- **Systemic pattern** (a lane repeatedly over-claims) → note it in the cycle
  log entry and consider a `framework_gap_analysis`-style write-up; the fix is
  usually a missing machine gate in that lane's playbook.

### 5. Report

Log entry must include: window (SHAs), commits sampled, verdicts, rows marked,
and the end SHA (the next audit's window start). Outcome to driver:
`{status: PASS|FAIL, summary, signals_to_emit: [], budget_consumed: 0}` —
FAIL means at least one DISCREPANCY was found (the cycle itself still completed).

## Hard rules

- **Promote durable lore.** If the window reveals a rule agents re-learn every
  week (depth waves, panel thrash, CI hold etiquette), add **one bullet** to
  `improve/oral-history.md` in the same audit ship — do not leave it only in a
  capability-map stamp.
- **Audit the claim, not the taste.** Style opinions about audited commits are
  out of scope; only claim/reality mismatches count.
- **Evidence or it didn't happen**: every DISCREPANCY needs a reproducible
  check (a command + its output), same bar the lanes are held to.
- **No fixing inline.** The audit files findings; the owning lane (or /issues)
  fixes them. One cycle = one job.
- **Reviewer subagents must NEVER mutate the shared worktree.** (Learned the hard
  way, cycle 231: a reviewer ran `git stash pop` to "get a clean tree at the target
  commit" and accidentally popped an ancient WIP stash onto HEAD — 55 conflicts,
  ~14k lines, a corrupted tree recovered only by `git reset --hard HEAD`.) The
  subagents run in the SAME working directory as the driver and each other; any
  `git stash`/`git checkout <ref>`/`git reset`/`git merge`/`git stash pop`/`git
  cherry-pick` there corrupts every concurrent reviewer AND the driver. Verify
  **against the current tree in place**: `git show <sha>` for the diff, `git log`/
  `git diff <sha>..HEAD` for history, run tests/greps on the working tree AS-IS
  (the audit asks whether the claim holds NOW — the current tree answers that). If
  an at-commit checkout is truly required, use an ISOLATED `git worktree add
  /tmp/audit-<sha> <sha>` and remove it after — never `checkout`/`stash` in the
  shared tree. The subagent brief must state this explicitly, and the driver must
  verify `git status` is clean after the fan-out returns, recovering with `git
  reset --hard HEAD` if not (HEAD is safe — all audited work is committed).
