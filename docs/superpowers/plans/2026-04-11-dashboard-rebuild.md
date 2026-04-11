# Dashboard Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED CONTEXT:** Before writing any code, read these ux-architect skill artefacts:
> - `~/.claude/skills/ux-architect/tokens/linear.md`
> - `~/.claude/skills/ux-architect/components/dashboard-grid.md`
> - `~/.claude/skills/ux-architect/components/card.md`
> - `~/.claude/skills/ux-architect/primitives/drag-and-drop.md`
> - `~/.claude/skills/ux-architect/primitives/resize.md`
> - `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md`

**Goal:** Replace the SortableJS-based dashboard with a native pointer-event implementation governed by the ux-architect skill's component contracts and interaction primitives.

**Architecture:** Single Alpine `x-data` controller on grid root manages all state (cards, drag, resize, save lifecycle, undo). Template uses pure Tailwind utilities with structural tokens frozen from the Linear token sheet and colours mapped through existing `design-system.css` CSS variables. No external drag library.

**Tech Stack:** Alpine.js 3.x, HTMX 1.9.x, Tailwind CSS 4.x, native Pointer Events API

**Spec:** `docs/superpowers/specs/2026-04-11-dashboard-rebuild-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/dazzle_ui/runtime/static/js/dashboard-builder.js` | Rewrite | Alpine controller: cards, drag, resize, save lifecycle, undo |
| `src/dazzle_ui/templates/workspace/_content.html` | Rewrite | Grid markup, card chrome, toolbar, keyboard a11y |
| `src/dazzle_ui/templates/workspace/_card_picker.html` | Rewrite | Pure Tailwind card picker popover (remove DaisyUI classes) |
| `src/dazzle_ui/templates/base.html` | Modify line 46 | Remove SortableJS `<script>` tag |
| `src/dazzle_ui/runtime/static/css/dz.css` | Modify lines 254-261 | Remove `.sortable-ghost` and `.sortable-chosen` rules |
| `src/dazzle_ui/runtime/static/vendor/sortable.min.js` | Delete | No remaining consumers |

**Unchanged:** `workspace_renderer.py`, `page_routes.py`, all 17 region templates, layout JSON format, preference API.

---

### Task 1: Remove SortableJS Dependency

**Files:**
- Delete: `src/dazzle_ui/runtime/static/vendor/sortable.min.js`
- Modify: `src/dazzle_ui/templates/base.html:46`
- Modify: `src/dazzle_ui/runtime/static/css/dz.css:254-261`

- [ ] **Step 1: Delete the vendored SortableJS file**

```bash
rm src/dazzle_ui/runtime/static/vendor/sortable.min.js
```

- [ ] **Step 2: Remove the SortableJS script tag from base.html**

In `src/dazzle_ui/templates/base.html`, remove line 46:
```html
  <script defer src="{{ 'vendor/sortable.min.js' | static_url }}"></script>
```

- [ ] **Step 3: Remove SortableJS CSS rules from dz.css**

In `src/dazzle_ui/runtime/static/css/dz.css`, remove lines 254-261:
```css
/* Dashboard builder: SortableJS drag feedback */
.sortable-ghost {
  opacity: 0.3;
}
.sortable-chosen {
  box-shadow: 0 0 0 2px oklch(var(--p));
  border-radius: var(--rounded-box, 1rem);
}
```

- [ ] **Step 4: Verify no other files reference SortableJS**

```bash
rg -i "sortable" src/dazzle_ui --type js --type html --type css -l
```

Expected: only `dashboard-builder.js` and `_content.html` (which we rewrite in later tasks). The `task_inbox.py` and `template_compiler.py` references to `sortable` are the table column sort attribute — unrelated.

- [ ] **Step 5: Commit**

```bash
git add -A src/dazzle_ui/runtime/static/vendor/sortable.min.js src/dazzle_ui/templates/base.html src/dazzle_ui/runtime/static/css/dz.css
git commit -m "chore: remove SortableJS vendor dependency

No remaining consumers after dashboard rewrite. The 'sortable'
attribute on table columns (task_inbox.py, template_compiler.py)
is unrelated — it controls server-side sort, not SortableJS."
```

---

### Task 2: Rewrite Alpine Controller — Core State and Save Lifecycle

**Files:**
- Rewrite: `src/dazzle_ui/runtime/static/js/dashboard-builder.js`

This task writes the controller skeleton with card data loading, save lifecycle (clean/dirty/saving/saved/error), and undo stack. Drag and resize are added in Tasks 3 and 4.

- [ ] **Step 1: Write the new controller**

Replace the entire contents of `src/dazzle_ui/runtime/static/js/dashboard-builder.js` with:

