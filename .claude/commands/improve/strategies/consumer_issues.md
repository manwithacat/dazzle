# Strategy: consumer_issues (driver-level)

**Force:** `/improve consumer-issues` or `/improve consumer_issues`
**Probe:** `uv run python scripts/improve_github_inbox.py`
**Budget:** `0` when triage-only; `1` if a fix is implemented this cycle.

Poll GitHub for **incoming bugs from downstream Dazzle consumers** (external
authors + bug-shaped issues) and act. Complements standalone `/issues` — this
strategy is the improve-loop's **inbox intake** so consumer pain is not starved
by explore STALE-clear.

## When the driver picks this

Step 0c3 / selection rule **consumer-bugs**: inbox `heat` is `consumer_bug`, or
`recommended[0].kind == "consumer_issue"` with `bug_shaped: true`.

Also forceable when the operator wants an intake-only cycle.

## Classification (from the probe)

| Class | Who | Shape | Improve action |
|-------|-----|-------|----------------|
| `consumer_bug` | author ≠ owner **or** consumer label | bug-shaped title/labels | **Autonomous fix** if clear (Tier 1); else investigate + comment + leave open |
| `consumer_other` | external author | not clearly a bug | Comment with analysis; do **not** implement features without human fork |
| `owner_bug` | owner (`manwithacat`) | bug-shaped | Prefer `/issues` routing or implement if small + clear (same Tier 1 rules) |
| `deferred_future` | any | `future` label, not a bug | Skip (log only) |

**Bug-shaped:** labels ∈ {bug, regression, crash, security, blocker, …} **or**
title matches `bug|crash|fail|broken|error|exception|regress|traceback|…`.

**Consumer author:** login ≠ project owner and not Dependabot.

## Playbook (one cycle → one primary issue)

### 1. Probe

```bash
uv run python scripts/improve_github_inbox.py
# JSON also at .dazzle/improve-github-inbox.json
```

Pick `primary` when `kind == "consumer_issue"`, else first `consumer_issues[]`
with `bug_shaped: true`.

### 2. Load issue

```bash
gh issue view <N> --repo manwithacat/dazzle
gh issue view <N> --repo manwithacat/dazzle --comments
```

Skip if already fixed: `git log --oneline --all --grep="#N"` — then comment + close.

### 3. Classify intervention tier (same bar as `/issues auto`)

| Tier | Action this cycle |
|------|-------------------|
| **1 — Autonomous** | Clear root cause, reversible, no public-claim fork → implement + tests + ship + close |
| **2 — Design** | Bounded options → comment options; leave open (do not block improve forever) |
| **3 — Brainstorm** | Comment analysis + leave open |

**Bias Tier 1** for consumer bugs with a concrete stack/error path.

### 4. Implement (Tier 1 only)

- Hold `.dazzle/improve.lock` (already held by driver).
- Fix root cause + regression test when possible.
- Commit: `fix(#N): …` then push (same `/ship` gates as appropriate).
- Close: `gh issue close N --comment "…"` + emit `fix-deployed` with `issue: N`.

### 5. Non-Tier-1

Post an analysis comment (root cause / repro / approach). Do **not** close.
Optionally seed an improve backlog row if framework work is needed:

```markdown
| CI-<N> | consumer #<N> | <title> | OPEN | → framework-ux or example-apps |
```

### 6. Report

Log `lane: consumer-issues`. Summarize issue #, author, tier, action taken.
`budget_consumed: 0` (triage/comment) or `1` (implemented fix).

## Hard rules

- **One issue per cycle** (plus trivial already-fixed closes).
- **Do not** treat owner `future` enhancements as consumer bugs.
- **Dependabot is not a consumer** — handled by `github_prs`.
- Coordinate with `/issues`: same lock file; if another session holds the lock, skip implement.
- Prefer consumer bugs over STALE capability re-stamps.
