Commit all current changes and push to the remote. Follow these steps exactly:

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop.
- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to auto-fix lint issues.
- Run `mypy src/dazzle --ignore-missing-imports --exclude 'eject'` to catch type errors. **This lint + type pair must stay identical across `/ship`, `/check`, and CI** — change one, change all three. (`/ship` deliberately runs the fast drift/policy gates below instead of `/check`'s full unit-test pass; that difference is by design, not drift.)
- **Run drift + policy gates** — fast (~10s, no DB), catches the recurring Python ↔ htmx/Alpine boundary regressions (#949 / #963 / #966 / #968 class) plus CI-class violations that ruff/mypy don't see (bare excepts, abandoned shims, parser-regex sneaks, etc.):

  ```bash
  pytest tests/unit/test_*_drift.py \
         tests/unit/test_no_*.py \
         $(ls tests/unit/test_idiomorph_alpine_patch.py \
              tests/unit/test_htmx_preload_silence.py \
              tests/unit/test_filter_ref_select_cancellation.py \
              tests/unit/test_delete_preference_idempotent.py \
              tests/unit/test_alpine_error_handler.py \
              tests/unit/test_view_transition_swap.py \
              tests/unit/test_action_url_surface_resolution.py \
              tests/unit/test_htmx_undefined_guards.py \
              tests/unit/test_forbidden_detail.py \
              tests/unit/test_typed_runtime_no_jinja.py \
              tests/unit/test_complexity_ratchet.py \
              tests/unit/test_import_contracts.py \
              tests/unit/test_dedup_footgun_gates.py \
              tests/unit/test_swallow_ratchet.py \
              2>/dev/null) \
         -q
  ```

  Globs (`test_*_drift.py`, `test_no_*.py`) auto-pick up new gates so this list doesn't rot. The trailing explicit files are the gates that don't follow either naming convention: the htmx/Alpine boundary regressions, plus the **framework structural-fitness gates** (`test_complexity_ratchet.py` = radon CC/MI ratchet, `test_import_contracts.py` = import-linter layer contracts — both shipped v0.83.26; the ratchet shipping v0.83.27 red is exactly why they're pinned here). The `ls ... 2>/dev/null` wrapper drops any entry whose file has been deleted upstream so pre-flight survives drift (#1156). When you delete a pinned-regression test, remove its line here in the same commit. A complexity-ratchet failure means a touched function crossed CC 15 / a file dropped MI rank — refactor (often: extract a helper to keep the inline branch count down), or regenerate the baseline with `dazzle fitness code --write-baseline` if the increase is genuinely justified.

  If a drift gate fails, **fix the regression** — or, if it's a deliberate API-surface change, regenerate the baseline with `--write` and add a CHANGELOG entry under Added/Changed/Removed. Never bypass.

  Pre-ship gap that motivated keeping the policy gates in here (v0.65.11 → v0.65.12): the chaos-monkey work added 3 `except Exception: pass` patterns to `src/dazzle/testing/fuzz_runtime/runner.py`; the pre-ship cycle ran only drift gates and missed `test_no_bare_except_pass.py`.

- **Run the spec-drift strict guard** if the project opts in via `[spec] strict = true` in `dazzle.toml` (#1106 Prop 3):

  ```bash
  dazzle spec status --fail-on-strict
  ```

  Fails when a DSL entity isn't named in any row of the `## Domain map` table in `SPEC.md`. Substring prose mentions don't satisfy this — the entity has to appear in a table row, optionally pointing at a `docs/specs/<topic>.md` design doc. Fix by adding the row (and, if the entity introduces a new domain concept, the design doc) before re-running. The guard only fires when the project opts in via the manifest flag; framework-injected entities (AIJob, DeployHistory, FeedbackReport, SystemHealth, SystemMetric) are excluded by default.

- **Build the docs** — catches broken links and nav rot before they ship. This is the gate SP3's `../../ROADMAP.md` link slipped past (a repo-root file — `mkdocs` only resolves links inside `docs/`, so that link is unreachable and `--strict` rejects it):

  ```bash
  mkdocs build --strict
  ```

  `--strict` turns broken internal links, missing nav entries, and unrecognised link targets into errors — the build must pass clean (exit 0, no warnings). Links to repo-root files (`README.md`, `ROADMAP.md`, `CHANGELOG.md`) and to non-`docs/` paths (`benchmarks/`, `examples/`) must be GitHub blob/tree URLs, not `../../` relative paths — `mkdocs` only resolves links inside `docs/`. The docs toolchain is pinned in `requirements-docs.txt` — run `pip install -r requirements-docs.txt` so a local build matches CI (a stale `pymdown-extensions` is what made #1203 look like a repo bug).

- If lint, type, drift, policy, spec-strict, or docs-build errors remain after auto-fix, fix them before proceeding. Do NOT commit code that fails any of these checks.

## 2. Commit

- Stage only the relevant changed files by name (never `git add -A` or `git add .`).
- Do NOT stage files that look like secrets (.env, credentials, tokens).
- Write a concise commit message that explains *why* the change was made, following the conventional commit style used in recent history (`git log --oneline -10`).
- End the commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` (matches the signature on recent commits — bump this when the upstream model changes).
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
