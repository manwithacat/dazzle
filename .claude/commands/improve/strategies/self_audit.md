# Strategy: self_audit (driver-level)

Adversarial review of recent `improve:` commits against the claims their cycle
log entries and backlog transitions made. The driver otherwise **trusts lane
self-reports** — a lane can mark a row DONE, write a glowing log entry, and
nothing re-checks that the diff actually did what the entry says. This strategy
is the periodic counterweight.

Runs as its own cycle (`lane: self-audit` in the log). No backlog section of its
own — findings land in the *audited* lane's section. `budget_consumed: 0`
(verification, not exploration).

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
git log --oneline --grep '^improve: cycle' <last-audit-sha>..HEAD
```

### 2. Sample

- ≤5 improve-commits in window → audit all of them.
- More → audit the 5 with the largest diffstat (most substantive claims), plus
  any commit whose log entry moved a row to `DONE`/`VERIFIED`.

### 3. Adversarial review (one subagent per commit)

Dispatch a reviewer subagent per sampled commit — **no `model` override**
(judgment work inherits the session model per CLAUDE.md). Give it: the commit
diff, the matching `improve-log.md` cycle entry, and the backlog row(s) that
cycle touched (grep the archive too — the row may have been compacted since).
Its brief is to **refute**, not summarise:

1. **Claim ↔ diff**: does the diff actually do what the log entry says it did?
2. **Verification honesty**: if the entry claims tests ran / QA passed, do the
   named tests exist, and do they pass now?
3. **Transition justification**: was a row moved to `DONE`/`VERIFIED` without
   the lane's own QA step (e.g. framework-ux Phase A/B) having run?
4. **Scope honesty**: does the commit change files the log entry doesn't
   mention (undeclared drive-by edits)?

Verdict per commit: `CLEAN` | `DISCREPANCY` (with evidence: file:line, failing
command output, missing test).

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

- **Audit the claim, not the taste.** Style opinions about audited commits are
  out of scope; only claim/reality mismatches count.
- **Evidence or it didn't happen**: every DISCREPANCY needs a reproducible
  check (a command + its output), same bar the lanes are held to.
- **No fixing inline.** The audit files findings; the owning lane (or /issues)
  fixes them. One cycle = one job.