```js
/**
 * dashboard-builder.js — Alpine.js controller for spec-governed dashboards.
 *
 * Implements: ux-architect/components/dashboard-grid.md
 * Tokens: ux-architect/tokens/linear.md (structural only; colours via --dz-* CSS vars)
 * No external dependencies (SortableJS removed).
 */
document.addEventListener("alpine:init", () => {
  Alpine.data("dzDashboardBuilder", () => ({
    // ── Data (from layout JSON data island) ──
    cards: [],
    catalog: [],
    workspaceName: "",

    // ── UI state ──
    showPicker: false,
    saveState: "clean", // clean | dirty | saving | saved | error
    _saveError: "",
    undoStack: [],

    // ── Drag state (null when idle) ──
    drag: null,

    // ── Resize state (null when idle) ──
    resize: null,

    // ── Timers ──
    _savedTimer: null,

    // ── Init ──
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

      // Keyboard shortcuts
      this._onKeydown = this._handleKeydown.bind(this);
      document.addEventListener("keydown", this._onKeydown);
    },

    destroy() {
      if (this._onKeydown) {
        document.removeEventListener("keydown", this._onKeydown);
      }
    },

    // ── Save lifecycle ──
    _markDirty() {
      if (this.saveState !== "dirty") {
        this.saveState = "dirty";
      }
    },

    _pushUndo() {
      this.undoStack.push(JSON.parse(JSON.stringify(this.cards)));
      // Cap at 20 entries
      if (this.undoStack.length > 20) this.undoStack.shift();
    },

    undo() {
      if (this.undoStack.length === 0) return;
      this.cards = this.undoStack.pop();
      this._markDirty();
    },

    async save() {
      if (this.saveState !== "dirty" && this.saveState !== "error") return;
      this.saveState = "saving";
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

      try {
        const resp = await fetch("/auth/preferences", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preferences: prefs }),
        });
        if (!resp.ok) throw new Error("Server returned " + resp.status);
        this.saveState = "saved";
        this.undoStack = [];
        clearTimeout(this._savedTimer);
        this._savedTimer = setTimeout(() => {
          if (this.saveState === "saved") this.saveState = "clean";
        }, 1200);
      } catch (err) {
        this.saveState = "error";
        this._saveError = err.message || "Failed to save";
      }
    },

    resetLayout() {
      if (this.saveState === "dirty" && !confirm("Discard unsaved changes?")) {
        return;
      }
      const key = "workspace." + this.workspaceName + ".layout";
      fetch("/auth/preferences/" + encodeURIComponent(key), {
        method: "DELETE",
      }).then(() => location.reload());
    },

    // ── Card management ──
    addCard(regionName) {
      this._pushUndo();
      const nextId = "card-" + Date.now();
      const entry = this.catalog.find((c) => c.name === regionName);
      this.cards.push({
        id: nextId,
        region: regionName,
        title: entry ? entry.title : regionName,
        col_span: 6,
        row_order: this.cards.length,
      });
      this.showPicker = false;
      this._markDirty();

      this.$nextTick(() => {
        const cardEl = this.$el.querySelector(
          '[data-card-id="' + nextId + '"]'
        );
        if (cardEl) htmx.process(cardEl);
      });
    },

    removeCard(cardId) {
      this._pushUndo();
      this.cards = this.cards.filter((c) => c.id !== cardId);
      this._markDirty();
    },

    // ── Keyboard ──
    _handleKeydown(e) {
      // Cmd/Ctrl+S — save
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        if (this.saveState === "dirty") {
          e.preventDefault();
          this.save();
        }
      }
      // Cmd/Ctrl+Z — undo
      if ((e.metaKey || e.ctrlKey) && e.key === "z" && !e.shiftKey) {
        if (this.undoStack.length > 0) {
          e.preventDefault();
          this.undo();
        }
      }
    },

    // ── Drag (Task 3) ──
    // startDrag, onPointerMoveDrag, endDrag — added in Task 3

    // ── Resize (Task 4) ──
    // startResize, onPointerMoveResize, endResize — added in Task 4

    // ── Helpers ──
    _colSpanClass(span) {
      const s = Math.min(Math.max(span, 3), 12);
      return "grid-column: span " + s + " / span " + s;
    },
  }));
});
```

- [ ] **Step 2: Verify the app still loads**

```bash
cd examples/ops_dashboard && dazzle serve --local
```

Open the workspace page. The dashboard should render cards (without drag/resize — those come in Tasks 3-4). The save button, add card, remove card, Cmd+S, and Cmd+Z should work. The cards will be static (no reordering yet).

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/dashboard-builder.js
git commit -m "feat(dashboard): rewrite Alpine controller with save lifecycle and undo

