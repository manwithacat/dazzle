Iterative GitHub issue resolver. Run continuously: triage, investigate, implement, ship, repeat — until all open issues are resolved or the user stops you.

**This command uses parallel subagents** for investigation — dispatching one per issue to analyze root causes concurrently before picking which to implement.

## Modes

Parse `ARGUMENTS`: if it contains the word `auto`, run in **auto mode**; otherwise run the **default** loop.

- **`/issues`** (default) — standard loop. The decision gate (Step 3) pauses for user input on genuine ambiguity; the loop stops when the remaining backlog is all large/blocked (Step 8).
- **`/issues auto`** — *as-autonomous-as-possible* mode. The loop does **not** stop on a large backlog: it works through **every** open issue, escalating per-issue via the three intervention tiers below. It halts only when no open issues remain or the user stops it. Tier-2/3 pauses surface as prompts — this pairs with `/remote-control`, so design questions can be answered from anywhere and the loop resumes on the reply. This is a high-velocity, high-risk strategy *by intent*: a degree of imperfection and rework is expected and acceptable.

## Intervention tiers (auto mode)

Every issue is classified into one tier during investigation (Step 2). The classification is the agent's own call — **bias toward Tier 1**. Escalate only for a *specific, nameable* reason, never on vague unease.

**The tier-2 / tier-3 discriminator:** *Can I write the design question right now with 2-4 concrete, mutually-exclusive options?* If yes → Tier 2. If the option space itself needs exploring before the question can even be posed → Tier 3.

