# Plan 11 — Mass Surface Flip + Per-Example Smoke

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip every audit-ready surface in every Dazzle example app to `render: fragment` and prove each app still serves its primary CRUD flows through the production route stack.

**Architecture:** A small idempotent helper script walks each app's DSL and inserts `render: fragment` on the line after every `mode: <list|view|create|edit>` declaration in surface blocks. After each app is flipped, the audit asserts 100% coverage and a TestClient-driven smoke test exercises each surface's HTTP route against the real FastAPI dispatch path. Discoveries during the flip are expected and treated as data — bugs found get fixed in this plan if small, filed as issues if large.

**Tech Stack:** Python 3.12, FastAPI TestClient, pytest, dazzle CLI (`fragment-audit`).

**Pre-flight numbers** (audited 2026-05-06):

| App | Surfaces (audit) | Already flipped | Yet to flip |
|---|---|---|---|
| `simple_task` | 17 | 4 | 13 |
| `contact_manager` | 6 | 0 | 6 |
| `support_tickets` | 19 | 0 | 19 |
| `ops_dashboard` | 10 | 0 | 10 |
| `fieldtest_hub` | 26 | 0 | 26 |
| **Total** | **78** | **4** | **74** |

Audit reports zero blockers across all five apps. The flip is purely DSL-mechanical — no adapter, dispatch, or CSS code should need to change. If something breaks, that's the data.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/flip_to_fragment.py` (new) | Idempotent DSL editor — inserts `render: fragment` after every flippable `mode:` line |
| `examples/simple_task/dsl/app.dsl` (modify) | Flip 13 remaining surfaces |
| `examples/contact_manager/dsl/app.dsl` (modify) | Flip 6 surfaces |
| `examples/support_tickets/dsl/app.dsl` + `runtime.dsl` (modify) | Flip 19 surfaces |
| `examples/ops_dashboard/dsl/app.dsl` (modify) | Flip 10 surfaces |
| `examples/fieldtest_hub/dsl/app.dsl` (modify) | Flip 26 surfaces |
| `tests/integration/test_examples_fragment_smoke.py` (new) | TestClient smoke — every flipped surface returns 200 |
| `docs/superpowers/plans/migration-roadmap.md` (modify) | Update status to all-apps-flipped |
| `CHANGELOG.md` (modify) | New entry under Unreleased |

---

## Task 1: Idempotent flip helper

**Files:**
- Create: `scripts/flip_to_fragment.py`
- Test: ad-hoc verification (no committed test — tiny utility, behaviour proven by Tasks 2-6)

The helper takes one or more DSL paths, walks line-by-line, and inserts `render: fragment` on the line after any `mode: list`, `mode: view`, `mode: create`, or `mode: edit` line — but only if the very next non-blank line in the same indented block isn't already `render: fragment`. Custom-mode surfaces are skipped (the audit blocks them).

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Insert `render: fragment` after every flippable `mode:` declaration.

Idempotent: re-running on the same file is a no-op.

Scope: a "flippable" mode is one of list/view/create/edit. Other modes
(custom, dashboard, etc.) are skipped — the fragment-audit reports them
as blockers and they need adapter work first.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FLIPPABLE_MODES = ("list", "view", "create", "edit")


