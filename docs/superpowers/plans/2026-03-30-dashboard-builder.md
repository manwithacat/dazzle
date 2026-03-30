# Dashboard Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the workspace editor with a full dashboard builder — SortableJS drag-reorder, snap-grid drag-resize, add/remove cards from DSL catalog, auto-save.

**Architecture:** Rewrite `workspace-editor.js` → `dashboard-builder.js` (Alpine component backed by SortableJS). Layout schema v2 stores card instances with `{id, region, col_span, row_order}`. v1 layouts auto-migrate. New `/api/workspaces/{name}/catalog` endpoint returns available widgets. Template rewritten to remove edit-mode gating.

**Tech Stack:** SortableJS (vendored), Alpine.js (existing), HTMX (existing), DaisyUI (existing)

**Spec:** `docs/superpowers/specs/2026-03-30-dashboard-builder-design.md`

---

### Task 1: v1→v2 Layout Migration + v2 Schema Support

**Files:**
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py:395-445`
- Modify: `tests/unit/test_workspace_layout_prefs.py`

This task updates `apply_layout_preferences()` to handle v2 layouts and auto-migrate v1 layouts.

- [ ] **Step 1: Write failing tests for v2 layout schema**

Add these tests to `tests/unit/test_workspace_layout_prefs.py`:

```python
class TestLayoutV2:
    """apply_layout_preferences handles v2 card-instance layouts."""

    def _make_ctx(self, region_count: int = 3) -> object:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=region_count)
        return build_workspace_context(ws)

    def test_v2_layout_applies_card_order(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_2", "col_span": 6, "row_order": 0},
                {"id": "c2", "region": "region_0", "col_span": 12, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_2", "region_0"]
        assert result.regions[0].col_span == 6
        assert result.regions[1].col_span == 12

    def test_v2_duplicate_region_creates_multiple_cards(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 6, "row_order": 0},
                {"id": "c2", "region": "region_0", "col_span": 12, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert len(result.regions) == 2
        assert result.regions[0].col_span == 6
        assert result.regions[1].col_span == 12

    def test_v2_ghost_region_skipped(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "ghost", "col_span": 6, "row_order": 0},
                {"id": "c2", "region": "region_0", "col_span": 12, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert len(result.regions) == 1
        assert result.regions[0].name == "region_0"

    def test_v2_col_span_3_allowed(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(1)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 3, "row_order": 0},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[0].col_span == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_workspace_layout_prefs.py::TestLayoutV2 -v`
Expected: FAIL — v2 layout not handled yet

- [ ] **Step 3: Write failing tests for v1→v2 migration**

Add to `tests/unit/test_workspace_layout_prefs.py`:

```python
class TestV1ToV2Migration:
    """v1 layouts auto-migrate to v2 format."""

    def test_migrate_preserves_order_and_widths(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {
            "order": ["region_2", "region_0", "region_1"],
            "hidden": [],
            "widths": {"region_0": 6, "region_2": 4},
        }
        dsl_region_names = ["region_0", "region_1", "region_2"]
        v2 = migrate_v1_to_v2(v1, dsl_region_names)
        assert v2["version"] == 2
        assert len(v2["cards"]) == 3
        assert v2["cards"][0]["region"] == "region_2"
        assert v2["cards"][0]["col_span"] == 4
        assert v2["cards"][1]["region"] == "region_0"
        assert v2["cards"][1]["col_span"] == 6

    def test_migrate_drops_hidden(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {
            "order": ["region_0", "region_1"],
            "hidden": ["region_1"],
            "widths": {},
        }
        v2 = migrate_v1_to_v2(v1, ["region_0", "region_1"])
        assert len(v2["cards"]) == 1
        assert v2["cards"][0]["region"] == "region_0"

    def test_migrate_ghost_region_dropped(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["region_0", "ghost"], "hidden": [], "widths": {}}
        v2 = migrate_v1_to_v2(v1, ["region_0"])
        assert len(v2["cards"]) == 1

    def test_migrate_assigns_unique_ids(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["r0", "r1"], "hidden": [], "widths": {}}
        v2 = migrate_v1_to_v2(v1, ["r0", "r1"])
        ids = [c["id"] for c in v2["cards"]]
        assert len(set(ids)) == len(ids)
```

- [ ] **Step 4: Run migration tests to verify they fail**

Run: `pytest tests/unit/test_workspace_layout_prefs.py::TestV1ToV2Migration -v`
Expected: FAIL — `migrate_v1_to_v2` not defined

- [ ] **Step 5: Implement `migrate_v1_to_v2` and update `apply_layout_preferences`**

In `src/dazzle_ui/runtime/workspace_renderer.py`, add the migration function before `apply_layout_preferences` and update that function to handle both schemas:

```python
def migrate_v1_to_v2(
    v1_layout: dict[str, Any],
    dsl_region_names: list[str],
) -> dict[str, Any]:
    """Convert v1 layout {order, hidden, widths} to v2 {version, cards}."""
    valid_names = set(dsl_region_names)
    hidden_set = set(v1_layout.get("hidden", []))
    widths = v1_layout.get("widths", {})
    cards: list[dict[str, Any]] = []
    for i, name in enumerate(v1_layout.get("order", [])):
        if name not in valid_names or name in hidden_set:
            continue
        cards.append({
            "id": f"migrated-{i}",
            "region": name,
            "col_span": widths.get(name, 6),
            "row_order": i,
        })
    return {"version": 2, "cards": cards}


def apply_layout_preferences(
    ctx: WorkspaceContext,
    user_prefs: dict[str, str],
) -> WorkspaceContext:
    """Merge user layout preferences with DSL defaults.

    Supports v2 card-instance layouts and auto-migrates v1 layouts.
    Returns *ctx* unchanged if no preference exists.
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

    # Auto-migrate v1 → v2
    dsl_region_names = [r.name for r in ctx.regions]
    if layout.get("version") != 2:
        layout = migrate_v1_to_v2(layout, dsl_region_names)

    # Build region instances from v2 card list
    region_map = {r.name: r for r in ctx.regions}
    valid_spans = {3, 4, 6, 8, 12}
    ordered: list[RegionContext] = []
    for card in layout.get("cards", []):
        region_name = card.get("region", "")
        if region_name not in region_map:
            continue
        r = region_map[region_name].model_copy(deep=True)
        span = card.get("col_span", r.col_span)
        if span in valid_spans:
            r.col_span = span
        r.hidden = False
        ordered.append(r)

    return ctx.model_copy(update={"regions": ordered})
```

- [ ] **Step 6: Run all layout preference tests**

Run: `pytest tests/unit/test_workspace_layout_prefs.py -v`
Expected: `TestLayoutV2` and `TestV1ToV2Migration` PASS. Some existing `TestApplyLayoutPreferences` tests may fail because v1 hidden behaviour changed (v2 drops hidden cards instead of flagging them). Update `test_hidden_regions_flagged` and `test_fold_count_skips_hidden_regions` — hidden cards are now simply absent:

```python
def test_hidden_regions_flagged(self) -> None:
    """v1 hidden regions are dropped during migration (not flagged)."""
    import json

    from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

    ctx = self._make_ctx(3)
    prefs = {f"workspace.{ctx.name}.layout": json.dumps({"hidden": ["region_1"]})}
    result = apply_layout_preferences(ctx, prefs)
    assert len(result.regions) == 2
    assert all(r.name != "region_1" for r in result.regions)
```

- [ ] **Step 7: Run full test suite to confirm no regressions**

Run: `pytest tests/unit/test_workspace_layout_prefs.py tests/unit/test_workspace_rendering.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/dazzle_ui/runtime/workspace_renderer.py tests/unit/test_workspace_layout_prefs.py
git commit -m "feat: v2 layout schema with card instances and v1 auto-migration"
```

---

### Task 2: Catalog Endpoint

**Files:**
- Modify: `src/dazzle_ui/runtime/workspace_renderer.py`
- Modify: `src/dazzle_ui/runtime/page_routes.py:897-912`
- Test: `tests/unit/test_workspace_layout_prefs.py`

- [ ] **Step 1: Write failing test for catalog builder**

Add to `tests/unit/test_workspace_layout_prefs.py`:

```python
class TestCatalogBuilder:
    """build_catalog returns available regions for widget picker."""

    def test_returns_all_regions(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            build_catalog,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=3)
        ctx = build_workspace_context(ws)
        catalog = build_catalog(ctx)
        assert len(catalog) == 3
        assert catalog[0]["name"] == "region_0"
        assert catalog[0]["title"] == "Region 0"

    def test_includes_display_and_entity(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import (
            build_catalog,
            build_workspace_context,
        )

        ws = _make_workspace("scanner_table", region_count=1)
        ctx = build_workspace_context(ws)
        catalog = build_catalog(ctx)
        assert catalog[0]["display"] == "LIST"
        assert catalog[0]["entity"] == "Entity0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_layout_prefs.py::TestCatalogBuilder -v`
Expected: FAIL — `build_catalog` not defined

- [ ] **Step 3: Implement `build_catalog`**

Add to `src/dazzle_ui/runtime/workspace_renderer.py`:

```python
def build_catalog(ctx: WorkspaceContext) -> list[dict[str, str]]:
    """Build the widget catalog for a workspace's card picker."""
    return [
        {
            "name": r.name,
            "title": r.title or r.name.replace("_", " ").title(),
            "display": r.display,
            "entity": r.source,
        }
        for r in ctx.regions
    ]
```

- [ ] **Step 4: Run catalog tests**

Run: `pytest tests/unit/test_workspace_layout_prefs.py::TestCatalogBuilder -v`
Expected: PASS

- [ ] **Step 5: Update layout_json in page_routes.py to include v2 data**

In `src/dazzle_ui/runtime/page_routes.py`, update the `layout_json` block (around line 900) to include catalog and v2 card data:

```python
    from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences, build_catalog

    render_ws_ctx = apply_layout_preferences(ws_context, user_preferences)
    catalog = build_catalog(ws_context)

    # Build v2 card list for the template data island
    cards_for_json = []
    for i, r in enumerate(render_ws_ctx.regions):
        cards_for_json.append({
            "id": f"card-{i}",
            "region": r.name,
            "title": r.title or r.name.replace("_", " ").title(),
            "col_span": r.col_span,
            "row_order": i,
        })

    layout_json = json.dumps({
        "version": 2,
        "cards": cards_for_json,
        "catalog": catalog,
        "workspace_name": render_ws_ctx.name,
    })
```

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_ui/runtime/workspace_renderer.py src/dazzle_ui/runtime/page_routes.py tests/unit/test_workspace_layout_prefs.py
git commit -m "feat: workspace catalog builder and v2 layout JSON for dashboard"
```

---

### Task 3: Vendor SortableJS + Update Base Template

**Files:**
- Create: `src/dazzle_ui/runtime/static/vendor/sortable.min.js`
- Remove: `src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js`
- Modify: `src/dazzle_ui/templates/base.html:47,53`

- [ ] **Step 1: Download and vendor SortableJS**

```bash
curl -L -o src/dazzle_ui/runtime/static/vendor/sortable.min.js \
  "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"
```

Verify the file is non-empty and contains `Sortable`:

```bash
head -c 100 src/dazzle_ui/runtime/static/vendor/sortable.min.js
```

- [ ] **Step 2: Update base.html script tags**

In `src/dazzle_ui/templates/base.html`, replace:
```html
  <script defer src="{{ 'vendor/alpine-sort.min.js' | static_url }}"></script>
```
with:
```html
  <script defer src="{{ 'vendor/sortable.min.js' | static_url }}"></script>
```

And replace:
```html
  <script defer src="{{ 'js/workspace-editor.js' | static_url }}"></script>
```
with:
```html
  <script defer src="{{ 'js/dashboard-builder.js' | static_url }}"></script>
```

- [ ] **Step 3: Remove old Alpine Sort plugin**

```bash
rm src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js
```

- [ ] **Step 4: Verify no remaining references to alpine-sort**

```bash
grep -r "alpine-sort" src/dazzle_ui/ tests/
```

Expected: No matches (the old `workspace-editor.js` references it but we'll replace that file in Task 4).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_ui/runtime/static/vendor/sortable.min.js src/dazzle_ui/templates/base.html
git rm src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js
git commit -m "feat: vendor SortableJS, remove Alpine Sort plugin"
```

---

### Task 4: Dashboard Builder JS Component

**Files:**
- Create: `src/dazzle_ui/runtime/static/js/dashboard-builder.js`
- Remove: `src/dazzle_ui/runtime/static/js/workspace-editor.js`

This is the core JS component — Alpine.js data component backed by SortableJS for drag-reorder, custom resize handler for snap-grid, add/remove card management, and auto-save.

- [ ] **Step 1: Write `dashboard-builder.js`**

Create `src/dazzle_ui/runtime/static/js/dashboard-builder.js`:

```javascript
/**
 * dashboard-builder.js — Alpine.js component for card-based workspace dashboards.
 *
 * Features: SortableJS drag-to-reorder, snap-grid drag-to-resize,
 * add/remove cards, auto-save to user preferences.
 *
 * Replaces workspace-editor.js (v0.51.16).
 */

document.addEventListener("alpine:init", () => {
  Alpine.data("dzDashboardBuilder", () => ({
    cards: [],
    catalog: [],
    workspaceName: "",
    showPicker: false,
    _saveTimer: null,
    _sortable: null,

    init() {
      const el = document.getElementById("dz-workspace-layout");
      if (!el) return;
      try {
        const data = JSON.parse(el.textContent);
        this.cards = data.cards || [];
        this.catalog = data.catalog || [];
        this.workspaceName = data.workspace_name || "";
      } catch {
        return;
      }

      // Init SortableJS on the grid container after Alpine renders
      this.$nextTick(() => {
        const grid = this.$el.querySelector("[data-dashboard-grid]");
        if (!grid) return;
        this._sortable = new Sortable(grid, {
          handle: "[data-drag-handle]",
          animation: 150,
          ghostClass: "opacity-30",
          chosenClass: "ring-2 ring-primary",
          onEnd: () => {
            // Rebuild card order from DOM
            const ids = [];
            grid.querySelectorAll("[data-card-id]").forEach((el) => {
              ids.push(el.dataset.cardId);
            });
            const cardMap = {};
            this.cards.forEach((c) => { cardMap[c.id] = c; });
            this.cards = ids.map((id) => cardMap[id]).filter(Boolean);
            this._scheduleSave();
          },
        });
      });
    },

    // ── Resize ──────────────────────────────────────────────
    startResize(cardId, event) {
      event.preventDefault();
      const grid = this.$el.querySelector("[data-dashboard-grid]");
      if (!grid) return;
      const gridWidth = grid.offsetWidth;
      const snaps = [
        { cols: 3, pct: 0.25 },
        { cols: 4, pct: 0.333 },
        { cols: 6, pct: 0.5 },
        { cols: 8, pct: 0.667 },
        { cols: 12, pct: 1.0 },
      ];
      const card = this.cards.find((c) => c.id === cardId);
      if (!card) return;

      const onMove = (e) => {
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const cardEl = grid.querySelector(`[data-card-id="${cardId}"]`);
        if (!cardEl) return;
        const cardLeft = cardEl.getBoundingClientRect().left;
        const width = clientX - cardLeft;
        const pct = Math.max(0.1, Math.min(1.0, width / gridWidth));

        // Find nearest snap
        let best = snaps[snaps.length - 1];
        let bestDist = Math.abs(pct - best.pct);
        for (const snap of snaps) {
          const dist = Math.abs(pct - snap.pct);
          if (dist < bestDist) {
            best = snap;
            bestDist = dist;
          }
        }
        card.col_span = best.cols;
      };

      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.removeEventListener("touchmove", onMove);
        document.removeEventListener("touchend", onUp);
        document.body.classList.remove("select-none", "cursor-col-resize");
        this._scheduleSave();
      };

      document.body.classList.add("select-none", "cursor-col-resize");
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.addEventListener("touchmove", onMove);
      document.addEventListener("touchend", onUp);
    },

    // ── Add / Remove ────────────────────────────────────────
    addCard(regionName) {
      const nextId = "card-" + Date.now();
      const catalogEntry = this.catalog.find((c) => c.name === regionName);
      this.cards.push({
        id: nextId,
        region: regionName,
        title: catalogEntry ? catalogEntry.title : regionName,
        col_span: 6,
        row_order: this.cards.length,
      });
      this.showPicker = false;
      this._scheduleSave();

      // Trigger HTMX load for the new card
      this.$nextTick(() => {
        const cardEl = this.$el.querySelector(`[data-card-id="${nextId}"]`);
        if (cardEl) htmx.process(cardEl);
      });
    },

    removeCard(cardId) {
      this.cards = this.cards.filter((c) => c.id !== cardId);
      this._scheduleSave();
    },

    // ── Persistence ─────────────────────────────────────────
    _scheduleSave() {
      clearTimeout(this._saveTimer);
      this._saveTimer = setTimeout(() => this._save(), 500);
    },

    _save() {
      const layout = {
        version: 2,
        cards: this.cards.map((c, i) => ({
          id: c.id,
          region: c.region,
          col_span: c.col_span,
          row_order: i,
        })),
      };
      const key = "workspace." + this.workspaceName + ".layout";
      const prefs = {};
      prefs[key] = JSON.stringify(layout);
      fetch("/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: prefs }),
      }).catch(() => {
        if (window.dz?.toast) window.dz.toast("Failed to save layout", "error");
      });
    },

    resetLayout() {
      const key = "workspace." + this.workspaceName + ".layout";
      fetch("/auth/preferences/" + encodeURIComponent(key), {
        method: "DELETE",
      }).then(() => location.reload());
    },
  }));
});
```

- [ ] **Step 2: Remove old workspace-editor.js**

```bash
rm src/dazzle_ui/runtime/static/js/workspace-editor.js
```

- [ ] **Step 3: Verify no remaining references to workspace-editor or dzWorkspaceEditor**

```bash
grep -r "workspace-editor\|dzWorkspaceEditor" src/dazzle_ui/ tests/
```

Expected: Only `_content.html` (which we'll rewrite in Task 5).

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/dashboard-builder.js
git rm src/dazzle_ui/runtime/static/js/workspace-editor.js
git commit -m "feat: dashboard-builder.js with SortableJS, snap-resize, add/remove"
```

---

### Task 5: Rewrite Workspace Template

**Files:**
- Modify: `src/dazzle_ui/templates/workspace/_content.html`
- Create: `src/dazzle_ui/templates/workspace/_card_picker.html`

- [ ] **Step 1: Create the card picker popover template**

Create `src/dazzle_ui/templates/workspace/_card_picker.html`:

```html
{# Card picker popover — lists available regions from the catalog #}
<div x-show="showPicker" x-transition
     @click.away="showPicker = false"
     class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-80 bg-base-100 shadow-xl rounded-lg border border-base-300 p-3 z-50 max-h-64 overflow-y-auto">
  <h4 class="text-sm font-semibold mb-2">Add a card</h4>
  <template x-for="item in catalog" :key="item.name">
    <button @click="addCard(item.name)"
            class="w-full text-left px-3 py-2 rounded hover:bg-base-200 flex items-center gap-2 text-sm">
      <span class="badge badge-sm badge-ghost" x-text="item.display.toLowerCase()"></span>
      <span x-text="item.title"></span>
      <span class="text-xs opacity-50 ml-auto" x-text="item.entity"></span>
    </button>
  </template>
  <div x-show="catalog.length === 0" class="text-sm opacity-50 py-2">No widgets available.</div>
</div>
```

- [ ] **Step 2: Rewrite `_content.html` for dashboard builder**

Replace the full contents of `src/dazzle_ui/templates/workspace/_content.html`:

```html
{# Layout JSON embedded as a data island (#635) #}
<script type="application/json" id="dz-workspace-layout">{{ layout_json | safe }}</script>
<div class="p-4" x-data="dzDashboardBuilder()">
  {% if workspace.purpose %}
  <p class="text-sm opacity-60 mb-4">{{ workspace.purpose }}</p>
  {% endif %}

  {% if workspace.context_options_url %}
  <div class="mb-4 flex items-center gap-2">
    <label class="text-sm font-medium" for="dz-context-selector">{{ workspace.context_selector_label or workspace.context_selector_entity.replace('_', ' ') }}:</label>
    <select id="dz-context-selector" class="select select-bordered select-sm">
      <option value="">All</option>
    </select>
  </div>
  <script>
  (function() {
    var sel = document.getElementById('dz-context-selector');
    if (!sel) return;
    var wsName = {{ workspace.name | tojson }};
    var prefKey = 'workspace.' + wsName + '.context';
    fetch({{ workspace.context_options_url | tojson }})
      .then(function(r) { return r.json(); })
      .then(function(data) {
        (data.options || []).forEach(function(opt) {
          var o = document.createElement('option');
          o.value = opt.id;
          o.textContent = opt.label;
          sel.appendChild(o);
        });
        var saved = window.dzPrefs ? window.dzPrefs.get(prefKey) : null;
        if (saved) { sel.value = saved; sel.dispatchEvent(new Event('change')); }
      });
    sel.addEventListener('change', function() {
      var val = sel.value;
      if (window.dzPrefs) { if (val) window.dzPrefs.set(prefKey, val); else window.dzPrefs.del(prefKey); }
      document.querySelectorAll('[id^="region-"][hx-get]').forEach(function(el) {
        var url = el.getAttribute('hx-get');
        var base = url.split('?')[0];
        var params = new URLSearchParams(url.split('?')[1] || '');
        if (val) params.set('context_id', val); else params.delete('context_id');
        var qs = params.toString();
        var newUrl = base + (qs ? '?' + qs : '');
        el.setAttribute('hx-get', newUrl);
        htmx.process(el);
        htmx.ajax('GET', newUrl, {target: '#' + el.id, swap: 'innerHTML'});
      });
    });
  })();
  </script>
  {% endif %}

  {# Dashboard header with reset menu #}
  <div class="flex items-center justify-end mb-4">
    <div class="dropdown dropdown-end">
      <label tabindex="0" class="btn btn-sm btn-ghost">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v.01M12 12v.01M12 19v.01"/>
        </svg>
      </label>
      <ul tabindex="0" class="dropdown-content menu p-2 shadow bg-base-100 rounded-box w-52 z-50">
        <li><a @click="resetLayout()">Reset to default layout</a></li>
      </ul>
    </div>
  </div>

  {# Card grid — SortableJS container #}
  <div class="grid grid-cols-1 md:grid-cols-12 gap-4" data-dashboard-grid
       {% if workspace.sse_url %}hx-ext="sse"
       sse-connect="{{ workspace.sse_url }}"{% endif %}>
    <template x-for="card in cards" :key="card.id">
      <div class="transition-all duration-200 relative group"
           :data-card-id="card.id"
           :style="'grid-column: span ' + Math.min(card.col_span, 12) + ' / span ' + Math.min(card.col_span, 12)">
        {# Drag handle — visible on hover #}
        <div class="absolute -top-0 left-2 opacity-0 group-hover:opacity-100 transition-opacity z-10" data-drag-handle>
          <span class="cursor-grab active:cursor-grabbing p-1 rounded hover:bg-base-200">
            <svg class="w-4 h-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16"/></svg>
          </span>
        </div>
        {# Remove button — visible on hover #}
        <button @click="removeCard(card.id)"
                class="absolute -top-1 -right-1 opacity-0 group-hover:opacity-100 transition-opacity z-10 btn btn-circle btn-xs btn-ghost">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
        {# Card content — HTMX lazy-loaded #}
        <div class="card bg-base-100 shadow-sm"
             :id="'region-' + card.region + '-' + card.id"
             :hx-get="'/api/workspaces/{{ workspace.name }}/regions/' + card.region"
             hx-trigger="intersect once{% if workspace.sse_url %}, sse:entity.created, sse:entity.updated, sse:entity.deleted{% endif %}"
             hx-swap="innerHTML">
          <div class="card-body">
            <h3 class="card-title text-sm" x-text="card.title"></h3>
            <div class="space-y-3 py-2">
              <div class="dz-skeleton dz-skeleton-text-lg"></div>
              <div class="dz-skeleton dz-skeleton-text" style="width: 90%"></div>
              <div class="dz-skeleton dz-skeleton-text" style="width: 75%"></div>
            </div>
          </div>
        </div>
        {# Resize handle — right edge #}
        <div @mousedown="startResize(card.id, $event)"
             @touchstart="startResize(card.id, $event)"
             class="absolute top-0 right-0 w-1 h-full cursor-col-resize opacity-0 group-hover:opacity-100 hover:bg-primary/30 transition-opacity rounded-r"></div>
      </div>
    </template>
  </div>

  {# Add Card button #}
  <div class="relative flex justify-center mt-4">
    <button @click="showPicker = !showPicker"
            class="btn btn-sm btn-ghost btn-wide border-2 border-dashed border-base-300 hover:border-primary">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
      Add Card
    </button>
    {% include 'workspace/_card_picker.html' %}
  </div>
</div>

{# Detail drawer (unchanged) #}
<div id="dz-drawer-backdrop"
     class="fixed inset-0 z-40 bg-black/30 opacity-0 pointer-events-none transition-opacity duration-300"
     onclick="window.dzDrawer.close()"></div>
<aside id="dz-detail-drawer"
       class="fixed inset-y-0 right-0 z-50 flex flex-col w-full sm:max-w-2xl bg-base-100 shadow-2xl translate-x-full transition-transform duration-300 ease-in-out">
  <div class="flex items-center justify-between px-4 py-3 border-b border-base-200 bg-base-100 shrink-0">
    <button class="btn btn-ghost btn-sm gap-1" onclick="window.dzDrawer.close()">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      Close
    </button>
    <a id="dz-drawer-expand" href="#" class="btn btn-ghost btn-sm gap-1">
      Open full page
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
    </a>
  </div>
  <div id="dz-detail-drawer-content" class="flex-1 overflow-y-auto p-4"></div>
</aside>
<script>
(function() {
  var drawer = document.getElementById('dz-detail-drawer');
  var backdrop = document.getElementById('dz-drawer-backdrop');
  var content = document.getElementById('dz-detail-drawer-content');
  var expand = document.getElementById('dz-drawer-expand');

  window.dzDrawer = {
    isOpen: false,
    open: function(url) {
      if (url && expand) expand.href = url;
      drawer.classList.remove('translate-x-full');
      backdrop.classList.remove('opacity-0', 'pointer-events-none');
      document.body.classList.add('overflow-hidden');
      this.isOpen = true;
    },
    close: function() {
      drawer.classList.add('translate-x-full');
      backdrop.classList.add('opacity-0', 'pointer-events-none');
      document.body.classList.remove('overflow-hidden');
      this.isOpen = false;
    }
  };

  document.body.addEventListener('dz:drawerOpen', function(e) {
    var url = (e.detail && e.detail.url) || '';
    window.dzDrawer.open(url);
  });

  content.addEventListener('click', function(e) {
    var link = e.target.closest('a[href]');
    if (!link) return;
    if (link.hasAttribute('hx-get')) return;
    var href = link.getAttribute('href');
    if (!href || href === '#') return;
    if (link.textContent.trim().match(/back/i)) {
      e.preventDefault();
      window.dzDrawer.close();
      return;
    }
    if (href.startsWith('/')) {
      e.preventDefault();
      htmx.ajax('GET', href, {target: '#dz-detail-drawer-content', swap: 'innerHTML'});
    }
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && window.dzDrawer.isOpen) {
      window.dzDrawer.close();
    }
  });
})();
</script>
```

- [ ] **Step 3: Verify no remaining references to old component**

```bash
grep -r "dzWorkspaceEditor\|workspace-editor\|alpine-sort\|x-sort" src/dazzle_ui/
```

Expected: No matches.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/templates/workspace/_content.html src/dazzle_ui/templates/workspace/_card_picker.html
git commit -m "feat: rewrite workspace template for dashboard builder"
```

---

### Task 6: CSS for Resize Handles + Drag Feedback

**Files:**
- Modify: `src/dazzle_ui/runtime/static/css/dz.css`

- [ ] **Step 1: Add dashboard builder styles**

Append to `src/dazzle_ui/runtime/static/css/dz.css`:

```css
/* Dashboard builder: SortableJS drag feedback */
.sortable-ghost {
  opacity: 0.3;
}
.sortable-chosen {
  box-shadow: 0 0 0 2px oklch(var(--p));
  border-radius: var(--rounded-box, 1rem);
}
/* Prevent text selection during resize drag */
body.select-none {
  user-select: none;
  -webkit-user-select: none;
}
body.cursor-col-resize,
body.cursor-col-resize * {
  cursor: col-resize !important;
}
```

- [ ] **Step 2: Remove old `.sortable-drag` style if present**

Check for and remove any existing `.sortable-drag` rule that was for the old Alpine Sort integration.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_ui/runtime/static/css/dz.css
git commit -m "feat: CSS for dashboard builder drag and resize feedback"
```

---

### Task 7: Integration Test — Full Round-Trip

**Files:**
- Test: `tests/unit/test_workspace_layout_prefs.py`

- [ ] **Step 1: Write integration test for full layout round-trip**

Add to `tests/unit/test_workspace_layout_prefs.py`:

```python
class TestDashboardRoundTrip:
    """Full round-trip: default → add card → reorder → resize → persist."""

    def _make_ctx(self, region_count: int = 3) -> object:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=region_count)
        return build_workspace_context(ws)

    def test_default_layout_matches_dsl(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        result = apply_layout_preferences(ctx, {})
        assert [r.name for r in result.regions] == ["region_0", "region_1", "region_2"]

    def test_add_duplicate_card_and_persist(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        # Simulate user adding a duplicate of region_0
        layout = {
            "version": 2,
            "cards": [
                {"id": "card-0", "region": "region_0", "col_span": 12, "row_order": 0},
                {"id": "card-1", "region": "region_1", "col_span": 6, "row_order": 1},
                {"id": "card-2", "region": "region_0", "col_span": 4, "row_order": 2},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)

        assert len(result.regions) == 3
        assert result.regions[0].name == "region_0"
        assert result.regions[0].col_span == 12
        assert result.regions[2].name == "region_0"
        assert result.regions[2].col_span == 4

    def test_remove_card_persists(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        # Simulate user removing middle card
        layout = {
            "version": 2,
            "cards": [
                {"id": "card-0", "region": "region_0", "col_span": 12, "row_order": 0},
                {"id": "card-2", "region": "region_2", "col_span": 6, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert len(result.regions) == 2
        assert [r.name for r in result.regions] == ["region_0", "region_2"]

    def test_resize_snap_values_respected(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(1)
        for span in [3, 4, 6, 8, 12]:
            layout = {
                "version": 2,
                "cards": [{"id": "c", "region": "region_0", "col_span": span, "row_order": 0}],
            }
            prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
            result = apply_layout_preferences(ctx, prefs)
            assert result.regions[0].col_span == span, f"span={span} not applied"

    def test_invalid_span_uses_default(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(1)
        layout = {
            "version": 2,
            "cards": [{"id": "c", "region": "region_0", "col_span": 7, "row_order": 0}],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        # 7 is not a valid snap point — should keep original DSL default (12 for scanner_table)
        assert result.regions[0].col_span == 12
```

- [ ] **Step 2: Run all workspace tests**

Run: `pytest tests/unit/test_workspace_layout_prefs.py -v`
Expected: All PASS

- [ ] **Step 3: Run broader test suite to catch regressions**

Run: `pytest tests/unit/ -m "not e2e" -x -q --timeout=60 -k "workspace"`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_workspace_layout_prefs.py
git commit -m "test: dashboard builder round-trip integration tests"
```

---

### Task 8: Lint + Final Verification

**Files:** All modified files

- [ ] **Step 1: Run ruff**

```bash
ruff check src/dazzle_ui/ tests/unit/test_workspace_layout_prefs.py --fix
ruff format src/dazzle_ui/ tests/unit/test_workspace_layout_prefs.py
```

- [ ] **Step 2: Run mypy**

```bash
mypy src/dazzle_ui/runtime/workspace_renderer.py
```

Expected: No errors

- [ ] **Step 3: Run full unit test suite**

```bash
pytest tests/unit/ -m "not e2e" -x -q --timeout=60
```

Expected: All pass, no regressions

- [ ] **Step 4: Verify clean grep — no old references**

```bash
grep -r "dzWorkspaceEditor\|workspace-editor\|alpine-sort\|x-sort" src/ tests/
```

Expected: No matches

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -u
git commit -m "chore: lint fixes for dashboard builder"
```