Replaces SortableJS-based controller with native Alpine state.
Save lifecycle: clean → dirty → saving → saved → clean.
Undo stack with Cmd+Z support. Drag and resize added next."
```

---

### Task 3: Implement Drag-and-Drop Primitive

**Files:**
- Modify: `src/dazzle_ui/runtime/static/js/dashboard-builder.js`

Adds the drag-and-drop reordering system using native Pointer Events, following the phases in `ux-architect/primitives/drag-and-drop.md`.

- [ ] **Step 1: Add drag methods to the controller**

In `dashboard-builder.js`, replace the `// ── Drag (Task 3) ──` comment block with:

```js
    // ── Drag ──
    startDrag(cardId, e) {
      if (e.button && e.button !== 0) return; // left click only
      e.preventDefault();
      const cardEl = this.$el.querySelector('[data-card-id="' + cardId + '"]');
      if (!cardEl) return;

      const rect = cardEl.getBoundingClientRect();
      this.drag = {
        cardId,
        startX: e.clientX,
        startY: e.clientY,
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        width: rect.width,
        height: rect.height,
        currentX: e.clientX,
        currentY: e.clientY,
        phase: "pressed",
        placeholderIndex: this.cards.findIndex((c) => c.id === cardId),
      };

      cardEl.setPointerCapture(e.pointerId);
      this._dragPointerId = e.pointerId;
    },

    onPointerMoveDrag(e) {
      if (!this.drag) return;
      this.drag.currentX = e.clientX;
      this.drag.currentY = e.clientY;

      // Phase transition: pressed → dragging (4px threshold)
      if (this.drag.phase === "pressed") {
        const dx = e.clientX - this.drag.startX;
        const dy = e.clientY - this.drag.startY;
        if (Math.sqrt(dx * dx + dy * dy) < 4) return;
        this._pushUndo();
        this.drag.phase = "dragging";
        document.body.classList.add("select-none");
      }

      if (this.drag.phase !== "dragging") return;

      // Find which card the pointer is over (by midpoint comparison)
      const grid = this.$el.querySelector("[data-grid-container]");
      if (!grid) return;
      const wrappers = grid.querySelectorAll("[data-card-id]");
      let targetIndex = this.drag.placeholderIndex;

      wrappers.forEach((wrapper, i) => {
        if (wrapper.dataset.cardId === this.drag.cardId) return;
        const rect = wrapper.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        if (e.clientY > midY) {
          // Find this card's index in the array
          const cardIndex = this.cards.findIndex(
            (c) => c.id === wrapper.dataset.cardId
          );
          if (cardIndex >= 0) targetIndex = cardIndex + 1;
        }
      });

      // Move placeholder in array if position changed
      if (targetIndex !== this.drag.placeholderIndex) {
        const card = this.cards.find((c) => c.id === this.drag.cardId);
        if (card) {
          const filtered = this.cards.filter(
            (c) => c.id !== this.drag.cardId
          );
          filtered.splice(
            Math.min(targetIndex, filtered.length),
            0,
            card
          );
          this.cards = filtered;
          this.drag.placeholderIndex = this.cards.findIndex(
            (c) => c.id === this.drag.cardId
          );
        }
      }
    },

    endDrag(e) {
      if (!this.drag) return;
      const wasDragging = this.drag.phase === "dragging";
      this.drag = null;
      this._dragPointerId = null;
      document.body.classList.remove("select-none");

      if (wasDragging) {
        this._markDirty();
        // Announce for screen readers
        this._announce("Card moved");
      }
    },

    cancelDrag() {
      if (!this.drag) return;
      if (this.drag.phase === "dragging" && this.undoStack.length > 0) {
        this.cards = this.undoStack.pop();
      }
      this.drag = null;
      this._dragPointerId = null;
      document.body.classList.remove("select-none");
    },

    isDragging(cardId) {
      return (
        this.drag &&
        this.drag.phase === "dragging" &&
        this.drag.cardId === cardId
      );
    },

    dragTransform(cardId) {
      if (!this.isDragging(cardId)) return "";
      const x = this.drag.currentX - this.drag.offsetX;
      const y = this.drag.currentY - this.drag.offsetY;
      return (
        "position:fixed;left:0;top:0;width:" +
        this.drag.width +
        "px;height:" +
        this.drag.height +
        "px;transform:translate(" +
        x +
        "px," +
        y +
        "px) scale(1.02);z-index:500;opacity:0.95;pointer-events:none;" +
        "box-shadow:0 12px 24px rgb(0 0 0/0.12),0 4px 8px rgb(0 0 0/0.06);"
      );
    },

    _announce(message) {
      let el = document.getElementById("dz-live-region");
      if (!el) {
        el = document.createElement("div");
        el.id = "dz-live-region";
        el.setAttribute("aria-live", "polite");
        el.setAttribute("aria-atomic", "true");
        el.className = "sr-only";
        document.body.appendChild(el);
      }
      el.textContent = message;
    },
```

