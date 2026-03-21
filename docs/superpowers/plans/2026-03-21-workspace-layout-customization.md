# Workspace Layout Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add drag-to-reorder, show/hide, and snap-resize to workspace dashboard regions with persistent per-user layout preferences.

**Architecture:** Server-side preference merge in `workspace_renderer.py` transforms DSL-default region order/sizing before rendering. Client-side Alpine.js component manages edit mode UI; SortableJS (via alpine-sort plugin) handles drag-and-drop. Layout state persists via the existing `dzPrefs`/`user_preferences` system.

**Tech Stack:** Alpine.js, alpine-sort, SortableJS (vendored), Tailwind 12-column grid, existing `dzPrefs` JS API + `PUT /auth/preferences` endpoint.

**Spec:** `docs/superpowers/specs/2026-03-21-workspace-layout-customization-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/dazzle_ui/runtime/workspace_renderer.py` | Modify | Add `col_span` field, remove `grid_class`, add `apply_layout_preferences()`, update `build_workspace_context()` |
| `src/dazzle_ui/templates/workspace/_content.html` | Modify | Alpine `x-data` wrapper, 12-col grid, edit mode UI, floating toolbar |
| `src/dazzle_ui/runtime/static/js/workspace-editor.js` | Create | `dzWorkspaceEditor` Alpine component |
| `src/dazzle_ui/runtime/static/vendor/alpine.min.js` | Create | Vendored Alpine.js |
| `src/dazzle_ui/runtime/static/vendor/sortable.min.js` | Create | Vendored SortableJS |
| `src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js` | Create | Vendored alpine-sort plugin |
| `src/dazzle_ui/templates/base.html` | Modify | Add Alpine.js + plugin script tags |
| `tests/unit/test_workspace_layout_prefs.py` | Create | Unit tests for merge logic, col_span defaults, round-trip |

---

### Task 1: Add `col_span` to RegionContext and compute defaults from stage

**Files:**
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py:47-79` (RegionContext model)
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py:82-96` (WorkspaceContext model)
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py:102-145` (stage maps)
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py:200-216` (build_workspace_context grid_class assignment)
- Test: `tests/unit/test_workspace_layout_prefs.py`

- [ ] **Step 1: Write failing tests for col_span defaults**

Create `tests/unit/test_workspace_layout_prefs.py`:

```python
"""Tests for workspace layout preferences and col_span grid system."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_if_missing() -> None:
    pytest.importorskip("pydantic")


class TestColSpanDefaults:
    """Each stage assigns correct default col_span values."""

    def test_focus_metric_first_region_full_width(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("focus_metric", region_count=3)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 12
        assert ctx.regions[1].col_span == 6
        assert ctx.regions[2].col_span == 6

    def test_dual_pane_flow_all_half(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("dual_pane_flow", region_count=2)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 6
        assert ctx.regions[1].col_span == 6

    def test_scanner_table_all_full(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=2)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 12
        assert ctx.regions[1].col_span == 12

    def test_monitor_wall_all_half(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("monitor_wall", region_count=4)
        ctx = build_workspace_context(ws)
        for r in ctx.regions:
            assert r.col_span == 6

    def test_command_center_cycle(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("command_center", region_count=6)
        ctx = build_workspace_context(ws)
        spans = [r.col_span for r in ctx.regions]
        assert spans == [12, 6, 6, 4, 4, 4]

    def test_no_stage_defaults_to_12(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("", region_count=2)
        ctx = build_workspace_context(ws)
        for r in ctx.regions:
            assert r.col_span == 12

    def test_grid_class_removed_from_region(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        r = RegionContext(name="test")
        assert not hasattr(r, "grid_class")


def _make_workspace(stage: str, region_count: int = 3) -> object:
    """Build a minimal WorkspaceSpec-like object for testing."""
    from types import SimpleNamespace

    regions = []
    for i in range(region_count):
        regions.append(
            SimpleNamespace(
                name=f"region_{i}",
                source=f"Entity{i}",
                sources=[],
                display="LIST",
                filter=None,
                sort=[],
                limit=None,
                action=None,
                group_by=None,
                aggregates={},
                date_field=None,
                date_range=False,
                heatmap_rows=None,
                heatmap_columns=None,
                heatmap_value=None,
                heatmap_thresholds=None,
                progress_stages=None,
                progress_complete_at=None,
            )
        )
    return SimpleNamespace(
        name="test_workspace",
        title="Test Workspace",
        purpose="",
        stage=stage,
        regions=regions,
        nav_groups=[],
        context_selector=None,
        sse_url="",
        fold_count=None,
        access=None,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_workspace_layout_prefs.py -v`
