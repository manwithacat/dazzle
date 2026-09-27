# Strategy: github_prs (driver-level)

**Force:** `/improve github-prs` or `/improve prs`
**Probe:** `uv run python scripts/improve_github_inbox.py`
**Budget:** `0` (merge/review bookkeeping; no explore).

Process open pull requests. **Routine Dependabot PRs auto-merge** when CI is
green and the PR is mergeable. Human PRs get a light review pass (status note /
request changes) — do not auto-merge non-bot PRs without explicit human intent.

## When the driver picks this

- Inbox `heat` is `dependabot_merge` or `dependabot_ci_red`
- Or `recommended[0].kind` ∈ {`dependabot_merge`, `dependabot_ci_red`, `human_pr_review`}
- Force path above

**Preemption:** after main CI red (0c) and CodeQL high (0c2), Dependabot ready
to merge outranks product explore (cheap fleet hygiene). Dependabot **CI red**
outranks STALE-clear explore when the failure is on the PR checks.

## Dependabot auto-merge gates (all required)

From the probe `dependabot_ready[]` / `checks.ready`:

| Gate | Pass when |
|------|-----------|
| Author | Dependabot (`app/dependabot`, `dependabot[bot]`, …) |
| Draft | `isDraft == false` |
| Checks | No **FAILURE** / **CANCELLED** / **TIMED_OUT** among non-ignorable checks; no pending required jobs; ≥1 SUCCESS |
| Merge | not `CONFLICTING` / not `DIRTY` |
| Scope | Prefer routine dep bumps (Actions, lockfile, minor pins). If the PR touches application source beyond dep metadata, **stop and review** — do not auto-merge |

Ignorable checks (probe): `claude-review`, docs `deploy`, codecov, bare `CodeQL` status, semgrep status. **CI** and **CodeQL Analyze** jobs still count.

## Playbook

### 1. Probe

```bash
uv run python scripts/improve_github_inbox.py
```

### 2a. Merge ready Dependabot (preferred)

For each `dependabot_ready` entry (max **2** per cycle):

```bash
# Re-confirm checks (optional second source)
gh pr checks <N> --repo manwithacat/dazzle
gh pr view <N> --repo manwithacat/dazzle --json mergeable,mergeStateStatus,statusCheckRollup,files

# Merge (squash keeps main history clean for bot bumps)
gh pr merge <N> --repo manwithacat/dazzle --squash --delete-branch
```

If merge fails because branch is behind:

```bash
gh pr update-branch <N> --repo manwithacat/dazzle
# leave for next cycle (CI will re-run) — do not force-merge
```

Log each merge. Emit:

```python
emit(source="improve", kind="fix-deployed",
     payload={"pr": N, "kind": "dependabot_merge"})
```

### 2b. Dependabot CI red

- `gh pr checks <N>` / `gh run view … --log-failed`
- If flake (timeout, infra): `gh run rerun <id> --failed` and wait/log
- If real break from the bump: either fix on a follow-up commit on the PR branch
  (if permission) or comment and leave open — do not squash-merge red CI

### 2c. Human PRs

- Summarize diff + CI status in the cycle log
- If CI green and change is trivial/docs-only: comment "looks ready" (do **not**
  merge without operator policy — only Dependabot is auto-merge)
- If CI red: comment with failing job pointer

### 3. Report

Log `lane: github-prs`. List PRs merged / blocked / reviewed.
`budget_consumed: 0`.

## Hard rules

- **Never** auto-merge non-Dependabot PRs in this strategy.
- **Never** merge with failing non-ignorable checks.
- Prefer **squash** for Dependabot.
- One cycle may merge up to two ready Dependabot PRs; then stop (keep cycles short).
- After merges, next self-schedule should treat main CI as in-progress (deployed).
