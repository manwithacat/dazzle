Commit all current changes, push to the remote, and monitor CI/CD until the worktree is clean and the pipeline passes. Follow these steps exactly:

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop.
- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to auto-fix lint issues.
- Run `mypy src/dazzle` to catch type errors.
- If lint or type errors remain after auto-fix, fix them before proceeding. Do NOT commit code that fails lint or type checks.

## 2. Commit

- Stage only the relevant changed files by name (never `git add -A` or `git add .`).
- Do NOT stage files that look like secrets (.env, credentials, tokens).
- Write a concise commit message that explains *why* the change was made, following the conventional commit style used in recent history (`git log --oneline -10`).
- End the commit message with: `Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>`
- Use a HEREDOC to pass the message to `git commit -m`.

## 3. Push

- Run `git push` to push the current branch to origin.
- If the push is rejected (e.g. non-fast-forward), do NOT force-push. Inform the user and stop.

## 4. Monitor CI/CD

- After pushing, poll for CI/CD status using `gh run list --branch $(git branch --show-current) --limit 1 --json status,conclusion,name,url` every 15 seconds, up to 20 attempts.
- While the run status is `in_progress` or `queued`, keep polling and show a brief status update each time.
- If the run concludes with `success`, report success and the run URL.
- If the run concludes with `failure`, fetch the failed job logs with `gh run view <run-id> --log-failed | tail -80` and report the failure details so the user can decide what to do.
- If no CI run appears after 3 polls, note that no workflow was triggered and stop.

## 5. Final verification

- Run `git status` one last time to confirm the worktree is clean.
- Report the final state: commit SHA, branch, CI result, and worktree status.