| Tier | When | Loop behaviour |
|------|------|----------------|
| **Tier 1 — Autonomous** | Clear root cause; one correct approach, or the codebase convention dictates the choice. Reversible (code + tests, locally verifiable). Does **not** change a public claim, a default behaviour, a dependency, or architecture. *Bug fixes, metadata alignment, added tests, internal refactors with one obvious shape.* | Implement → ship → close → next. No pause. |
| **Tier 2 — Design decision** | 2-4 nameable options with real trade-offs the codebase does not settle; **or** the change touches a user-visible contract, a default, a public/marketing claim, a dependency, or anything not cheaply reversible (data migrations, etc.). The decision is bounded — once made, implementation is clear. *"Implement X vs defer X", "strict default vs opt-in flag".* | Pause: ask the user to choose among the options (ask-user-choice). Implement per the answer → ship → close → next. |
| **Tier 3 — Needs brainstorming** | The *shape* of the solution is unclear — the issue is a goal, not a spec; a new subsystem / new example app / cross-cutting design; you cannot crisply enumerate the options. | Run a structured brainstorming dialogue with the user (use your harness's brainstorming workflow if it has one). Outcome: a written spec/plan. If the resulting work is small/medium → implement it in-loop → ship → close. If large → save the plan (issue comment or `dev_docs/`), comment on the issue, leave it **open**, → next. |

**Front-loading (auto mode):** after Step 2 classifies all issues, you MAY batch every Tier-2 question into a single ask-user-choice round (up to 4 questions) *before* implementing anything — so design decisions are answered once and the implementation phase then runs uninterrupted. Tier-3 brainstorms are still handled one at a time, when their issue comes up in priority order.

**When torn:** Tier 1 vs 2 — lean Tier 1 if the change is reversible and internal; lean Tier 2 if it touches a public contract or claim. Tier 2 vs 3 — lean Tier 2 (a focused question is cheap, and the user can always answer "let's brainstorm this").

## Backward Compatibility Policy

**Backward compatibility is NOT a requirement at this stage.** The project has one major user who is fully engaged with the dev process. When implementing fixes and features:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Do not create wrapper functions, re-exports, or compatibility aliases to preserve old call sites.
- **Update all callers** in the same commit rather than preserving old APIs.
- **Communicate breaking changes** by noting them in CHANGELOG.md (under `### Changed` or `### Removed`) and in the GitHub issue comment when closing. That is sufficient notice.

## Loop: Triage → Investigate → Implement → Ship → Repeat

### Step 0: Shared mutation lock (coordinate with `/improve`)

`/improve` and `/issues` may run as independent loops (separate sessions or cloud routines) on different cadences. Both push to `main`, so they must never mutate the repo concurrently. They coordinate through the **single** file lock `.dazzle/improve.lock` (`PID ISO-timestamp`, 15-min TTL) that `/improve`'s driver already honours — `/improve` aborts its cycle when this lock is held & fresh, so if `/issues` holds it across a ship, `/improve` yields. One lock, bidirectional exclusion.

1. **At cycle start**, read `.dazzle/improve.lock`. If it exists and is **< 15 min old**, another loop (`/improve`) holds the repo → **run read-only only this cycle**: triage (Step 1) and third-party analysis comments are fine, but do **not** implement/commit/push/close. Then loop back (Step 8). If the lock is **> 15 min old**, treat it as stale and `rm -f` it.
2. Triage + investigation (Steps 1–3) are read-only — they don't need the lock.
3. **Immediately before implementing (Step 4), acquire the lock**: re-check it; if now held & fresh, defer (loop back to Step 1); otherwise write `issues-<PID> <ISO-timestamp>` to `.dazzle/improve.lock`. Hold it through Step 6 (ship/push).
4. **Release** the lock (`rm -f .dazzle/improve.lock`) immediately after the push completes (Step 6), and on **any** early exit or error — never leave it held across the idle gap between cycles (that would starve `/improve`).
5. If a single implement→ship will plausibly exceed 15 min, re-stamp the lock's timestamp mid-work so `/improve` doesn't treat it as stale and steal it.

### Step 1: Triage

- Run `gh issue list --state open --limit 50 --json number,title,labels,author` to get all open issues with author info.
- Run `gh issue list --state closed --limit 20 --search "sort:updated-desc"` to check recently closed.
- For each **open** issue, check if the fix has already been committed: `git log --oneline --all --grep="#<number>"`.
- If a commit exists that resolves an issue:
  1. Read the issue body with `gh issue view <number>`.
  2. Post a comment summarising what was implemented and which commit(s) resolve it.
  3. Close the issue: `gh issue close <number>`.
  4. Remove the `needs-triage` label if present: `gh issue edit <number> --remove-label "needs-triage"`.
  5. Emit the `fix-deployed` signal so /improve lanes re-verify affected rows (the
     cross-lane contract names /issues as this signal's emitter — previously
     declared but never wired). Best-effort, never blocks the loop:
     `python -c "from dazzle.cli.runtime_impl.ux_cycle_signals import emit; emit(source='issues', kind='fix-deployed', payload={'issue': <number>})"`
- Clean up stale labels: run `gh issue list --state closed --label "needs-triage" --limit 50 --json number` and remove the label from each: `gh issue edit <number> --remove-label "needs-triage"`.
- Display a summary table of remaining open issues: number, title, labels, **author**.

### Author routing

Issues are handled differently based on who filed them:

- **`manwithacat` issues** → full cycle: investigate, implement, ship, close.
- **Third-party issues** (any other author) → analyse and comment only:
  1. Read the full issue with `gh issue view <number>`.
  2. Search the codebase to understand the request or reproduce the bug.
  3. Post a comment with your analysis: root cause (bugs), feasibility assessment (features), relevant code paths, and suggested approach. Do NOT implement, commit, or close.
  4. Skip to the next issue.

### Step 2: Parallel investigation (when 2+ issues open)

When there are **2 or more open `manwithacat` issues**, dispatch investigation subagents **in parallel** (one per issue, all in a single message). Run them concurrently where the harness supports it (parallel-investigation, else sequential); root-cause investigation is judgment work — run it at the session tier (model-tiering, AGENTS.md Capability Mapping).

Each investigation subagent prompt:

```
Investigate GitHub issue #<number> in the Dazzle project (/Volumes/SSD/Dazzle).

Issue title: <title>

1. Read the full issue: run `gh issue view <number>`
2. Search the codebase for relevant files using Grep/Glob
3. Read the key files that would need to change
4. Determine: root cause (bugs) or design approach (features), files to modify, scope (small/medium/large)
5. Classify the intervention tier:
   - tier1 — you could implement this correctly without user input (clear root
     cause / one correct approach / codebase convention dictates the choice;
     reversible; no change to a public claim, default, dependency, or architecture).
   - tier2 — there is a bounded design choice: 2-4 concrete, mutually-exclusive
     options with real trade-offs, OR the change touches a user-visible contract,
     a default, a public/marketing claim, a dependency, or something not cheaply
     reversible. If tier2, you MUST be able to list the 2-4 options.
   - tier3 — the shape of the solution is unclear; you cannot crisply enumerate
     the options without exploring the problem first.

Return your analysis in this format:
ISSUE: #<number> — <title>
SCOPE: small|medium|large
ROOT_CAUSE: <one-line summary>
FILES: <comma-separated list of files to modify>
APPROACH: <2-3 sentence fix description>
COMPLEXITY: <estimated lines changed>
DEPENDENCIES: <any issues this depends on or blocks>
INTERVENTION: tier1|tier2|tier3 — <one-line reason>
OPTIONS: <tier2 only — 2-4 concrete options, each one line; omit for tier1/tier3>
```

When there is only **1 issue**, skip parallel dispatch and investigate directly (still classify the tier).

### Step 3: Prioritise and pick

- From investigation results, choose the best next issue based on:
  - **Priority labels** (bug > enhancement > feature)
  - **Dependencies** (issues that unblock others first)
  - **Complexity** (prefer smaller, well-scoped issues completable in one session)
  - **Momentum** (issues related to recently completed work)
- Display your reasoning briefly.
- Remove the `needs-triage` label: `gh issue edit <number> --remove-label "needs-triage"`.

**Decision gate — dispatch on the intervention tier:**

- **Default mode:** if the issue has genuine ambiguity — multiple valid approaches with real trade-offs, unclear requirements, or would benefit from user input — ask the user before proceeding. Otherwise pick the most sensible approach following existing codebase patterns and continue.
- **Auto mode:** act on the tier from Step 2:
  - **Tier 1** → go straight to Step 4.
  - **Tier 2** → ask-user-choice with the `OPTIONS` from investigation (one question per issue; or a batched front-loaded round per the front-loading note above). Record the answer, then Step 4 implementing that choice.
  - **Tier 3** → invoke the `brainstorming` skill with the user to produce a written spec. If the spec's work is small/medium, proceed to Step 4. If large, post the spec as an issue comment (or save to `dev_docs/`), leave the issue open, and loop back to Step 3 for the next issue.

### Step 4: Implement

- Write the fix or feature, following existing codebase conventions.
- Add or update tests to cover the changes.
- Keep changes focused — one issue per cycle.

### Step 5: Quality checks

- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to fix lint.
- Run `pytest tests/ -m "not e2e" -x` — ensure all unit tests pass. If failures are related to your changes, fix them. If unrelated pre-existing failures, note them and continue.
- Run `mypy src/dazzle` — fix any type errors in changed files.

### Step 6: Ship

- The shared mutation lock (Step 0) must be **held across this whole step** and released the instant the push (and any CI-fix re-push) is done.
- Run `/bump patch` (or the appropriate level) so the push carries a unique version.
- Commit the changes with a descriptive message referencing the issue number (e.g., "Fix X for issue #N").
- Push to the remote.
- Monitor CI with `gh run list --branch $(git branch --show-current) --limit 3` — if CI fails on your changes, fix and re-push. If CI fails on unrelated flaky tests, note it and move on.
- **Release the lock** (`rm -f .dazzle/improve.lock`) once the push lands.

### Step 7: Close the issue

- Post a comment on the issue summarising what was done.
- Close the issue: `gh issue close <number>`.
- Remove the `needs-triage` label if still present: `gh issue edit <number> --remove-label "needs-triage"`.

### Step 8: Loop back

- Return to **Step 1** and pick the next issue.
- If no open issues remain, report completion and stop.
- **Default mode:** if all remaining issues are large/blocked/need user decisions, summarise the state and ask the user how to proceed.
- **Auto mode:** do **not** stop for a large backlog — continue the loop, escalating each remaining issue via its intervention tier (Step 3). Stop only when no open issues remain (excluding Tier-3 issues deliberately left open with a saved plan, and third-party issues) or the user halts the loop. When you do stop, report: issues shipped, issues left open with reasons, and any saved Tier-3 plans.