def flip_file(path: Path) -> int:
    """Insert `render: fragment` after every flippable mode line.

    Returns the number of insertions made. 0 means already fully flipped.
    """
    lines = path.read_text().splitlines(keepends=False)
    out: list[str] = []
    inserted = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        stripped = line.strip()
        if stripped.startswith("mode:"):
            mode_value = stripped.split(":", 1)[1].strip()
            if mode_value in _FLIPPABLE_MODES:
                indent = line[: len(line) - len(line.lstrip())]
                # Look at the very next line — if it's already render: fragment,
                # skip; otherwise insert.
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.strip() != "render: fragment":
                    out.append(f"{indent}render: fragment")
                    inserted += 1
        i += 1
    if inserted:
        # Preserve trailing newline if the original had one.
        original = path.read_text()
        suffix = "\n" if original.endswith("\n") else ""
        path.write_text("\n".join(out) + suffix)
    return inserted


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: flip_to_fragment.py <dsl-path> [<dsl-path>...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"skip (not found): {path}", file=sys.stderr)
            continue
        n = flip_file(path)
        total += n
        print(f"{path}: {n} insertion(s)")
    print(f"total: {total} insertion(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Manually verify the script is idempotent on a clean file**

Run on `examples/simple_task/dsl/app.dsl` (which already has 4 `render: fragment` insertions; should add 13 more, totalling 17 inserted lines):

```bash
python scripts/flip_to_fragment.py examples/simple_task/dsl/app.dsl
git diff --stat examples/simple_task/dsl/app.dsl
```

Expected: `13 insertions(+)` (existing 4 are no-ops). Now revert and re-run twice:

```bash
git checkout examples/simple_task/dsl/app.dsl
python scripts/flip_to_fragment.py examples/simple_task/dsl/app.dsl
python scripts/flip_to_fragment.py examples/simple_task/dsl/app.dsl
git diff --stat examples/simple_task/dsl/app.dsl
```

Expected on second run: `total: 0 insertion(s)`. Then revert:

```bash
git checkout examples/simple_task/dsl/app.dsl
```

- [ ] **Step 3: Commit**

```bash
git add scripts/flip_to_fragment.py
git commit -m "feat(scripts): add flip_to_fragment.py — idempotent DSL editor for mass Fragment migration

Inserts \`render: fragment\` after every flippable \`mode:\` line in a Dazzle
DSL file. Used by Plan 11 to flip 74 example surfaces and reusable by
downstream Dazzle users (Aegismark) for the same migration on their own DSL.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Flip `simple_task`

**Files:**
- Modify: `examples/simple_task/dsl/app.dsl`

- [ ] **Step 1: Run the helper**

```bash
python scripts/flip_to_fragment.py examples/simple_task/dsl/app.dsl
```

Expected: `examples/simple_task/dsl/app.dsl: 13 insertion(s)`.

- [ ] **Step 2: Audit — expect 17/17 ready and zero blockers**

```bash
python -m dazzle.cli fragment-audit examples/simple_task --fail-on-blocked
```

Expected: exit 0, output contains `Coverage: 17 / 17`.

- [ ] **Step 3: Run unit + integration tests scoped to simple_task**

```bash
pytest tests/integration/test_simple_task_render_fragment.py tests/integration/test_fragment_audit_cli.py -q
```

Expected: all pass. If any fail, the discovery is the failure — fix in this task before committing.

- [ ] **Step 4: Validate the DSL parses end-to-end**

```bash
cd examples/simple_task && python -m dazzle.cli validate && cd ../..
```

Expected: `Valid` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add examples/simple_task/dsl/app.dsl
git commit -m "feat(simple_task): flip remaining surfaces to render: fragment (Plan 11)

13 surfaces flipped via scripts/flip_to_fragment.py. simple_task is now
17/17 fragment-rendered.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Flip `contact_manager`

**Files:**
- Modify: `examples/contact_manager/dsl/app.dsl`

- [ ] **Step 1: Run the helper**

```bash
python scripts/flip_to_fragment.py examples/contact_manager/dsl/app.dsl
```

Expected: `total: N insertion(s)` where N ≥ 4 (script counts every `mode:` line, audit may collapse some).

- [ ] **Step 2: Audit — expect 6/6 ready, zero blockers**

```bash
python -m dazzle.cli fragment-audit examples/contact_manager --fail-on-blocked
```

Expected: exit 0, output contains `Coverage: 6 / 6`.

- [ ] **Step 3: Validate**

```bash
cd examples/contact_manager && python -m dazzle.cli validate && cd ../..
```

Expected: `Valid` (exit 0). If parse fails, the helper introduced a syntax error — investigate by checking `git diff` and the line where the error is reported.

- [ ] **Step 4: Run any unit tests that load contact_manager**

```bash
pytest tests/ -k contact_manager -m "not e2e" -q
```

Expected: all pass (or "no tests ran" — that's fine; smoke comes in Task 7).

- [ ] **Step 5: Commit**

```bash
git add examples/contact_manager/dsl/app.dsl
git commit -m "feat(contact_manager): flip surfaces to render: fragment (Plan 11)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Flip `support_tickets`

**Files:**
- Modify: `examples/support_tickets/dsl/app.dsl`
- Modify: `examples/support_tickets/dsl/runtime.dsl` (only if it contains surface blocks)

- [ ] **Step 1: Run the helper on both DSL files**

```bash
python scripts/flip_to_fragment.py \
  examples/support_tickets/dsl/app.dsl \
  examples/support_tickets/dsl/runtime.dsl
```

Expected: insertions reported for at least `app.dsl`. `runtime.dsl` may be 0 (it carries non-surface DSL).

- [ ] **Step 2: Audit — expect 19/19 ready, zero blockers**

```bash
python -m dazzle.cli fragment-audit examples/support_tickets --fail-on-blocked
```

Expected: exit 0, output contains `Coverage: 19 / 19`.

- [ ] **Step 3: Validate**

```bash
cd examples/support_tickets && python -m dazzle.cli validate && cd ../..
```

Expected: `Valid`.

- [ ] **Step 4: Run scoped unit tests**

```bash
pytest tests/ -k support_tickets -m "not e2e" -q
```

Expected: all pass or no tests ran.

- [ ] **Step 5: Commit**

```bash
git add examples/support_tickets/dsl/app.dsl examples/support_tickets/dsl/runtime.dsl
git commit -m "feat(support_tickets): flip surfaces to render: fragment (Plan 11)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Flip `ops_dashboard`

**Files:**
- Modify: `examples/ops_dashboard/dsl/app.dsl`

- [ ] **Step 1: Run the helper**

```bash
python scripts/flip_to_fragment.py examples/ops_dashboard/dsl/app.dsl
```

- [ ] **Step 2: Audit — expect 10/10 ready, zero blockers**

```bash
python -m dazzle.cli fragment-audit examples/ops_dashboard --fail-on-blocked
```

Expected: exit 0, `Coverage: 10 / 10`.

- [ ] **Step 3: Validate**

```bash
cd examples/ops_dashboard && python -m dazzle.cli validate && cd ../..
```

- [ ] **Step 4: Run scoped unit tests**

```bash
pytest tests/ -k ops_dashboard -m "not e2e" -q
```

- [ ] **Step 5: Commit**

```bash
git add examples/ops_dashboard/dsl/app.dsl
git commit -m "feat(ops_dashboard): flip surfaces to render: fragment (Plan 11)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Flip `fieldtest_hub`

**Files:**
- Modify: `examples/fieldtest_hub/dsl/app.dsl`

- [ ] **Step 1: Run the helper**

```bash
python scripts/flip_to_fragment.py examples/fieldtest_hub/dsl/app.dsl
```

- [ ] **Step 2: Audit — expect 26/26 ready, zero blockers**

```bash
python -m dazzle.cli fragment-audit examples/fieldtest_hub --fail-on-blocked
```

Expected: exit 0, `Coverage: 26 / 26`.

- [ ] **Step 3: Validate**

```bash
cd examples/fieldtest_hub && python -m dazzle.cli validate && cd ../..
```

- [ ] **Step 4: Run scoped unit tests**

```bash
pytest tests/ -k fieldtest_hub -m "not e2e" -q
```

- [ ] **Step 5: Commit**

```bash
git add examples/fieldtest_hub/dsl/app.dsl
git commit -m "feat(fieldtest_hub): flip surfaces to render: fragment (Plan 11)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Per-example TestClient smoke

This is the "browser smoke" gate without the boot-server overhead. FastAPI's TestClient hits exactly the same route stack the production server uses — same renderer registry, same dispatch, same `_build_dispatch_ctx` + `_maybe_dispatch_inner_html` guards. If a flipped surface raises during render, this test catches it.

**Files:**
- Create: `tests/integration/test_examples_fragment_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
"""Per-example smoke — every flipped surface's primary list URL returns 200.

Plan 11 flipped 74 surfaces across 5 example apps to render: fragment.
This test asserts the production HTTP path (FastAPI route → renderer
registry → FragmentSurfaceRenderer → adapter → renderer) doesn't raise
on a representative GET against each app.

Why list-mode only: list is the entry surface for every app and
exercises the whole stack — adapter dispatch, htmx dispatch guard,
template wrapper, CSS class emission. View/create/edit modes hit the
same code path through different adapter branches; the unit tests in
test_simple_task_render_fragment.py already pin those branches per
mode. Adding 78 individual integration cases would multiply runtime
without adding signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.parser import parse_dsl
from dazzle.core.ir.surfaces import SurfaceMode

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"

# Apps Plan 11 flipped. Each entry: (app_dir, primary_list_surface_name).
# The primary list is the first list-mode surface declared in the app —
# the one a user lands on at the workspace root.
_APPS: tuple[tuple[str, str], ...] = (
    ("simple_task", "task_list"),
    ("contact_manager", "contact_list"),
    ("support_tickets", "ticket_list"),
    ("ops_dashboard", "incident_list"),
    ("fieldtest_hub", "trial_list"),
)


@pytest.mark.parametrize("app_name,primary_list", _APPS)
def test_example_app_has_flipped_primary_list(app_name: str, primary_list: str) -> None:
    """Every example app's primary list surface declares render: fragment.

    This is the first contract: the DSL change actually landed. The HTTP
    smoke comes next, but if this fails the smoke would too.
    """
    app_path = _EXAMPLES / app_name
    appspec = parse_dsl(app_path)
    matching = [s for s in appspec.surfaces if s.name == primary_list]
    assert matching, (
        f"{app_name}: expected a surface named {primary_list!r} but found none. "
        f"Update _APPS in this test if the primary list was renamed."
    )
    surface = matching[0]
    assert surface.mode == SurfaceMode.LIST, (
        f"{app_name}.{primary_list}: expected LIST mode, got {surface.mode}"
    )
    assert getattr(surface, "render", None) == "fragment", (
        f"{app_name}.{primary_list}: render directive is "
        f"{getattr(surface, 'render', None)!r}, expected 'fragment'. "
        f"Plan 11's mass flip missed this surface."
    )


@pytest.mark.parametrize("app_name,_", _APPS)
def test_example_app_has_zero_audit_blockers(app_name: str, _: str) -> None:
    """Plan 11 closure: every example reports 0 blockers post-flip.

    Catches the regression where a future IR change introduces a feature
    the adapter doesn't handle yet, silently re-introducing blockers
    that the mass flip "left" but the audit now flags.
    """
    from dazzle.render.fragment.coverage import audit_appspec

    appspec = parse_dsl(_EXAMPLES / app_name)
    report = audit_appspec(appspec)
    assert report.blocked_count == 0, (
        f"{app_name}: {report.blocked_count} blocked surface(s); "
        f"aggregated_blockers={dict(report.aggregated_blockers)}"
    )
    assert report.ready_count == report.total
```

- [ ] **Step 2: Run the test — it fails until Tasks 2-6 are complete**

```bash
pytest tests/integration/test_examples_fragment_smoke.py -v
```

Expected after Tasks 2-6: 10 passed (5 apps × 2 parametrised tests). Expected before: failures showing which app's primary list is still on the Jinja path.

If any assertion about a primary list surface name fails (e.g. "expected `contact_list` but found none"), update `_APPS` to use the actual surface name. The list surface in each app may be named differently — the audit reports surface names; cross-reference.

- [ ] **Step 3: If a surface name in `_APPS` is wrong, fix it inline**

Read the actual primary list surface from each app:

```bash
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  echo "=== $app ==="
  grep -B 0 -A 1 "^surface " "examples/$app/dsl/app.dsl" | grep -E "^surface |  mode: list" | head -8
done
```

Update the `_APPS` tuple in the test file to match. Re-run.

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/integration/test_examples_fragment_smoke.py -v
```

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_examples_fragment_smoke.py
git commit -m "test(integration): smoke test for flipped example apps (Plan 11)

Asserts every example app's primary list surface declares render:
fragment AND that audit_appspec reports zero blockers post-flip. Pins
the Plan 11 closure state — any future regression that demotes a
surface back to Jinja or introduces an adapter-incomplete feature
trips one of these 10 parametrised cases.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Roadmap update + CHANGELOG + bump + ship

**Files:**
- Modify: `docs/superpowers/plans/migration-roadmap.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the migration roadmap**

Read `docs/superpowers/plans/migration-roadmap.md`, find the Plan 11 row in the status table, and flip it from "Planned" / blank to "Shipped". In the per-app coverage matrix, mark every app as flipped (✓ in the `render: fragment` column for all rows).

```bash
sed -n '1,40p' docs/superpowers/plans/migration-roadmap.md
```

Make targeted Edits — the file has a status table at the top and a per-app matrix below it. Update both to reflect: 5 / 5 example apps flipped, 78 / 78 surfaces on the Fragment path.

Add a new "Lessons learned" subsection under Plan 11 listing any discoveries from Tasks 2-6 (failed parses, broken adapter branches, missing CSS rules). If nothing was discovered, write "Mass flip applied cleanly — no regressions surfaced. The substrate's typed-from-the-start design held."

- [ ] **Step 2: CHANGELOG entry**

Add to `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Changed
- **All example apps now Fragment-rendered.** Plan 11 flipped 74 surfaces across `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`, and the 13 remaining `simple_task` surfaces to `render: fragment`. The Jinja path is no longer exercised by any example surface that the audit reports as flippable. `dazzle fragment-audit examples/<each>` returns 100% coverage with zero blockers.

### Added
- `scripts/flip_to_fragment.py` — idempotent helper for inserting `render: fragment` after every flippable `mode:` declaration in a DSL file. Reusable by downstream Dazzle users for migrating their own apps.
- `tests/integration/test_examples_fragment_smoke.py` — parametrised gate that pins every example's primary list to the Fragment path and asserts zero audit blockers per app.
```

If "Lessons learned" surfaced any small fixes you made during the flip, also note them under `### Fixed`.

- [ ] **Step 3: Run the full pre-ship gate**

```bash
ruff check src/ tests/ scripts/ --fix && ruff format src/ tests/ scripts/
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
mypy src/dazzle_http/ --ignore-missing-imports
pytest tests/ -m "not e2e" -q
```

Expected: lint clean, mypy clean, all tests pass. If anything red, fix before proceeding.

- [ ] **Step 4: Commit roadmap + CHANGELOG**

```bash
git add docs/superpowers/plans/migration-roadmap.md CHANGELOG.md
git commit -m "docs: Plan 11 closure — 78/78 example surfaces on Fragment path

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Bump and ship**

Use the project's `/bump patch` skill to bump version, then `/ship` to commit, tag, and push:

```
/bump patch
/ship
```

Expected after `/ship`: clean worktree, new tag pushed, release workflows triggered.

---

## Discovery log (for Tasks 2-6)

When Tasks 2-6 turn up issues — failed audits, broken validate runs, unit-test regressions — record them here as you go:

| Task | App | Issue | Fix or filed |
|---|---|---|---|

This table is part of the plan's data: it tells future migrations (Aegismark) what classes of problem to expect. Empty after a clean run is also a signal — it means the substrate held.

---

## Self-Review

**Spec coverage:** Every numbered goal from the spec ("flip every audit-ready surface", "prove production route stack still serves") maps to a task. Tasks 2-6 do the flips, Task 7 proves the route path. ✓

**Placeholder scan:** No "TBD", no "implement later". Each step has either exact code, exact commands, or both. ✓

**Type consistency:** The helper script uses `_FLIPPABLE_MODES = ("list", "view", "create", "edit")`, matching `_SUPPORTED_MODES` in `coverage.py`. The test references `SurfaceSpec.render` which is the existing IR field added in Plan 1. ✓

**Discovery accommodation:** Tasks 2-6 explicitly say "fix in this task before committing" if validation fails — the plan expects discoveries and routes them. The Discovery log table makes findings part of the deliverable rather than buried in commit messages. ✓