- [ ] **Step 2: Add keyboard move mode**

Also in the controller, add inside the `_handleKeydown` method, before the closing brace:

```js
      // Escape during drag — cancel
      if (e.key === "Escape" && this.drag) {
        e.preventDefault();
        this.cancelDrag();
      }
```

And add a new method for keyboard-based card movement:

```js
    // Keyboard card move (Space to enter, arrows to move, Enter/Esc to exit)
    _keyboardMoveCardId: null,

    toggleKeyboardMove(cardId) {
      if (this._keyboardMoveCardId === cardId) {
        this._keyboardMoveCardId = null;
        this._announce("Move mode exited");
        return;
      }
      this._keyboardMoveCardId = cardId;
      this._announce("Move mode. Use arrow keys to reorder. Enter to confirm, Escape to cancel.");
    },

    handleCardKeydown(cardId, e) {
      if (e.key === " " || e.key === "Enter") {
        if (e.key === " ") {
          e.preventDefault();
          this.toggleKeyboardMove(cardId);
        } else if (this._keyboardMoveCardId === cardId) {
          e.preventDefault();
          this._keyboardMoveCardId = null;
          this._announce("Position confirmed");
        }
        return;
      }

      if (this._keyboardMoveCardId !== cardId) return;

      if (e.key === "Escape") {
        e.preventDefault();
        this._keyboardMoveCardId = null;
        this._announce("Move cancelled");
        return;
      }

      const idx = this.cards.findIndex((c) => c.id === cardId);
      if (idx < 0) return;

      let newIdx = idx;
      if (e.key === "ArrowUp" && idx > 0) newIdx = idx - 1;
      if (e.key === "ArrowDown" && idx < this.cards.length - 1) newIdx = idx + 1;

      if (newIdx !== idx) {
        e.preventDefault();
        this._pushUndo();
        const [card] = this.cards.splice(idx, 1);
        this.cards.splice(newIdx, 0, card);
        this._markDirty();
        this._announce("Card moved to position " + (newIdx + 1));

        // Re-focus the card after Alpine re-renders
        this.$nextTick(() => {
          const el = this.$el.querySelector('[data-card-id="' + cardId + '"]');
          if (el) el.focus();
        });
      }
    },
```

- [ ] **Step 3: Test drag in browser**

Open `ops_dashboard` workspace. Verify:
- Click a card header without moving — card stays put
- Drag 5px+ — card lifts with shadow and follows pointer
- Release — card settles into new position
- Save button shows "Save layout"
- `Cmd+Z` undoes the move
- Tab to a card, press Space, arrow keys reorder, Enter confirms

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/dashboard-builder.js
git commit -m "feat(dashboard): implement drag-and-drop with pointer events

Native pointer event drag replacing SortableJS. 5-phase model:
pressed → dragging (4px threshold) → continuous (transform:translate)
→ drop (reflow) or cancel (Esc). Keyboard move mode via Space+arrows.
Screen reader announcements via aria-live region."
```

---

### Task 4: Implement Resize Primitive

**Files:**
- Modify: `src/dazzle_ui/runtime/static/js/dashboard-builder.js`

Adds col-span resize following `ux-architect/primitives/resize.md`.

- [ ] **Step 1: Add resize methods to the controller**

In `dashboard-builder.js`, replace the `// ── Resize (Task 4) ──` comment block with:

