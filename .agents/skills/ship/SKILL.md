---
name: ship
description: Commit, verify, tag, and push with the repo's pre-flight gate suite (lint, type, drift gates, docs build)
---

Commit all current changes and push to the remote. Follow these steps exactly.

Local ↔ CI concordance is documented in
`docs/contributing/local-ci-concordance.md`. The single runner is
`scripts/ci_local.sh` (Makefile: `preflight-surface` / `ship-surface` /
`ci-changed` / `ci-fast` / `ci-core`).

## 1. Pre-flight checks

- Run `git status` (never use `-uall`) and `git diff --stat` to understand what changed.
- If the worktree is already clean and there is nothing to commit, say so and stop
  (unless the user asked to **bump + ship a release** of already-committed work —
  then proceed to version bump / gates / tag / push with an empty tree is fine only
  when they explicitly want a version bump of clean history).

### Surface debt gate (mandatory — every ship)

**Before** choosing a tier, unpaid structural/artifact debt must be clear.
This is the pattern that kept main red while laptops looked green (API
baselines, docs drift, deferred imports, import contracts, HM gallery,
catalogue CSS).

```bash
make preflight-surface
# → bash scripts/ci_local.sh preflight-surface
# → python scripts/preflight_surface.py
```

- **Non-zero exit → fix debt, do not commit or tag.** Remediation text is
  printed by the script (inspect api --write, docs generate, baselines, HM
  `site/build_site.py`, etc.).
- `ci-fast` / `ci-core` already run this **first**; calling it alone is for
  mid-change checks. Never skip by running ad-hoc pytest only.

If `origin/main` CI is already red for surface debt, **repair main first**
(or include the repair in this ship) — do not stack another feature tip.

### Ship-surface pack (mandatory — every Tier 0 ship)

Recurrent badge-red classes (bandit medium, example SPEC freshness, IR/brief
goldens, pattern_count, viewport DRAWER freshness). See
`scripts/ship_surface.py`.

```bash
make ship-surface
# also runs automatically inside make ci-fast (after preflight-surface)
```

Optional mid-edit path packs (does not replace Tier 0):

```bash
make ci-changed   # scripts/ci_changed.py — packs from git diff
```

### Gate tier (required)

Decide the tier from the ship arguments / intent (each includes preflight-surface):

| Situation | Tier | Command |
|-----------|------|---------|
| Default `/ship`, patch with no version bump | **Tier 0** (ship-fast) | `make ci-fast` |
| `/ship minor`, `/ship major`, or any commit that changes `pyproject.toml` `version =` | **Tier 1** (ci-core) | `make ci-core` |
| Operator asked for maximum local confidence | Tier 1 | `make ci-core` |

```bash
# Tier 0 — default (~3–4 min, no DB)
make ci-fast
# → bash scripts/ci_local.sh tier0
#    preflight-surface          ← structural debt gate
#    ship-surface               ← bandit + recurrent SPEC/IR/viewport pack
#    ruff check --fix + format
#    mypy src/dazzle
#    pytest tests/unit -m gate
#    mkdocs build --strict

# Tier 1 — before release tags (~full non-e2e CI mirror)
make ci-core
# → bash scripts/ci_local.sh tier1
#    uv sync --frozen (CI extras, Python 3.12)
#    preflight-surface
#    scripts/build_dist.py
#    ruff check + format --check
#    mypy src/dazzle
#    CSS clip/raw-ramp + dazzle coverage --fail-on-uncovered
#    bandit + pip-audit (hard-fail)
#    JWT fuzz + shapes RBAC matrix
#    pytest -n auto --dist loadgroup -m "not e2e"
#    mkdocs build --strict
```

**Do not** re-expand these steps ad-hoc in the agent transcript — call the
Makefile / script so extras lists and command strings stay one source of truth
with `.github/workflows/ci.yml`. If you change CI, update `scripts/ci_local.sh`
constants in the same change.

**mypy command** is always `mypy src/dazzle` (same as CI type-check job). The
local↔CI divergence is **installed extras**, not flags: Tier 1 syncs the
type-check extras superset (`dev,llm,mcp,mobile,postgres,pitch,i18n,viewport,perf,lsp`).
Tier 0 may warn if the active interpreter ≠ 3.12 — for release tags, prefer
Tier 1.

**Gate marker** (`pytest -m gate`): every fast, DB-free structural gate must
carry `pytestmark = pytest.mark.gate` (see `tests/unit/test_gate_marker_complete.py`).
Ratchet failures → refactor or regenerate baseline (`dazzle fitness code
--write-baseline`); never bypass.

### Optional project guards (still ship-owned)

- **Spec strict** (only if `[spec] strict = true` in the project's `dazzle.toml`):

  ```bash
  dazzle spec status --fail-on-strict
  ```

- If preflight-surface, tier0/tier1, or spec-strict fails, **fix before
  committing**. Do NOT ship red.

Tier 0 is **not** full GitHub CI: Postgres services, Playwright walks,
guide-walk matrix, and multi-version python-tests still only run on Actions.
See the concordance doc for Tier 2.

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
- **Release tags require Tier 1 green** (`make ci-core`) in this session (or operator-confirmed) before `git push origin vX.Y.Z`.

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
- Report the final state: commit SHA, branch, worktree status, and which gate tier ran.