Expected: FAIL — `grid_class` still exists on RegionContext, `col_span` does not exist.

- [ ] **Step 3: Update RegionContext — add `col_span`, `hidden`; remove `grid_class`**

In `src/dazzle_ui/runtime/workspace_renderer.py`, modify `RegionContext` (line 47):

Remove the `grid_class: str = ""` field (line 78). Add:

```python
    col_span: int = 12  # Resolved column span (4, 6, 8, or 12)
    hidden: bool = False  # User has hidden this region
```

In `WorkspaceContext` (line 82), remove `grid_class: str = "grid grid-cols-1 gap-4"` (line 89).

Replace `STAGE_GRID_MAP` dict (lines 102-108) and `COMMAND_CENTER_SPANS` list (lines 138-145) with a new stage-to-col-span mapping:

```python
# Stage → default col_span per region position
STAGE_DEFAULT_SPANS: dict[str, list[int] | int] = {
    "focus_metric": [12, 6],        # first = 12, rest = 6
    "dual_pane_flow": 6,            # all = 6
    "scanner_table": 12,            # all = 12
    "monitor_wall": 6,              # all = 6
    "command_center": [12, 6, 6, 4, 4, 4],  # cycle
}


def _default_col_span(stage: str, index: int) -> int:
    """Compute the default col_span for a region at the given index in a stage."""
    pattern = STAGE_DEFAULT_SPANS.get(stage)
    if pattern is None:
        return 12
    if isinstance(pattern, int):
        return pattern
    # List pattern: use index, clamped to last element
    return pattern[min(index, len(pattern) - 1)]
```

- [ ] **Step 4: Update `build_workspace_context()` to assign `col_span` instead of `grid_class`**

In `build_workspace_context()` around line 208-216, replace the `grid_class` assignment block:

```python
        # Before (remove this block):
        region_grid = ""
        if stage == "command_center":
            ...
        elif stage == "focus_metric" and idx == 0:
            ...

        # After (add this):
        col_span = _default_col_span(stage, idx)
```

Then in the `RegionContext(...)` constructor call (around line 280), replace `grid_class=region_grid` with `col_span=col_span`.

Also remove `grid_class=grid_class` from the `WorkspaceContext(...)` constructor call (around line 310).

- [ ] **Step 5: Fix any callers of `grid_class` across the codebase**

Search for `grid_class` usage and update all references. Key files:
- `src/dazzle_ui/templates/workspace/_content.html` (lines 52, 58, 62) — update in Task 5
- Any test files referencing `grid_class` — update assertions

Run: `grep -rn "grid_class" src/ tests/ --include="*.py" | grep -v __pycache__`

Fix each reference.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_workspace_layout_prefs.py -v`
Expected: All 7 tests PASS.

Run: `pytest tests/ -m "not e2e" -x -q` to check for regressions.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_ui/runtime/workspace_renderer.py tests/unit/test_workspace_layout_prefs.py
git commit -m "refactor: replace grid_class with col_span on RegionContext, stage-based defaults"
```

---

### Task 2: Implement `apply_layout_preferences()` merge logic