```js
    // ── Resize ──
    _resizeSnaps: [3, 4, 6, 8, 12],

    startResize(cardId, e) {
      if (e.button && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const grid = this.$el.querySelector("[data-grid-container]");
      if (!grid) return;
      const card = this.cards.find((c) => c.id === cardId);
      if (!card) return;

      this._pushUndo();
      const gridRect = grid.getBoundingClientRect();

      this.resize = {
        cardId,
        startX: e.clientX,
        startColSpan: card.col_span,
        currentColSpan: card.col_span,
        gridWidth: gridRect.width,
        gridLeft: gridRect.left,
      };

      const target = e.target;
      if (target.setPointerCapture) target.setPointerCapture(e.pointerId);
      document.body.classList.add("select-none");
      document.body.style.cursor = "col-resize";
    },

    onPointerMoveResize(e) {
      if (!this.resize) return;

      const card = this.cards.find((c) => c.id === this.resize.cardId);
      if (!card) return;

      // Find the card element's left edge
      const cardEl = this.$el.querySelector(
        '[data-card-id="' + this.resize.cardId + '"]'
      );
      if (!cardEl) return;
      const cardLeft = cardEl.getBoundingClientRect().left;

      // Width from card left to current pointer
      const width = e.clientX - cardLeft;
      const colWidth = this.resize.gridWidth / 12;
      const rawCols = Math.round(width / colWidth);

      // Snap to nearest allowed value
      let best = this._resizeSnaps[0];
      let bestDist = Math.abs(rawCols - best);
      for (const snap of this._resizeSnaps) {
        const dist = Math.abs(rawCols - snap);
        if (dist < bestDist) {
          best = snap;
          bestDist = dist;
        }
      }

      card.col_span = best;
      this.resize.currentColSpan = best;
    },

    endResize(e) {
      if (!this.resize) return;
      const changed = this.resize.currentColSpan !== this.resize.startColSpan;
      this.resize = null;
      document.body.classList.remove("select-none");
      document.body.style.cursor = "";

      if (changed) {
        this._markDirty();
        this._announce("Card resized to " + this.cards.find(c => c.id)?.col_span + " columns");
      } else {
        // No change — pop the undo we pushed
        this.undoStack.pop();
      }
    },

    cancelResize() {
      if (!this.resize) return;
      const card = this.cards.find((c) => c.id === this.resize.cardId);
      if (card) card.col_span = this.resize.startColSpan;
      this.resize = null;
      document.body.classList.remove("select-none");
      document.body.style.cursor = "";
      this.undoStack.pop();
    },

    isResizing(cardId) {
      return this.resize && this.resize.cardId === cardId;
    },

    handleResizeKeydown(cardId, e) {
      if (e.key !== "r" && e.key !== "R") return;
      // Toggle keyboard resize mode
      const card = this.cards.find((c) => c.id === cardId);
      if (!card) return;

      if (this._keyboardResizeCardId === cardId) {
        this._keyboardResizeCardId = null;
        this._announce("Resize mode exited");
        return;
      }
      this._keyboardResizeCardId = cardId;
      this._announce(
        "Resize mode. Left/Right arrow to change width. Enter to confirm, Escape to cancel. Current: " +
        card.col_span + " columns."
      );
    },

    _keyboardResizeCardId: null,
    _keyboardResizeOriginal: null,

    handleResizeArrow(cardId, e) {
      if (this._keyboardResizeCardId !== cardId) return;
      const card = this.cards.find((c) => c.id === cardId);
      if (!card) return;

      if (e.key === "Escape") {
        e.preventDefault();
        if (this._keyboardResizeOriginal !== null) {
          card.col_span = this._keyboardResizeOriginal;
        }
        this._keyboardResizeCardId = null;
        this._keyboardResizeOriginal = null;
        this._announce("Resize cancelled");
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        if (this._keyboardResizeOriginal !== null && card.col_span !== this._keyboardResizeOriginal) {
          this._pushUndo();
          this._markDirty();
        }
        this._keyboardResizeCardId = null;
        this._keyboardResizeOriginal = null;
        this._announce("Resize confirmed: " + card.col_span + " columns");
        return;
      }

      const snaps = this._resizeSnaps;
      const currentIdx = snaps.indexOf(card.col_span);

      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        if (this._keyboardResizeOriginal === null) {
          this._keyboardResizeOriginal = card.col_span;
        }
        let newIdx = currentIdx;
        if (e.key === "ArrowRight" && currentIdx < snaps.length - 1) newIdx++;
        if (e.key === "ArrowLeft" && currentIdx > 0) newIdx--;
        if (newIdx !== currentIdx) {
          card.col_span = snaps[newIdx];
          this._announce(card.col_span + " columns");
        }
      }
    },
```

- [ ] **Step 2: Add Escape handling for resize in _handleKeydown**

In the `_handleKeydown` method, add after the drag Escape handler:

```js
      // Escape during resize — cancel
      if (e.key === "Escape" && this.resize) {
        e.preventDefault();
        this.cancelResize();
      }
```

- [ ] **Step 3: Test resize in browser**

Open `ops_dashboard`. Verify:
- Drag resize handle on right edge — col-span snaps to {3, 4, 6, 8, 12}
- Release — save button shows "Save layout"
- Focus a card, press R, Left/Right arrow changes width, Enter confirms
- Cmd+Z after resize undoes it

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/dashboard-builder.js
git commit -m "feat(dashboard): implement col-span resize with pointer events

