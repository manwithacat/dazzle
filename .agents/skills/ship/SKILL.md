---
name: ship
description: Commit, verify, tag, and push with the repo's pre-flight gate suite (lint, type, drift gates, docs build)
---

Commit all current changes and push to the remote. Follow these steps exactly:

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop.
- Run `ruff check src/ tests/ --fix && ruff format src/ tests/` to auto-fix lint issues.
- Run `mypy src/dazzle` to catch type errors. **This lint + type pair must stay identical across `/ship`, `/check`, and CI** — change one, change all three. CI runs exactly `mypy src/dazzle` (`.github/workflows/ci.yml`), so use that bare form here too — the old `--ignore-missing-imports --exclude 'eject'` flags were **no-ops** (`pyproject.toml` `[tool.mypy]` already sets `ignore_missing_imports = true`, and there is no `eject` path under `src/dazzle`). The real local↔CI mypy divergence is the **installed extras**, not the command: CI installs the `dev,llm,mcp,mobile,postgres,pitch,i18n,viewport,perf,lsp` superset, and a thinner local env makes `warn_unused_ignores` / `warn_return_any` fire differently — sync extras before trusting a local green. (`/ship` deliberately runs the fast drift/policy gates below instead of `/check`'s full unit-test pass; that difference is by design, not drift.)
- **Run drift + policy gates** — fast (~1 min, no DB), catches the recurring Python ↔ htmx/Alpine boundary regressions (#949 / #963 / #966 / #968 class) plus CI-class violations that ruff/mypy don't see (bare excepts, abandoned shims, parser-regex sneaks, etc.):

  ```bash
  pytest tests/unit -m gate -q
  ```

  **The `gate` marker is the single source of truth for this set** — no file list to
  rot. Every fast, DB-free structural/regression gate carries
  `pytestmark = pytest.mark.gate` (the marker is registered in `pyproject.toml`
  `[tool.pytest.ini_options]`), so `-m gate` selects exactly them (~345 tests, ~1 min,
  no Postgres). `tests/unit/test_gate_marker_complete.py` keeps it honest: the
  high-churn gate families (`*drift*`, `test_no_*`, `*ratchet*`) **must** carry the
  marker or that meta-gate fails in CI — which closes the #1466 class (a ratchet gate
  that matched no glob, slipped the local pre-flight, and only went red in CI,
  v0.86.10→.11).

  **Adding a gate:** give the test file `pytestmark = pytest.mark.gate` (merge into a
  list — `pytestmark = [pytest.mark.gate, pytest.mark.asyncio]` — if it already has a
  `pytestmark`) and it runs here automatically. Keep gates **fast and DB-free** —
  anything needing Postgres/Playwright belongs only in CI's full suite, never this
  pre-flight. A ratchet failure (complexity CC>15 / MI drop; deferred-import or swallow
  count grew) means: refactor (often extract a helper), or regenerate the baseline
  (`dazzle fitness code --write-baseline`, or the gate's own baseline fixture) if the
  increase is genuinely justified. This set mirrors the structural/regression gates in
  CI's `Python Tests` job so a red badge is caught locally first.

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
- End the commit message with your harness's agent-attribution trailer, if it defines one (a `Co-Authored-By:` line naming the agent — match the signature style visible in recent commits; harnesses that supply their own trailer automatically need nothing extra).
- Use a HEREDOC to pass the message to `git commit -m`.

## 3. Tag (if version was bumped)

- Check if `pyproject.toml` was modified in this commit by running `git diff HEAD~1 HEAD -- pyproject.toml`.
- If the `version = "X.Y.Z"` line changed, extract the new version and create a lightweight tag: `git tag vX.Y.Z`.
- The tag MUST be created AFTER the commit so it points to the correct commit (not the parent).

## 4. Push

- Run `git push` to push the current branch to origin.
- If a tag was created in step 3, push **only that tag**: `git push origin vX.Y.Z`. This triggers release workflows (PyPI, Homebrew). **Never `git push origin --tags`** — a clone that still holds historically-pruned patch tags re-publishes ALL of them (the 2026-07-02 incident re-pushed 257 pruned v0.82–v0.87 tags; the prune-old-releases workflow had to be dispatched to sweep them).
- If the push is rejected (e.g. non-fast-forward), do NOT force-push. Inform the user and stop.

## 5. Signal the improvement loop

After a successful push, emit the `fix-deployed` signal so /improve lanes
re-verify rows the change may affect (the cross-lane contract in
`improve.md` names /ship as this signal's emitter — previously declared
but never wired, so lanes sat on stale verification state across releases):

```bash
python -c "
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='ship', kind='fix-deployed', payload={'sha': '$(git rev-parse --short HEAD)', 'version': 'vX.Y.Z'})
"
```

If step 4 pushed a **published-release tag** — one matching `vX.Y.0`, the same
`endsWith('.0')` condition the release workflows use to publish to PyPI/Homebrew —
additionally emit `dazzle-updated` (the cross-lane contract's "(external — releases)"
signal). This is what tells /improve a new framework version is live: lanes mark
affected rows for re-verification and the driver resets the explore budget
(new release = fresh explore territory):

```bash
python -c "
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='ship', kind='dazzle-updated', payload={'version': 'vX.Y.0', 'sha': '$(git rev-parse --short HEAD)'})
"
```

Both are best-effort — a failure here never blocks the ship; note it and continue.

## 6. Final verification

- Run `git status` one last time to confirm the worktree is clean.
- Report the final state: commit SHA, branch, and worktree status.
