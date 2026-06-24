Commit all current changes and push to the remote. Follow these steps exactly:

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop.
- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to auto-fix lint issues.
- Run `mypy src/dazzle` to catch type errors. **This lint + type pair must stay identical across `/ship`, `/check`, and CI** — change one, change all three. CI runs exactly `mypy src/dazzle` (`.github/workflows/ci.yml`), so use that bare form here too — the old `--ignore-missing-imports --exclude 'eject'` flags were **no-ops** (`pyproject.toml` `[tool.mypy]` already sets `ignore_missing_imports = true`, and there is no `eject` path under `src/dazzle`). The real local↔CI mypy divergence is the **installed extras**, not the command: CI installs the `dev,llm,mcp,mobile,postgres,pitch,i18n,viewport,perf,lsp` superset, and a thinner local env makes `warn_unused_ignores` / `warn_return_any` fire differently — sync extras before trusting a local green. (`/ship` deliberately runs the fast drift/policy gates below instead of `/check`'s full unit-test pass; that difference is by design, not drift.)
- **Run drift + policy gates** — fast (~1 min, no DB), catches the recurring Python ↔ htmx/Alpine boundary regressions (#949 / #963 / #966 / #968 class) plus CI-class violations that ruff/mypy don't see (bare excepts, abandoned shims, parser-regex sneaks, etc.):

  ```bash
  pytest tests/unit/test_*drift*.py \
         tests/unit/test_no_*.py \
         tests/unit/test_*ratchet*.py \
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
              tests/unit/test_import_contracts.py \
              tests/unit/test_dedup_footgun_gates.py \
              tests/unit/test_testing_class_method_cap_1446.py \
              tests/unit/test_nonowner_boot_gate_1462.py \
              tests/unit/test_membership_admission_gate.py \
              tests/unit/test_route_override_response_contract.py \
              tests/unit/test_parse_component_contract.py \
              tests/unit/test_widget_contract.py \
              2>/dev/null) \
         -q
  ```

  **Three globs auto-pick up new gates so the list can't silently rot:**
  `test_*drift*.py` (snapshot/baseline drift, incl. `_drift_<issue>` suffixes), `test_no_*.py`
  (forbidden-pattern gates), and `test_*ratchet*.py` (structural-fitness ratchets —
  complexity, swallow, deferred-imports #1438, etc.). **Name a new fast structural gate to
  match one of these globs** (`*drift*` / `test_no_*` / `*ratchet*`) and it registers
  automatically — that's the preferred convention. The trailing explicit list is the residue
  that doesn't fit a glob: the htmx/Alpine boundary regressions, `test_import_contracts.py`
  (import-linter layer contracts), and the `*_gate`/`*_contract`/`*_cap` gates whose names
  don't match a glob. **All entries must be fast and DB-free** (the pre-flight runs no
  Postgres) — a gate needing PG/Playwright belongs in CI's full suite, not here. The
  `ls ... 2>/dev/null` wrapper drops any deleted file so pre-flight survives drift (#1156);
  remove a line when you delete its test. A ratchet failure (complexity CC>15 / MI drop;
  deferred-import count grew; swallow count grew) means: refactor (often extract a helper),
  or regenerate the baseline (`dazzle fitness code --write-baseline`, or the gate's own
  baseline fixture) if the increase is genuinely justified.

  Why this set: it mirrors the structural/regression gates in CI's `Python Tests` job so a
  red badge is caught locally first. The #1466 deferred-import-ratchet regression (red badge,
  v0.86.10→.11) slipped precisely because that ratchet matched no glob and wasn't listed — the
  `test_*ratchet*.py` glob now closes that class.

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