Resize handle snaps to grid points {3,4,6,8,12}. Keyboard resize
via R key + arrow keys. Follows ux-architect/primitives/resize.md."
```

---

### Task 5: Rewrite Template — Card Chrome and Grid

**Files:**
- Rewrite: `src/dazzle_ui/templates/workspace/_content.html`
- Rewrite: `src/dazzle_ui/templates/workspace/_card_picker.html`

Rewrites both templates to pure Tailwind utilities with spec-governed card chrome. No DaisyUI component classes. Preserves the detail drawer (lines 119-189 of current file) and context selector (lines 4-50) unchanged.

- [ ] **Step 1: Rewrite _content.html**

Replace the entire contents of `src/dazzle_ui/templates/workspace/_content.html` with:

```html
{# Layout JSON embedded as a data island (#635) #}
<script type="application/json" id="dz-workspace-layout">{{ layout_json | safe }}</script>
<div class="p-4" x-data="dzDashboardBuilder()">
  {% if workspace.purpose %}
  <p class="text-[13px] leading-[18px] text-[hsl(var(--muted-foreground))] mb-4">{{ workspace.purpose }}</p>
  {% endif %}

  {% if workspace.context_options_url %}
  <div class="mb-4 flex items-center gap-2">
    <label class="text-[13px] font-medium" for="dz-context-selector">{{ workspace.context_selector_label or workspace.context_selector_entity.replace('_', ' ') }}:</label>
    <select id="dz-context-selector"
            class="h-8 rounded-[4px] border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-2 text-[13px] text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]">
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

  {# ── Toolbar ── #}
  <div class="flex items-center justify-end gap-2 mb-4">
    <div class="flex-1"></div>

    {# Reset button #}
    <button @click="resetLayout()"
            class="h-8 px-3 rounded-[4px] text-[13px] font-medium text-[hsl(var(--muted-foreground))]
                   transition-colors duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
                   hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]">
      Reset
    </button>

    {# Save button — reflects saveState #}
    <button @click="save()"
            :disabled="saveState === 'clean' || saveState === 'saving' || saveState === 'saved'"
            :class="{
              'text-[hsl(var(--muted-foreground))] cursor-default': saveState === 'clean',
              'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]': saveState === 'dirty',
              'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] opacity-70': saveState === 'saving',
              'bg-[hsl(var(--success))] text-[hsl(var(--success-foreground))]': saveState === 'saved',
              'border-[hsl(var(--destructive))] text-[hsl(var(--destructive))]': saveState === 'error',
            }"
            :title="saveState === 'error' ? _saveError : ''"
            class="h-8 px-3 rounded-[4px] text-[13px] font-medium border border-transparent
                   transition-all duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]">
      <span x-show="saveState === 'clean'">Saved</span>
      <span x-show="saveState === 'dirty'">Save layout</span>
      <span x-show="saveState === 'saving'" class="flex items-center gap-1">
        <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
        Saving
      </span>
      <span x-show="saveState === 'saved'" class="flex items-center gap-1">
        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
        Saved
      </span>
      <span x-show="saveState === 'error'">Retry</span>
    </button>
  </div>

  {# ── Card Grid ── #}
  <div class="grid grid-cols-1 md:grid-cols-12 gap-4"
       data-grid-container
       role="application"
       aria-label="Dashboard card grid"
       {% if workspace.sse_url %}hx-ext="sse" sse-connect="{{ workspace.sse_url }}"{% endif %}
       @pointermove.window="onPointerMoveDrag($event); onPointerMoveResize($event)"
       @pointerup.window="endDrag($event); endResize($event)">

    <template x-for="card in cards" :key="card.id">
      <div :data-card-id="card.id"
           :style="isDragging(card.id) ? dragTransform(card.id) : _colSpanClass(card.col_span)"
           :class="{ 'transition-all duration-[200ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]': !isDragging(card.id) && !drag }"
           tabindex="0"
           @keydown="handleCardKeydown(card.id, $event); handleResizeKeydown(card.id, $event); handleResizeArrow(card.id, $event)"
           class="relative group outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] focus:ring-offset-2 rounded-md">

        {# Card chrome #}
        <article class="rounded-md border bg-[hsl(var(--card))] overflow-hidden
                        transition-[border-color,box-shadow] duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]"
                 :class="{
                   'border-[hsl(var(--border))]': !isResizing(card.id),
                   'border-dashed border-[hsl(var(--primary))]': isResizing(card.id),
                 }"
                 role="article"
                 :aria-labelledby="'card-title-' + card.id">

          {# Card header — drag handle zone #}
          <div class="flex items-center justify-between px-4 py-2 cursor-grab active:cursor-grabbing min-h-[36px]"
               :class="{ 'cursor-grabbing': isDragging(card.id) }"
               @pointerdown="startDrag(card.id, $event)">
            <h3 :id="'card-title-' + card.id"
                class="text-[15px] font-medium leading-[22px] tracking-[-0.01em] text-[hsl(var(--foreground))] select-none"
                x-text="card.title"></h3>
            <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-[80ms]">
              <button @click.stop="removeCard(card.id)"
                      class="h-6 w-6 flex items-center justify-center rounded-[4px] text-[hsl(var(--muted-foreground))]
                             hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]
                             transition-colors duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]"
                      aria-label="Remove card">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          {# Card body — HTMX lazy-loaded region content #}
          <div class="px-4 pb-4"
               :id="'region-' + card.region + '-' + card.id"
               :hx-get="'/api/workspaces/{{ workspace.name }}/regions/' + card.region"
               hx-trigger="intersect once{% if workspace.sse_url %}, sse:entity.created, sse:entity.updated, sse:entity.deleted{% endif %}"
               hx-swap="innerHTML">
            {# Skeleton loading state #}
            <div class="space-y-3 py-2 animate-pulse">
              <div class="h-4 bg-[hsl(var(--muted))] rounded w-3/4"></div>
              <div class="h-3 bg-[hsl(var(--muted))] rounded w-full"></div>
              <div class="h-3 bg-[hsl(var(--muted))] rounded w-5/6"></div>
            </div>
          </div>
        </article>

        {# Resize handle — right edge, visible on hover #}
        <div @pointerdown="startResize(card.id, $event)"
             class="absolute top-0 right-0 w-1.5 h-full cursor-col-resize
                    opacity-0 group-hover:opacity-100 transition-opacity duration-[80ms]
                    hover:bg-[hsl(var(--primary)/0.3)] rounded-r-md"
             aria-hidden="true"></div>
      </div>
    </template>
  </div>

  {# ── Add Card ── #}
  <div class="relative flex justify-center mt-4">
    <button @click="showPicker = !showPicker"
            class="h-8 px-4 text-[13px] font-medium rounded-md
                   border-2 border-dashed border-[hsl(var(--border))]
                   text-[hsl(var(--muted-foreground))]
                   hover:border-[hsl(var(--primary))] hover:text-[hsl(var(--foreground))]
                   transition-colors duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
                   flex items-center gap-2">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
      Add Card
    </button>
    {% include 'workspace/_card_picker.html' %}
  </div>
</div>

{# Detail drawer (preserved unchanged) #}
<div id="dz-drawer-backdrop"
     class="fixed inset-0 z-40 bg-black/30 opacity-0 pointer-events-none transition-opacity duration-300"
     onclick="window.dzDrawer.close()"></div>
<aside id="dz-detail-drawer"
       class="fixed inset-y-0 right-0 z-50 flex flex-col w-full sm:max-w-2xl bg-[hsl(var(--background))] shadow-2xl translate-x-full transition-transform duration-300 ease-in-out">
  <div class="flex items-center justify-between px-4 py-3 border-b border-[hsl(var(--border))] shrink-0">
    <button class="h-8 px-3 rounded-[4px] text-[13px] font-medium text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))] flex items-center gap-1" onclick="window.dzDrawer.close()">
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      Close
    </button>
    <a id="dz-drawer-expand" href="#" class="h-8 px-3 rounded-[4px] text-[13px] font-medium text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))] flex items-center gap-1">
      Open full page
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
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

- [ ] **Step 2: Rewrite _card_picker.html**

Replace the entire contents of `src/dazzle_ui/templates/workspace/_card_picker.html` with:

```html
{# Card picker popover — lists available regions from the catalog #}
<div x-show="showPicker"
     x-transition:enter="transition duration-[140ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]"
     x-transition:enter-start="opacity-0 -translate-y-1"
     x-transition:enter-end="opacity-100 translate-y-0"
     x-transition:leave="transition duration-[80ms]"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0"
     @click.away="showPicker = false"
     class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-80
            bg-[hsl(var(--popover))] text-[hsl(var(--popover-foreground))]
            shadow-[0_4px_8px_rgb(0_0_0/0.08),0_2px_4px_rgb(0_0_0/0.04)]
            rounded-md border border-[hsl(var(--border))]
            p-3 z-50 max-h-64 overflow-y-auto">
  <h4 class="text-[12px] font-medium uppercase tracking-[0.04em] text-[hsl(var(--muted-foreground))] mb-2">Add a card</h4>
  <template x-for="item in catalog" :key="item.name">
    <button @click="addCard(item.name)"
            class="w-full text-left px-3 py-2 rounded-[4px]
                   hover:bg-[hsl(var(--muted))]
                   transition-colors duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
                   flex items-center gap-2 text-[13px]">
      <span class="px-1.5 py-0.5 rounded-[4px] bg-[hsl(var(--muted))] text-[11px] font-medium text-[hsl(var(--muted-foreground))]"
            x-text="item.display.toLowerCase()"></span>
      <span x-text="item.title" class="text-[hsl(var(--foreground))]"></span>
      <span class="text-[11px] text-[hsl(var(--muted-foreground))] ml-auto" x-text="item.entity"></span>
    </button>
  </template>
  <div x-show="catalog.length === 0" class="text-[13px] text-[hsl(var(--muted-foreground))] py-2">No widgets available.</div>
</div>
```

- [ ] **Step 3: Test the full dashboard in browser**

Open `ops_dashboard` workspace. Verify all functionality:
- Cards render with new chrome (no DaisyUI card/btn classes visible)
- Drag-and-drop works (pointer events)
- Resize works (col-span snaps)
- Save lifecycle (dirty → saving → saved → clean)
- Add card from picker
- Remove card on hover
- Cmd+S, Cmd+Z work
- Context selector still works (if applicable)
- Detail drawer still opens on row click in region tables
- Region content loads lazily via HTMX
- SSE updates work (if configured)

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/templates/workspace/_content.html src/dazzle_ui/templates/workspace/_card_picker.html
git commit -m "feat(dashboard): rewrite templates to pure Tailwind with spec-governed chrome

Removes all DaisyUI component classes (card, btn, badge, dropdown).
Uses design-system.css HSL variables for colours. Structural tokens
(spacing, radius, motion easing, density) frozen from Linear token sheet.
Card chrome follows ux-architect/components/card.md contract."
```

---

### Task 6: Run Quality Gates

**Files:** None (verification only)

- [ ] **Step 1: Start the verification app**

```bash
cd examples/ops_dashboard && dazzle serve --local
```

- [ ] **Step 2: Gate 1 — Drag threshold**

Click a card header without moving. Does it stay put? Drag 3px — still stays put. Drag 5px — does it lift with elevated shadow and 95% opacity?

Expected: Card does not move on click. Card lifts after 4px of pointer movement.

- [ ] **Step 3: Gate 2 — Drag performance**

Drag a card rapidly across the grid. Does it stay locked to the cursor without visual jank?

Expected: Card follows pointer at 60fps. No layout thrashing. Check browser DevTools Performance tab — no red frames during drag.

- [ ] **Step 4: Gate 3 — Save lifecycle**

Move a card. Does button change from "Saved" (grey, disabled) to "Save layout" (primary colour, enabled)? Click it. Does it show spinner → checkmark → back to "Saved"?

Expected: Full 5-state cycle visible. The "saved" checkmark shows for ~1200ms before reverting to "Saved".

- [ ] **Step 5: Gate 4 — Persistence boundary**

Move a card but don't save. Refresh the page. Does the layout revert to last saved state?

Expected: Layout reverts. Unsaved changes are not persisted.

- [ ] **Step 6: Gate 5 — Keyboard accessibility**

Tab to a card. Press Space. Use arrow keys to reorder. Press Enter. Does it stay in the new position? Does the save button become active?

Expected: Card reorders via keyboard. Screen reader should announce "Card moved to position N". Save button shows "Save layout".

- [ ] **Step 7: Record results and commit if all gates pass**

If any gate fails, identify which primitive phase is responsible (consult the relevant primitive spec) and fix before proceeding. Once all gates pass:

```bash
git add -A
git commit -m "chore(dashboard): verify quality gates pass

All 5 quality gates from ux-architect/components/dashboard-grid.md verified:
1. Drag threshold (4px) — PASS
2. Drag performance (transform-only) — PASS
3. Save lifecycle (5-state) — PASS
4. Persistence boundary (unsaved reverts) — PASS
5. Keyboard accessibility (Space+arrows) — PASS"
```

---

### Task 7: Clean Up and Final Verification

**Files:**
- Modify: `src/dazzle_ui/runtime/static/css/dz.css` (verify no stale references)

- [ ] **Step 1: Verify no remaining DaisyUI classes in dashboard templates**

```bash
rg "btn-|badge-|card-body|card-title|dropdown-|menu |base-100|base-200|base-300|rounded-box" src/dazzle_ui/templates/workspace/
```

Expected: No matches in `_content.html` or `_card_picker.html`. Region templates in `regions/` will still have DaisyUI classes — that's expected and correct (they're not spec-governed yet).

- [ ] **Step 2: Verify no remaining SortableJS references**

```bash
rg -i "sortable" src/dazzle_ui/runtime/static/ --type js --type css
```

Expected: No matches.

- [ ] **Step 3: Run existing tests to check for regressions**

```bash
pytest tests/ -m "not e2e" -x -q
```

Expected: All existing tests pass. The dashboard changes are template/JS-only so no Python tests should break.

- [ ] **Step 4: Run linter**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
```

- [ ] **Step 5: Final commit if any cleanup was needed**

```bash
git add -A
git commit -m "chore(dashboard): clean up stale references after rebuild"
```
