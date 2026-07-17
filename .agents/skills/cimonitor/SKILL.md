---
name: cimonitor
description: Monitor CI pipeline status, diagnose failures, and drive the badge back to green
---

Monitor CI/CD pipeline status. Checks both the current branch and the CI badge workflow on main.

**Also wired into `/improve`:** every improve cycle runs Step 0c (see `.claude/commands/improve.md` and `improve/strategies/cimonitor.md`) — a cheap snapshot of the `main` badge. When the latest completed `ci.yml` run is red, that improve cycle becomes CI repair (this skill's body) and does not pick a product lane. When green / in progress / `gh` unavailable, improve logs one line and continues.

**Local habits (pair with repair, do not replace the badge):**

| When | Command |
|------|---------|
| Mid-edit | `make ci-changed` |
| Before ship | `make ci-fast` (includes `ship-surface`) |
| After fixing a *new* badge-red class | Promote into `scripts/ship_surface.py` or `preflight_surface.py` |
| Concordance | `docs/contributing/local-ci-concordance.md` |

Tier 0 is intentional subset of GitHub; ship-surface closes the recurrent gap
(bandit / SPEC / IR goldens / viewport). Full matrix + walks remain Tier 2.

## 1. Check the CI badge workflow (always)

The README badge tracks the `CI` workflow on `main`. Always check this first:

```bash
gh run list --workflow ci.yml --branch main --limit 1 \
  --json status,conclusion,databaseId,url,displayTitle,updatedAt
```

Report whether the badge is green or red. If red, this takes priority — investigate and fix before other work.

## 2. Find runs for the current branch

```bash
gh run list --branch $(git branch --show-current) --limit 5 \
  --json status,conclusion,name,url,databaseId,event,workflowName
```

## 3. Poll in-progress runs

For each `in_progress` or `queued` run, poll every 15 seconds up to 20 attempts
**only when already in repair mode after a push** (do not burn an improve cycle
waiting on green):

```bash
gh run view <run-id> --json status,conclusion,name
```

## 4. Per-job breakdown

```bash
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion, startedAt, completedAt}'
```

Present as a table. Real `ci.yml` jobs include (names vary with matrix):

| Job family | What fails look like |
|------------|----------------------|
| `Python Tests (py3.12/13/14)` | full unit + integration non-e2e |
| `lint` | ruff, **bandit medium on src/**, CSS clip/raw-ramp, coverage |
| `type-check` | mypy |
| `Security Tests` | JWT fuzz, RBAC matrix, bandit, pip-audit |
| `integration` | integration tests (needs prior jobs) |
| `E2E Smoke` | example validate / serve |
| `PostgreSQL Tests` | service container |
| `E2E Runtime` | Playwright-ish runtime |
| `INTERACTION_WALK` | workspace gestures + **viewport geometry** |
| `GUIDE_WALK` | onboarding overlays |
| `UX Contracts` | `ux verify --contracts` on support_tickets |
| `Homebrew Formula Validation` | formula / version |

## 5. Diagnose and fix failures

For each failed job:

1. Fetch logs: `gh run view <run-id> --log-failed | tail -200`
2. Map log signature → **local mirror** (run this *before* guessing):

| Log signature | Local command (run first) |
|---------------|---------------------------|
| `B324` / `bandit` / `>> Issue:` | `make ship-surface` or `bandit -c pyproject.toml -r src/ --severity-level medium` |
| `SPECIFICATION.md is stale` / `test_example_spec_bar` | `pytest tests/unit/test_example_spec_bar.py -q` |
| `pattern_count` | `pytest tests/unit/test_patterns_phase2_kb_1217.py::test_pattern_count_meta_matches_actual_count -q` |
| `ir_reader_baseline` / `baselined orphan` | `pytest tests/unit/test_ir_field_reader_parity.py::test_no_new_ir_field_orphans -q` |
| `test_simple_dsl_to_ir_snapshot` / syrupy | `pytest tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot -q` |
| `spec_brief_simple_task` | `pytest tests/unit/test_spec_narrative_brief_snapshot.py -q` |
| `DRAWER_PATTERN` / `.dz-sidebar-toggle` / viewport | `pytest tests/unit/test_viewport.py -q` then INTERACTION_WALK if shell CSS |
| mypy | `mypy src/dazzle` |
| ruff | `ruff check src/ tests/ --fix && ruff format src/ tests/` |
| preflight / api surface / docs drift | `make preflight-surface` |

3. **Fix ALL errors — including pre-existing ones.** Goal is green badge.
4. Commit, push, re-snapshot.

## 6. Close the loop (mandatory after repair)

Fixing main without teaching Tier 0 is how the badge re-reds on the next ship.

After a successful product fix (or in the same commit when small):

1. Ask: **would `make ship-surface` or `make preflight-surface` have caught this?**
2. If **no** → promote the check into `scripts/ship_surface.py` (`SHIP_TESTS` or bandit)
   or `scripts/preflight_surface.py` (`SURFACE_TESTS`), with a remediation line.
3. If the failure was path-specific, add a pack to `scripts/ci_changed.py`.
4. Log one line: `ci_gap: <class> | local_mirror: none → promoted to ship-surface`

Do **not** treat "badge green after full CI" as complete without this step when
the failure class was new.

## 7. Report summary

```
## CI Status

**Badge (main):** ✅ green | ❌ red (failing since <date>)
**Current branch:** <branch> — <status>

### Job Results (run #<id>)
| Job | Result |
|-----|--------|
| ... | ...    |

### Local mirror
- command that would have caught this: <make ship-surface | …>
- promoted to ship-surface/preflight? yes | n/a (already covered) | TODO

### Action Required
- <what needs fixing, if anything>
```
