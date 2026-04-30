Commit all current changes and push to the remote. Follow these steps exactly:

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop.
- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to auto-fix lint issues.
- Run `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject' && mypy src/dazzle_back/ --ignore-missing-imports` to catch type errors (matches CI).
- **Run drift gates** — fast (~2s, no DB), catches the recurring Python ↔ htmx/Alpine boundary regressions (#949 / #963 / #966 / #968 class):

  ```bash
  pytest tests/unit/test_api_surface_drift.py \
         tests/unit/test_card_picker_attributes.py \
         tests/unit/test_idiomorph_alpine_patch.py \
         tests/unit/test_inline_edit_escape.py \
         tests/unit/test_htmx_preload_silence.py \
         tests/unit/test_preload_extension_disabled.py \
         tests/unit/test_filter_bar_no_xfor.py \
         tests/unit/test_template_xfor_alpine_children.py \
         tests/unit/test_workspace_cls_reservation.py \
         tests/unit/test_list_surface_cls_reservation.py \
         -q
  ```

  If any drift gate fails, **fix the regression** (or regenerate the baseline + add a CHANGELOG entry for API-surface drift). Never bypass.
- If lint, type, or drift errors remain after auto-fix, fix them before proceeding. Do NOT commit code that fails any of these checks.

## 2. Commit

- Stage only the relevant changed files by name (never `git add -A` or `git add .`).
- Do NOT stage files that look like secrets (.env, credentials, tokens).
- Write a concise commit message that explains *why* the change was made, following the conventional commit style used in recent history (`git log --oneline -10`).
- End the commit message with: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Use a HEREDOC to pass the message to `git commit -m`.

## 3. Tag (if version was bumped)

- Check if `pyproject.toml` was modified in this commit by running `git diff HEAD~1 HEAD -- pyproject.toml`.
- If the `version = "X.Y.Z"` line changed, extract the new version and create a lightweight tag: `git tag vX.Y.Z`.
- The tag MUST be created AFTER the commit so it points to the correct commit (not the parent).

## 4. Push

- Run `git push` to push the current branch to origin.
- If a tag was created in step 3, also run `git push origin --tags` to push it. This triggers release workflows (PyPI, Homebrew).
- If the push is rejected (e.g. non-fast-forward), do NOT force-push. Inform the user and stop.

## 5. Final verification

- Run `git status` one last time to confirm the worktree is clean.
- Report the final state: commit SHA, branch, and worktree status.
