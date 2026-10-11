---
name: issues
description: Triage, investigate, resolve, and ship consumer-forced repository issues through a bounded loop.
---

Consumer-forced GitHub issue resolver: triage, investigate, implement, ship, repeat — until
no admissible issue remains or the user stops you.

## Admission rule

Work is admitted only under **consumer force** (ADR-0057):

- issues filed from, or reproducing in, an app listed in `flense_consumers.toml`;
- consumer-app CI failures traced to the framework;
- proof-surface regressions (a gate on a claimed guarantee went red).

Everything else is triaged and commented on, not implemented. **Never implement** an issue
labelled `future` or one that points at a `PARKED` Deferred Decision (`docs/decisions/`)
until the DD is `FORCED` with a named consumer; then implement *that* plan.

## Modes

- **`/issues`** (default) — the decision gate (Step 3) pauses on genuine ambiguity; the loop
  stops when the admissible backlog is all large/blocked.
- **`/issues auto`** — escalate per issue via the tiers below; pause only when a tier says so.

| Tier | When | Behaviour |
|------|------|-----------|
| **1 — Autonomous** | Clear root cause, one correct approach, reversible, no change to a public claim, default, dependency or architecture | Implement → ship → close → next |
| **2 — Design decision** | 2–4 nameable options with real trade-offs, or a user-visible contract / default / claim / dependency / irreversible change | ask-user-choice with the options, then implement |
| **3 — Needs brainstorming** | The shape of the solution is unclear | Brainstorm with the user to a written plan; implement if small/medium, else comment the plan and leave open |

Bias toward Tier 1; escalate only for a specific, nameable reason. Tier-2 questions may be
front-loaded in one ask-user-choice round before implementing anything.

Backward compatibility is not required (ADR-0003): clean breaks, update all callers in the
same commit, note breaks in CHANGELOG.md and the closing comment.

## Loop

### Step 0: Shared mutation lock

Any agent pushing to `main` coordinates through `.dazzle/improve.lock` (`PID ISO-timestamp`,
15-min TTL). At cycle start, a fresh lock means **read-only this cycle** (triage and comments
only); a stale one is removed. Acquire it (`issues-<PID> <ISO-timestamp>`) immediately before
implementing, re-stamp it if work runs past 15 min, and release it (`rm -f`) as soon as the
push lands or on any early exit.

### Step 1: Triage

- `gh issue list --state open --limit 50 --json number,title,labels,author`.
- For each open issue, check whether a commit already resolves it
  (`git log --oneline --all --grep="#<number>"`). If so: comment with the commit(s), close it,
  remove `needs-triage`, and emit the `fix-deployed` signal (best-effort):
  `python -c "from dazzle.cli.runtime_impl.ux_cycle_signals import emit; emit(source='issues', kind='fix-deployed', payload={'issue': <number>})"`
- Apply the admission rule; show a table of admissible issues (number, title, labels, author).
- Third-party issues (author other than `manwithacat`): analyse and comment only — root cause
  or feasibility, code paths, suggested approach. Do not implement or close.

### Step 2: Investigate

With 2+ admissible issues, dispatch one investigation subagent per issue in parallel
(parallel-investigation; root-cause work runs at the session tier). Each returns: scope
(small/medium/large), root cause, files, approach, dependencies, tier (with 2–4 options for
Tier 2). With one issue, investigate directly.

### Step 3: Prioritise and pick

Order by consumer impact, then bug > enhancement, unblocking dependencies, and smaller scope.
Remove `needs-triage`. Dispatch on the tier (default mode: ask on genuine ambiguity).

### Step 4: Implement

Follow codebase conventions, add or update tests, one issue per cycle.

### Step 5: Ship

Hold the lock throughout. Ship through the **ship** skill (`make ci-fast`, `make push-gate`,
commit referencing the issue number, push); monitor CI and fix forward if your change broke it.
Release the lock once the push lands.

### Step 6: Close and loop

Comment what was done, close the issue, remove `needs-triage`, return to Step 1. Stop when no
admissible issue remains (auto mode) or when the rest are large/blocked (default mode), and
report: issues shipped, issues left open with reasons, saved Tier-3 plans.