**Files:**
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py`
- Test: `tests/unit/test_workspace_layout_prefs.py`

- [ ] **Step 1: Write failing tests for merge logic**

Add to `tests/unit/test_workspace_layout_prefs.py`:

```python
class TestApplyLayoutPreferences:
    """Merge user layout preferences with DSL defaults."""

    def test_no_preference_returns_unchanged(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("focus_metric", region_count=3)
        ctx = build_workspace_context(ws)
        original_order = [r.name for r in ctx.regions]

        result = apply_layout_preferences(ctx, {})
        assert [r.name for r in result.regions] == original_order

    def test_reorder_regions(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=3)
        ctx = build_workspace_context(ws)

        prefs = {"workspace.test_workspace.layout": '{"order": ["region_2", "region_0", "region_1"], "hidden": [], "widths": {}}'}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_2", "region_0", "region_1"]

    def test_hidden_regions_flagged(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=3)
        ctx = build_workspace_context(ws)

        prefs = {"workspace.test_workspace.layout": '{"order": ["region_0", "region_1", "region_2"], "hidden": ["region_1"], "widths": {}}'}
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[1].hidden is True
        assert result.regions[0].hidden is False

    def test_width_overrides(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=2)
        ctx = build_workspace_context(ws)

        prefs = {"workspace.test_workspace.layout": '{"order": ["region_0", "region_1"], "hidden": [], "widths": {"region_0": 8, "region_1": 4}}'}
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[0].col_span == 8
        assert result.regions[1].col_span == 4

    def test_deleted_dsl_region_dropped(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=2)
        ctx = build_workspace_context(ws)

        prefs = {"workspace.test_workspace.layout": '{"order": ["region_0", "gone_region", "region_1"], "hidden": [], "widths": {}}'}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_0", "region_1"]

    def test_new_dsl_region_appended(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=3)
        ctx = build_workspace_context(ws)

        # Saved order only has 2 of the 3 regions
        prefs = {"workspace.test_workspace.layout": '{"order": ["region_1", "region_0"], "hidden": [], "widths": {}}'}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_1", "region_0", "region_2"]

    def test_fold_count_skips_hidden_regions(self) -> None:
        """Hidden regions should not count toward fold_count."""
        from dazzle_ui.runtime.workspace_renderer import (
            apply_layout_preferences,
            build_workspace_context,
        )

        ws = _make_workspace("focus_metric", region_count=4)
        ctx = build_workspace_context(ws)
        assert ctx.fold_count == 3  # focus_metric default

        # Hide region_0 — fold_count should still apply to 3 *visible* regions
        prefs = {"workspace.test_workspace.layout": '{"order": ["region_0", "region_1", "region_2", "region_3"], "hidden": ["region_0"], "widths": {}}'}
        result = apply_layout_preferences(ctx, prefs)

        visible = [r for r in result.regions if not r.hidden]
        assert len(visible) == 3
        # All 3 visible regions should be within fold_count
        assert result.fold_count == 3

    def test_round_trip_json(self) -> None:
        """Layout JSON serializes and deserializes correctly."""
        import json

        layout = {"order": ["a", "b"], "hidden": ["c"], "widths": {"a": 8}}
        serialized = json.dumps(layout)
        deserialized = json.loads(serialized)
        assert deserialized == layout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_workspace_layout_prefs.py::TestApplyLayoutPreferences -v`
Expected: FAIL — `apply_layout_preferences` does not exist.

- [ ] **Step 3: Implement `apply_layout_preferences()`**

Add to `src/dazzle_ui/runtime/workspace_renderer.py`:

```python
def apply_layout_preferences(
    ctx: WorkspaceContext,
    user_prefs: dict[str, str],
) -> WorkspaceContext:
    """Merge user layout preferences with DSL defaults.

    Reads ``workspace.{name}.layout`` from *user_prefs* and applies
    ordering, visibility, and width overrides.  Returns *ctx* unchanged
    if no preference exists.
    """
    import json

    pref_key = f"workspace.{ctx.name}.layout"
    raw = user_prefs.get(pref_key)
    if not raw:
        return ctx

    try:
        layout = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ctx

    saved_order: list[str] = layout.get("order", [])
    hidden_set: set[str] = set(layout.get("hidden", []))
    widths: dict[str, int] = layout.get("widths", {})

    # Deep-copy regions to avoid mutating the shared startup context (#587 pattern)
    region_map = {r.name: r.model_copy(deep=True) for r in ctx.regions}

    # Reorder: saved order first (skip deleted), then append new DSL regions
    ordered: list[RegionContext] = []
    seen: set[str] = set()
    for name in saved_order:
        if name in region_map:
            ordered.append(region_map[name])
            seen.add(name)
    for r in ctx.regions:
        if r.name not in seen:
            ordered.append(region_map[r.name])

    # Apply hidden flag and width overrides
    for r in ordered:
        if r.name in hidden_set:
            r.hidden = True
        if r.name in widths:
            span = widths[r.name]
            if span in (4, 6, 8, 12):
                r.col_span = span

    # Return a new context to avoid mutating the shared startup object
    return ctx.model_copy(update={"regions": ordered})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_workspace_layout_prefs.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_ui/runtime/workspace_renderer.py tests/unit/test_workspace_layout_prefs.py
git commit -m "feat: apply_layout_preferences merges user layout delta with DSL defaults"
```

---

### Task 3: Wire layout preferences into workspace page rendering

**Files:**
- Modify: `src/dazzle_ui/runtime/page_routes.py` (where workspace pages render)
- Modify: `src/dazzle_ui/templates/workspace/_content.html`

- [ ] **Step 1: Find where workspace pages are rendered per-request**

Run: `grep -n "build_workspace_context\|_workspace_handler\|workspace_page" src/dazzle_ui/runtime/page_routes.py`

**Important:** `build_workspace_context()` is called once at startup and the result is captured in a closure. `apply_layout_preferences()` must be called *per-request* inside the handler function (e.g. `_workspace_handler`) so that each user gets their own layout. This mirrors the `ctx.table.model_copy(deep=True)` pattern from #587.

- [ ] **Step 2: Call `apply_layout_preferences` per-request in the handler**

Inside the workspace page handler, after getting the auth context but before rendering:

```python
from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

# ws_ctx was built at startup — apply per-user layout preferences
user_prefs = auth_ctx.preferences if auth_ctx else {}
render_ws_ctx = apply_layout_preferences(ws_ctx, user_prefs)
```

Use `render_ws_ctx` (not `ws_ctx`) for rendering. The original `ws_ctx` is never mutated.

- [ ] **Step 3: Pass `layout_json` to the template context**

Build the layout state as JSON for Alpine initialization:

```python
import json

layout_json = json.dumps({
    "regions": [
        {"name": r.name, "title": r.title, "col_span": r.col_span, "hidden": r.hidden}
        for r in ws_ctx.regions
    ]
})
```

Pass `layout_json` to the template render call.

- [ ] **Step 4: Update `_content.html` — replace grid_class, use col_span**

Replace `{{ workspace.grid_class }}` (line 52) with `grid grid-cols-12 gap-4`.

Replace `{{ region.grid_class }}` (lines 58, 62) with `col-span-12 md:col-span-{{ region.col_span }}`.

Update the fold count logic (line 66) to skip hidden regions — count only visible regions for eager vs lazy loading.

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/ -m "not e2e" -x -q`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_ui/runtime/page_routes.py src/dazzle_ui/templates/workspace/_content.html
git commit -m "feat: wire layout preferences into workspace rendering, 12-col grid"
```

---

### Task 4: Vendor Alpine.js, SortableJS, and alpine-sort

**Files:**
- Create: `src/dazzle_ui/runtime/static/vendor/alpine.min.js`
- Create: `src/dazzle_ui/runtime/static/vendor/sortable.min.js`
- Create: `src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js`
- Modify: `src/dazzle_ui/templates/base.html`

- [ ] **Step 1: Download vendored libraries**

```bash
# Alpine.js (v3.x latest)
curl -sL https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js -o src/dazzle_ui/runtime/static/vendor/alpine.min.js

# SortableJS
curl -sL https://cdn.jsdelivr.net/npm/sortablejs@1/Sortable.min.js -o src/dazzle_ui/runtime/static/vendor/sortable.min.js

# alpine-sort (requires SortableJS)
curl -sL https://cdn.jsdelivr.net/npm/@alpinejs/sort@3/dist/cdn.min.js -o src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js
```

Verify each file downloaded correctly (check file size > 0, contains JS).

- [ ] **Step 2: Add script tags to `base.html`**

After the HTMX extension script tags (line 35) and before the dz.js block (line 36), add:

```html
  {# Alpine.js + plugins (v0.45.0) #}
  <script defer src="/static/vendor/sortable.min.js"></script>
  <script defer src="/static/vendor/alpine-sort.min.js"></script>
  <script defer src="/static/vendor/alpine.min.js"></script>
```

**Important:** Alpine.js must load LAST (after plugins). SortableJS must load before alpine-sort. All use `defer` for non-blocking loading.

- [ ] **Step 3: Verify Alpine loads correctly**

Start a dev server (`dazzle serve --local`) and check browser console for errors. Verify `window.Alpine` is defined.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/runtime/static/vendor/alpine.min.js \
        src/dazzle_ui/runtime/static/vendor/sortable.min.js \
        src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js \
        src/dazzle_ui/templates/base.html
git commit -m "feat: vendor Alpine.js, SortableJS, alpine-sort"
```

---

### Task 5: Build the Alpine workspace editor component

**Files:**
- Create: `src/dazzle_ui/runtime/static/js/workspace-editor.js`

- [ ] **Step 1: Write the `dzWorkspaceEditor` Alpine component**

Create `src/dazzle_ui/runtime/static/js/workspace-editor.js`:

```javascript
/**
 * workspace-editor.js — Alpine.js component for workspace layout customization.
 *
 * Manages edit mode: drag-to-reorder (via alpine-sort), show/hide toggle,
 * and col-span width snapping. Persists layout to user preferences via dzPrefs.
 */

document.addEventListener("alpine:init", () => {
  Alpine.data("dzWorkspaceEditor", (workspaceName, initialLayout) => ({
    editing: false,
    regions: JSON.parse(JSON.stringify(initialLayout.regions)),
    _snapshot: null,

    toggleEdit() {
      this._snapshot = JSON.parse(JSON.stringify(this.regions));
      this.editing = true;
    },

    onReorder(item, position) {
      // alpine-sort calls this after a drag completes
      const names = [];
      this.$el.querySelectorAll("[data-region-name]").forEach((el) => {
        names.push(el.dataset.regionName);
      });
      // Reorder our regions array to match DOM order
      const regionMap = {};
      this.regions.forEach((r) => { regionMap[r.name] = r; });
      this.regions = names.map((n) => regionMap[n]).filter(Boolean);
    },

    setWidth(regionName, span) {
      const region = this.regions.find((r) => r.name === regionName);
      if (region) region.col_span = span;
    },

    toggleVisibility(regionName) {
      const region = this.regions.find((r) => r.name === regionName);
      if (region) region.hidden = !region.hidden;
    },

    save() {
      const layout = {
        order: this.regions.map((r) => r.name),
        hidden: this.regions.filter((r) => r.hidden).map((r) => r.name),
        widths: {},
      };
      this.regions.forEach((r) => { layout.widths[r.name] = r.col_span; });
      const key = "workspace." + workspaceName + ".layout";
      // Save directly via fetch (not dzPrefs.set which is debounced and
      // would be cancelled by the immediate location.reload below).
      const prefs = {};
      prefs[key] = JSON.stringify(layout);
      fetch("/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: prefs }),
      }).then(() => {
        this.editing = false;
        location.reload();
      });
    },

    cancel() {
      this.regions = this._snapshot;
      this._snapshot = null;
      this.editing = false;
    },

    reset() {
      const key = "workspace." + workspaceName + ".layout";
      fetch("/auth/preferences/" + encodeURIComponent(key), {
        method: "DELETE",
      }).then(() => location.reload());
    },
  }));
});
```

- [ ] **Step 2: Add script tag to `base.html`**

After the dz.js script tags (around line 38-40):

```html
  <script defer src="/static/js/workspace-editor.js"></script>
```

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/workspace-editor.js src/dazzle_ui/templates/base.html
git commit -m "feat: dzWorkspaceEditor Alpine component for layout customization"
```

---

### Task 6: Build the edit mode template UI

**Files:**
- Modify: `src/dazzle_ui/templates/workspace/_content.html`

- [ ] **Step 1: Wrap workspace in Alpine `x-data` and add edit mode UI**

Rewrite `_content.html` to add the Alpine wrapper, per-card edit controls, and floating toolbar. The full template replacement:

```html
<div class="p-4" x-data="dzWorkspaceEditor('{{ workspace.name }}', {{ layout_json }})">
  {% if workspace.purpose %}
  <p class="text-sm opacity-60 mb-4">{{ workspace.purpose }}</p>
  {% endif %}

  {# Workspace header with Customize button #}
  <div class="flex items-center justify-between mb-4">
    <div></div>
    <button @click="toggleEdit()" class="btn btn-sm btn-ghost gap-1" x-show="!editing" x-transition>
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
      </svg>
      Customize
    </button>
  </div>

  {% if workspace.context_options_url %}
  {# ... existing context selector code unchanged ... #}
  {% endif %}

  {# Region grid — 12-col with alpine-sort for drag reorder #}
  <div class="grid grid-cols-12 gap-4"
       x-sort="onReorder"
       {% if workspace.sse_url %}hx-ext="sse" sse-connect="{{ workspace.sse_url }}"{% endif %}>

    {% for region in workspace.regions %}
    <template x-for="r in regions" :key="r.name">
    {# This is rendered server-side; Alpine manages visibility/width in edit mode #}
    </template>
    {% if region.source_tabs %}
    <div class="col-span-12 transition-all duration-200"
         id="region-{{ region.name }}"
         data-region-name="{{ region.name }}"
         x-show="!regions.find(r => r.name === '{{ region.name }}')?.hidden || editing"
         :class="['md:col-span-' + (regions.find(r => r.name === '{{ region.name }}')?.col_span ?? {{ region.col_span }}), regions.find(r => r.name === '{{ region.name }}')?.hidden ? 'opacity-40' : '']">

      {# Edit mode controls #}
      <div x-show="editing" x-transition class="mb-1 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="cursor-grab" x-sort:handle>
            <svg class="w-4 h-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16"/></svg>
          </span>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 4}" @click="setWidth('{{ region.name }}', 4)">1/3</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 6}" @click="setWidth('{{ region.name }}', 6)">1/2</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 8}" @click="setWidth('{{ region.name }}', 8)">2/3</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 12}" @click="setWidth('{{ region.name }}', 12)">Full</button>
          </div>
        </div>
        <button class="btn btn-ghost btn-xs" @click="toggleVisibility('{{ region.name }}')">
          <svg x-show="!regions.find(r => r.name === '{{ region.name }}')?.hidden" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
          <svg x-show="regions.find(r => r.name === '{{ region.name }}')?.hidden" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg>
        </button>
      </div>

      {% include 'workspace/regions/tabbed_list.html' with context %}
    </div>
    {% else %}
    <div class="col-span-12 transition-all duration-200"
         id="region-{{ region.name }}"
         data-region-name="{{ region.name }}"
         x-show="!regions.find(r => r.name === '{{ region.name }}')?.hidden || editing"
         :class="['md:col-span-' + (regions.find(r => r.name === '{{ region.name }}')?.col_span ?? {{ region.col_span }}), regions.find(r => r.name === '{{ region.name }}')?.hidden ? 'opacity-40' : '']"
         {% if region.endpoint %}
         hx-get="{{ region.endpoint }}"
         hx-trigger="{% if not region.hidden and loop.index <= workspace.fold_count %}load{% else %}intersect once{% endif %}{% if workspace.sse_url %}, sse:entity.created, sse:entity.updated, sse:entity.deleted{% endif %}"
         hx-swap="innerHTML"
         {% endif %}>

      {# Edit mode controls (same as above) #}
      <div x-show="editing" x-transition class="mb-1 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="cursor-grab" x-sort:handle>
            <svg class="w-4 h-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16"/></svg>
          </span>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 4}" @click="setWidth('{{ region.name }}', 4)">1/3</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 6}" @click="setWidth('{{ region.name }}', 6)">1/2</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 8}" @click="setWidth('{{ region.name }}', 8)">2/3</button>
            <button class="btn btn-xs" :class="{'btn-primary': regions.find(r => r.name === '{{ region.name }}')?.col_span === 12}" @click="setWidth('{{ region.name }}', 12)">Full</button>
          </div>
        </div>
        <button class="btn btn-ghost btn-xs" @click="toggleVisibility('{{ region.name }}')">
          <svg x-show="!regions.find(r => r.name === '{{ region.name }}')?.hidden" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
          <svg x-show="regions.find(r => r.name === '{{ region.name }}')?.hidden" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg>
        </button>
      </div>

      {# Skeleton placeholder while loading #}
      <div class="card bg-base-100 shadow-sm">
        <div class="card-body">
          <h3 class="card-title text-sm">{{ region.title }}</h3>
          {% if region.endpoint %}
          <div class="space-y-3 py-2">
            <div class="dz-skeleton dz-skeleton-text-lg"></div>
            <div class="dz-skeleton dz-skeleton-text" style="width: 90%"></div>
            <div class="dz-skeleton dz-skeleton-text" style="width: 75%"></div>
          </div>
          {% else %}
          <p class="text-sm opacity-50">{{ region.empty_message }}</p>
          {% endif %}
        </div>
      </div>
    </div>
    {% endif %}
    {% endfor %}
  </div>

  {# Floating toolbar — edit mode only #}
  <div x-show="editing" x-transition
       class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-base-100 shadow-xl rounded-lg border border-base-300 px-4 py-3 flex items-center gap-3">
    <button @click="save()" class="btn btn-primary btn-sm">Save layout</button>
    <button @click="cancel()" class="btn btn-ghost btn-sm">Cancel</button>
    <button @click="reset()" class="btn btn-ghost btn-sm text-error">Reset to default</button>
  </div>
</div>

{# Detail drawer: unchanged — same as before #}
```

Note: The context selector block, detail drawer, and drawer JS remain unchanged. Only the region grid wrapper and per-region divs change.

- [ ] **Step 2: Verify the template renders without errors**

Start dev server, navigate to a workspace. Verify:
- Regions render in correct order with correct widths
- "Customize" button appears in header
- Clicking "Customize" enters edit mode (drag handles, width buttons, eye toggles appear)
- Clicking "Cancel" exits edit mode

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_ui/templates/workspace/_content.html
git commit -m "feat: workspace edit mode UI — drag handles, width selector, visibility toggle"
```

---

### Task 7: Quality checks and ship

**Files:** All modified files from Tasks 1-6.

- [ ] **Step 1: Lint**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
```

- [ ] **Step 2: Type check**

```bash
mypy src/dazzle_ui/runtime/workspace_renderer.py
```

- [ ] **Step 3: Full test suite**

```bash
pytest tests/ -m "not e2e" -x -q
```

Fix any failures.

- [ ] **Step 4: Push and monitor CI**

```bash
git push
gh run list --branch $(git branch --show-current) --limit 1
```

- [ ] **Step 5: Create GitHub issue for follow-on work**

Create issue: "Evaluate migrating dz.js consumers to Alpine.js" — references this feature as the catalyst for Alpine.js adoption.
