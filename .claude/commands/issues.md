Iterative GitHub issue resolver. Run continuously: triage, implement, ship, repeat — until all open issues are resolved or the user stops you.

## Loop: Triage → Implement → Ship → Repeat

### Step 1: Triage

- Run `gh issue list --state open --limit 50 --json number,title,labels,author` to get all open issues with author info.
- Run `gh issue list --state closed --limit 20 --search "sort:updated-desc"` to check recently closed.
- For each **open** issue, check if the fix has already been committed: `git log --oneline --all --grep="#<number>"`.
- If a commit exists that resolves an issue:
  1. Read the issue body with `gh issue view <number>`.
  2. Post a comment summarising what was implemented and which commit(s) resolve it.
  3. Close the issue: `gh issue close <number>`.
- Display a summary table of remaining open issues: number, title, labels, **author**.

### Author routing

Issues are handled differently based on who filed them:

- **`manwithacat` issues** → full cycle: investigate, implement, ship, close.
- **Third-party issues** (any other author) → analyse and comment only:
  1. Read the full issue with `gh issue view <number>`.
  2. Search the codebase to understand the request or reproduce the bug.
  3. Post a comment with your analysis: root cause (bugs), feasibility assessment (features), relevant code paths, and suggested approach. Do NOT implement, commit, or close.
  4. Skip to the next issue.

### Step 2: Prioritise and pick

- From remaining open **`manwithacat`** issues, choose the best next issue based on:
  - **Priority labels** (bug > enhancement > feature)
  - **Dependencies** (issues that unblock others first)
  - **Complexity** (prefer smaller, well-scoped issues completable in one session)
  - **Momentum** (issues related to recently completed work)
- Display your reasoning briefly.

### Step 3: Investigate

- Read the full issue with `gh issue view <number>`.
- Search the codebase for relevant files using Grep/Glob.
- Read the key files that would need to change.
- Determine: root cause (bugs) or design approach (features), files to modify, scope (small/medium/large).

**Decision gate**: If the issue has genuine ambiguity — multiple valid approaches with real trade-offs, unclear requirements, or would benefit from user input — ask the user before proceeding. Otherwise, pick the most sensible approach following existing codebase patterns and continue.

### Step 4: Implement

- Write the fix or feature, following existing codebase conventions.
- Add or update tests to cover the changes.
- Keep changes focused — one issue per cycle.

### Step 5: Quality checks

- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to fix lint.
- Run `pytest tests/ -m "not e2e" -x` — ensure all unit tests pass. If failures are related to your changes, fix them. If unrelated pre-existing failures, note them and continue.
- Run `mypy src/dazzle` — fix any type errors in changed files.

### Step 6: Ship

- Commit the changes with a descriptive message referencing the issue number (e.g., "Fix X for issue #N").
- Push to the remote.
- Monitor CI with `gh run list --branch $(git branch --show-current) --limit 3` — if CI fails on your changes, fix and re-push. If CI fails on unrelated flaky tests, note it and move on.

### Step 7: Close the issue

- Post a comment on the issue summarising what was done.
- Close the issue: `gh issue close <number>`.

### Step 8: Loop back

- Return to **Step 1** and pick the next issue.
- If no open issues remain, report completion and stop.
- If all remaining issues are large/blocked/need user decisions, summarise the state and ask the user how to proceed.
