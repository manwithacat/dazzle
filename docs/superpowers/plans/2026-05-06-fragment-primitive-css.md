# Fragment Primitive CSS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Style the CSS classes the Fragment renderer emits so `simple_task.task_list` (and any other surface flipped to `render: fragment` thereafter) renders with the same visual chrome as the equivalent Jinja path. Closes the "Known limitation" carry-forward from Plan 3.

**Architecture:** A new dedicated component CSS file `components/fragment-primitives.css` houses the styling for every primitive the Fragment renderer emits. Rules use the same design tokens (`--colour-*`, `--space-*`, `--radius-*`, etc.) as the existing Jinja-path components, so visual parity is structural — not duplication. Registered into the dist-build pipeline and tested via a CSS-presence test that asserts each Fragment-emitted class has a matching rule.

**Tech Stack:** Standard CSS with cascade layers (`@layer components`), CSS custom properties (design tokens), the existing `scripts/build_dist.py` bundler.

**Reference:** carry-forward #1 from Plan 3's final code review (`docs/superpowers/plans/2026-05-06-typed-fragment-first-conversion.md`). Plan 3's CHANGELOG entry under `### Known limitations` is the issue this plan closes.

**Out of scope:** styling primitives that no flipped surface uses yet (Drawer, Modal, Tabs, KanbanBoard, CalendarGrid, Timeline, BarChart, PivotTable, KPI, FormStack, Field, Combobox, Submit, Skeleton, EmptyState's full visual treatment, Interactive). Those land in Plan 5+ as additional surfaces flip. This plan covers exactly what `simple_task.task_list` needs to look right: Surface, Heading, Region (kind=list), Text, Table.

---

## Phase-4 stop condition

> **simple_task.task_list, when rendered via Fragment, displays the same visual chrome as the Jinja path** — surface header with title, list region body with a styled table, consistent typography and spacing. Verified by (a) CSS-presence test asserting each Fragment-emitted class is styled, (b) manual browser comparison against the Jinja baseline.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` | Create | All CSS rules for Fragment renderer output |
| `scripts/build_dist.py` | Modify | Register `fragment-primitives.css` in the bundle order |
| `tests/unit/test_fragment_primitive_css.py` | Create | Asserts each Fragment-emitted class has a CSS rule somewhere in the bundled stylesheet |
| `CHANGELOG.md` | Modify | Remove the "Known limitation" warning, add an "Added" entry |

4 files. Smallest plan in the typed-Fragment series.

---

## Conventions

- **CSS:** wrap rules in `@layer components`. Use design tokens from `tokens.css` and `design-system.css` (e.g. `var(--colour-surface)`, `var(--space-md)`) — never hardcoded colours/spaces.
- **Test command:** `pytest tests/unit/test_fragment_primitive_css.py -v`
- **Build command:** `python scripts/build_dist.py`
- **Lint:** the existing CSS doesn't run through a linter; keep formatting consistent with `regions.css` / `table.css` (4-space indent, lowercase hex, sorted properties where reasonable).
- **Commit messages:** `feat(ui): <subject>` for new CSS; `chore(build): <subject>` for build-script changes; `test(ui): <subject>` for tests.

---

## Task 1: Create the CSS-presence test

Test-first — write the test that asserts each Fragment-emitted class has a matching CSS rule, then add the rules until the test passes. This is the inverse of the usual TDD direction (the production code already exists from Plan 1; we're adding *styling* for it now), so the test asserts presence rather than behaviour.

**Files:**
- Create: `tests/unit/test_fragment_primitive_css.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fragment_primitive_css.py
"""CSS coverage test for Fragment renderer primitives.

Every CSS class the Fragment renderer emits MUST have a matching rule
in the bundled stylesheet. New primitive styling lives in
`src/dazzle_page/runtime/static/css/components/fragment-primitives.css`.

This is a presence test, not a styling-correctness test. Visual
correctness is verified manually in a browser; this test catches the
case where a primitive emits a class that has zero rules.
"""

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CSS_DIR = _REPO_ROOT / "src" / "dazzle_page" / "runtime" / "static" / "css"


# Classes the Fragment renderer emits for surfaces simple_task.task_list
# uses (Plan 4 scope). When more surfaces flip in Plan 5+, append here.
_REQUIRED_CLASSES: tuple[str, ...] = (
    # Surface (container with header/body/footer slots)
    "dz-surface",
    "dz-surface__header",
    "dz-surface__body",
    # Heading (level-1 used by Surface header)
    "dz-heading",
    "dz-heading--level-1",
    # Region (kind=list for task_list)
    "dz-region",
    "dz-region--kind-list",
    # Text (default tone — used inside table cells / empty state)
    "dz-text",
    "dz-text--tone-default",
    # Table — Plan 4 scope is "the Fragment Table primitive in a list region"
    # The table.css file already has a basic .dz-table rule. We add list-
    # context cascade in fragment-primitives.css.
    "dz-table",
)


def _bundled_css_text() -> str:
    """Read every CSS file in the components/ tree + tokens/design-system."""
    parts: list[str] = []
    for path in sorted(_CSS_DIR.rglob("*.css")):
        parts.append(path.read_text())
    return "\n".join(parts)


@pytest.mark.parametrize("css_class", _REQUIRED_CLASSES)
def test_fragment_emitted_class_has_a_css_rule(css_class: str) -> None:
    """Each class in _REQUIRED_CLASSES must appear as a selector somewhere
    in the bundled CSS source files. The bundle script (`build_dist.py`)
    concatenates these, so source-presence equals bundle-presence."""
    css = _bundled_css_text()
    # Match `.<class>` followed by a non-name char (`{`, ` `, `,`, `:`, `>`).
    # This catches both standalone selectors and compound ones like
    # `.dz-region--kind-list .dz-table`.
    pattern = re.compile(rf"\.{re.escape(css_class)}(?=[\s,{{:>~+\.\[])")
    matches = pattern.findall(css)
    assert matches, (
        f"CSS class {css_class!r} is emitted by the Fragment renderer "
        f"but has no rule in any source CSS file under {_CSS_DIR}. "
        f"Add a rule in components/fragment-primitives.css."
    )
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: FAIL on most classes (`dz-surface__header`, `dz-surface__body`, `dz-heading--level-1`, `dz-region--kind-list`, `dz-text--tone-default`, etc.) — they exist nowhere in the source CSS.

`dz-surface` may already pass (mentioned in 2 files), and `dz-table` will pass (in table.css). All others should fail.

- [ ] **Step 3: Commit the test**

```bash
git add tests/unit/test_fragment_primitive_css.py
git commit -m "test(ui): CSS-presence test for Fragment-emitted classes"
```

This commits a failing test deliberately — Tasks 2-4 add the CSS to make it pass.

---

## Task 2: Create fragment-primitives.css with the required rules

Add CSS rules for every class the test in Task 1 requires. Use design tokens (`var(--colour-*)`, `var(--space-*)`, `var(--radius-*)`) consistently.

**Files:**
- Create: `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`

- [ ] **Step 1: Read existing tokens to use the right names**

```bash
grep -E "^\s*--colour-|--space-|--radius-|--text-" src/dazzle_page/runtime/static/css/tokens.css | head -30
```

Identify the canonical token names (e.g. `--colour-surface`, `--colour-text`, `--space-md`, `--radius-md`). Use the ones that the Jinja-path components already use — see `regions.css`, `table.css`, `detail.css` for examples.

- [ ] **Step 2: Write the CSS file**

Create `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` with this content:

```css
/*
 * fragment-primitives.css — visual chrome for typed Fragment renderer output.
 *
 * The Fragment renderer (src/dazzle/render/fragment/renderer.py) emits a
 * deterministic class vocabulary derived from the typed primitive types.
 * Each class needs a matching rule here so flipped surfaces (those with
 * `render: fragment` in DSL) render with the same visual treatment as
 * their Jinja-path equivalents.
 *
 * Rules use the framework's design tokens — never hardcoded colours,
 * spaces, or radii — so theme overrides and token-sheet swaps cascade
 * automatically.
 *
 * Plan 4 scope: simple_task.task_list (Surface + Heading + Region.list +
 * Text + Table). Plan 5+ extends as more surfaces flip.
 */

@layer components {

  /* ───────────────────────── Surface ─────────────────────────
   * Top-level rendered surface — the typed Fragment equivalent of
   * a workspace's main page or a list/detail page wrapper.
   * Slots: header (titles), body (content), footer (optional).
   */

  .dz-surface {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
    padding: var(--space-md);
    background: var(--colour-surface);
    color: var(--colour-text);
  }

  .dz-surface__header {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    padding-block-end: var(--space-sm);
    border-block-end: 1px solid var(--colour-border-subtle);
  }

  .dz-surface__body {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
  }

  .dz-surface__footer {
    padding-block-start: var(--space-sm);
    border-block-start: 1px solid var(--colour-border-subtle);
  }

  /* ───────────────────────── Heading ─────────────────────────
   * Level-parameterised heading. Level 1 is the page-title weight;
   * 2-3 are section headings; 4-6 are sub-headings used inside
   * regions and panels. Sizing pulls from the same scale as
   * design-system.css's .dz-heading variants for the Jinja path.
   */

  .dz-heading {
    margin: 0;
    color: var(--colour-text);
    font-weight: var(--weight-semibold);
    line-height: 1.25;
  }

  .dz-heading--level-1 { font-size: var(--text-xl); }
  .dz-heading--level-2 { font-size: var(--text-lg); }
  .dz-heading--level-3 { font-size: var(--text-md); }
  .dz-heading--level-4 { font-size: var(--text-sm); font-weight: var(--weight-medium); }
  .dz-heading--level-5 { font-size: var(--text-sm); font-weight: var(--weight-medium); color: var(--colour-text-muted); }
  .dz-heading--level-6 { font-size: var(--text-xs); font-weight: var(--weight-medium); color: var(--colour-text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

  /* ───────────────────────── Region ──────────────────────────
   * A semantic content region inside a Surface. The `kind`
   * modifier drives the layout: list (table-shaped), detail
   * (definition-list-shaped), form (FormStack), dashboard
   * (Grid), kanban, calendar, report.
   *
   * Plan 4 scope: list only. Other kinds get base treatment but
   * no kind-specific styling until later plans.
   */

  .dz-region {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .dz-region--kind-list {
    /* List-mode region wraps a Table primitive. The table itself
       inherits its core styling from table.css; this rule provides
       the list-context spacing and any list-specific cascade
       (e.g. dz-table inside .dz-region--kind-list gets the same
       row-hover treatment as the Jinja .dz-list-table path). */
    overflow-x: auto;
  }

  .dz-region--kind-list > .dz-table {
    width: 100%;
    border-collapse: collapse;
    background: var(--colour-surface);
  }

  .dz-region--kind-list > .dz-table thead > tr {
    border-block-end: 1px solid var(--colour-border);
    text-align: left;
  }

  .dz-region--kind-list > .dz-table th {
    padding: var(--space-sm) var(--space-md);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    color: var(--colour-text-muted);
  }

  .dz-region--kind-list > .dz-table > tbody > tr {
    border-block-end: 1px solid var(--colour-border-subtle);
    transition: background-color 0.12s ease;
  }

  .dz-region--kind-list > .dz-table > tbody > tr:last-child {
    border-block-end: none;
  }

  .dz-region--kind-list > .dz-table > tbody > tr:hover {
    background: var(--colour-surface-hover);
  }

  .dz-region--kind-list > .dz-table td {
    padding: var(--space-sm) var(--space-md);
    color: var(--colour-text);
  }

  /* ───────────────────────── Text ────────────────────────────
   * Inline text primitive — used inside cells, in EmptyState
   * descriptions, badges, and as a bare leaf primitive. The tone
   * modifier controls colour role (default/muted/danger/success/
   * warning); other tones map to existing token roles.
   */

  .dz-text {
    color: var(--colour-text);
  }

  .dz-text--tone-default { color: var(--colour-text); }
  .dz-text--tone-muted   { color: var(--colour-text-muted); }
  .dz-text--tone-danger  { color: var(--colour-danger); }
  .dz-text--tone-success { color: var(--colour-success); }
  .dz-text--tone-warning { color: var(--colour-warning); }

}  /* @layer components */
```

If any token name doesn't exist (e.g. `--colour-surface-hover`), check `tokens.css` for the actual name and substitute. Don't introduce new tokens — use what exists. If a needed value genuinely isn't tokenised yet, fall back to a reasonable default (e.g. `rgba(0,0,0,0.04)` for hover background) and note it in a comment.

- [ ] **Step 3: Verify the test now passes for the classes you styled**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: PASS for every parametrised case. If any case still fails, the corresponding class isn't in the file you just wrote — add it.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/static/css/components/fragment-primitives.css
git commit -m "feat(ui): CSS for Fragment renderer primitives (Surface, Heading, Region, Text, Table)"
```

---

## Task 3: Register the CSS file in the dist build

The new `fragment-primitives.css` needs to be picked up by `scripts/build_dist.py` so it's included in `dist/dazzle.min.css`. Without this step, the source rules exist but the bundled CSS doesn't include them.

**Files:**
- Modify: `scripts/build_dist.py`

- [ ] **Step 1: Locate the CSS source list**

```bash
grep -n "components.*\.css\b" scripts/build_dist.py | head -20
```

Find the list of `(layer_name, path)` tuples that drives bundling. The list around lines 37-50 has entries like `("components", STATIC / "css" / "components" / "fragments.css")`.

- [ ] **Step 2: Insert the new entry**

In `scripts/build_dist.py`, find the components block. Add this entry — keep the position alphabetical (after `fragments.css`, before `regions.css`):

```python
    ("components", STATIC / "css" / "components" / "fragment-primitives.css"),
```

- [ ] **Step 3: Rebuild the dist**

```bash
python scripts/build_dist.py 2>&1 | tail -10
```

Expected: success message. The dist files (`src/dazzle_page/runtime/static/dist/dazzle.min.css`) are regenerated. Confirm via grep:

```bash
grep -c "dz-surface__header\|dz-heading--level-1\|dz-region--kind-list" src/dazzle_page/runtime/static/dist/dazzle.min.css
```

Expected: `>= 3` (at least one match per class).

- [ ] **Step 4: Commit**

```bash
git add scripts/build_dist.py src/dazzle_page/runtime/static/dist/
git commit -m "chore(build): register fragment-primitives.css + rebuild dist bundle"
```

---

## Task 4: Browser smoke + CHANGELOG cleanup

The visual verification step. Boot `simple_task` and confirm `task_list` renders correctly.

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Boot simple_task and inspect**

```bash
cd examples/simple_task && timeout 25 dazzle serve --local 2>&1 | head -20 &
SERVE_PID=$!
sleep 15
curl -sS -o /tmp/p4_smoke.html -w "status=%{http_code}\n" http://localhost:3000/app/surfaces/task_list 2>&1 | tail -3
head -200 /tmp/p4_smoke.html 2>/dev/null
kill $SERVE_PID 2>/dev/null
cd -
```

Expected: status=200, response contains `dz-surface`, `dz-heading--level-1`, `dz-region--kind-list`, `dz-table`. The HTML structure should look like the Fragment-rendered output from Plan 3.

If you can open a browser at `http://localhost:3000/app/surfaces/task_list` (i.e. on a dev machine), visually compare against the equivalent Jinja-rendered surface in another Dazzle example app. The two should look broadly equivalent — same typography weight, same row spacing, same border treatment, same background.

If the boot smoke fails (database, port, etc.), skip to step 2 — the CSS-presence test plus the dist regeneration are sufficient evidence. Note in the commit message that the visual smoke wasn't run.

- [ ] **Step 2: Update CHANGELOG**

In `CHANGELOG.md`, find the `### Known limitations` section under `## [Unreleased]` (added in Plan 3). Remove the bullet about Fragment-rendered surfaces being unstyled. If that's the only bullet under `### Known limitations`, remove the heading too.

Then add to the `### Added` section under the same `## [Unreleased]`:

```markdown
- **Fragment-rendered surfaces are now styled.** New
  `components/fragment-primitives.css` provides CSS rules for every class
  the Fragment renderer emits for `simple_task.task_list` (Surface,
  Heading, Region.kind=list, Text, Table). Surfaces flipped to
  `render: fragment` now display with the same visual chrome as the
  Jinja path. CSS-presence test in `tests/unit/test_fragment_primitive_css.py`
  pins the coverage; new primitives that get flipped in later plans must
  add to both the CSS file and the test's `_REQUIRED_CLASSES` tuple.
```

- [ ] **Step 3: Run the full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: all pass. The new CSS-presence test is included.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): close 'Fragment unstyled' limitation; note new CSS"
```

---

## Plan completion checklist

After Task 4:

- [ ] `pytest tests/unit/test_fragment_primitive_css.py -v` — all parametrised cases pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `python scripts/build_dist.py` produces dist files containing the new CSS rules.
- [ ] `git status` clean.
- [ ] **Phase-4 stop condition met:** simple_task.task_list renders with proper visual chrome (verified via HTML response containing the expected classes; visual confirmation in a browser is recommended but not strictly required).

---

## Self-Review

**Spec coverage:**
- The carry-forward from Plan 3 ("Fragment-rendered surfaces produce structurally-correct HTML but the framework CSS does not yet style the dz-surface/dz-heading--level-N/dz-region--kind-X classes") is fully addressed by Task 2 (CSS rules) + Task 3 (bundle registration) + Task 4 (CHANGELOG cleanup).
- The CSS-presence test in Task 1 prevents regression — adding a new Fragment primitive without CSS becomes a test failure.

**Placeholder scan:**
- All file paths exact.
- Every CSS rule body is concrete; design tokens are named via `var(--*)` not "TBD".
- The "if any token name doesn't exist" hedge in Task 2 step 2 explicitly says to substitute — no actual placeholder.

**Type consistency:**
- `_REQUIRED_CLASSES` tuple in Task 1 lists exactly the classes Task 2 styles.
- `fragment-primitives.css` is the file referenced consistently in Tasks 2, 3, and the test in Task 1 (via `_CSS_DIR.rglob`).

**Scope check:**
- Plan covers exactly the CSS gap from Plan 3's review. Out-of-scope primitives (Drawer, Modal, Tabs, Kanban, etc.) are explicitly listed in the plan header. Plan 5+ extends.
- 4 tasks. Smaller than Plans 1-3 because the work is mostly content (CSS rules), not architecture.
