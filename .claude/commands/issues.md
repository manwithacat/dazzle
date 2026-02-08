Review GitHub issues, triage resolved ones, and start investigating the next logical task. Follow these steps exactly:

## 1. Fetch open issues

- Run `gh issue list --state open --limit 50` to get all open issues.
- Run `gh issue list --state closed --limit 20 --search "sort:updated-desc"` to get recently closed issues.
- Display a summary table: number, title, labels, state.

## 2. Evaluate resolved issues

- For each **open** issue, check if the fix has already been committed by searching `git log --oneline --all --grep="#<number>"` for the issue number.
- If a commit exists that resolves the issue:
  1. Read the issue body with `gh issue view <number>`.
  2. Post a comment summarising what was implemented and which commit(s) resolve it: `gh issue comment <number> --body "..."`.
  3. Close the issue: `gh issue close <number>`.
- Report which issues were closed and which remain open.

## 3. Pick the next issue

- From the remaining open issues, choose the most logical next step based on:
  - **Priority labels** (bug > enhancement > feature)
  - **Dependencies** (issues that unblock others first)
  - **Complexity** (prefer smaller, well-scoped issues that can be completed in one session)
- Display your reasoning for the choice.

## 4. Investigate the chosen issue

- Read the full issue with `gh issue view <number>`.
- Search the codebase for relevant files using Grep/Glob.
- Read the key files that would need to change.
- Summarise your findings:
  - **Root cause** (for bugs) or **design approach** (for features)
  - **Files to modify**
  - **Estimated scope** (small / medium / large)
  - **Any open questions** for the user
- Ask the user if they want to proceed with implementation.
