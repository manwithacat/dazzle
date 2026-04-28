/**
 * dashboard-builder.js — Alpine.js controller for spec-governed dashboards.
 *
 * Implements: ux-architect/components/dashboard-grid.md
 * Tokens: ux-architect/tokens/linear.md (structural only; colours via --dz-* CSS vars)
 * No external dependencies (SortableJS removed).
 *
 * Tasks 2+3+4: Core state + save lifecycle + drag + resize
 */
document.addEventListener("alpine:init", () => {
  Alpine.data("dzDashboardBuilder", () => ({
    // ── Data (from layout JSON data island) ──
    cards: [],
    catalog: [],
    workspaceName: "",
    // v0.61.1 (#864): count of above-fold cards hydrated from the layout
    // JSON. isEager() uses it to split hx-trigger between "load" (above
    // fold) and "intersect once" (below fold) — previously both triggers
    // fired for every card, doubling backend work on first paint.
    foldCount: 0,

    // ── UI state ──
    showPicker: false,
    saveState: "clean", // clean | dirty | saving | saved | error
    _saveError: "",
    undoStack: [],

    // ── Drag state (null when idle) ──
    drag: null,

    // ── Resize state (null when idle) ──
    resize: null,

    // ── Keyboard move/resize state ──
    _keyboardMoveCardId: null,
    _keyboardResizeCardId: null,
    _keyboardResizeOriginal: null,

    // ── Resize snap points ──
    _resizeSnaps: [3, 4, 6, 8, 12],

    // ── Timers ──
    _savedTimer: null,

    // ── Init ──
    init() {
      // Register keyboard + pointer listeners FIRST (issue #797): if the
      // layout-JSON parse below failed for any reason, the early return
      // used to skip listener installation entirely, leaving drag/resize
      // dead. Lifecycle is driven by the Alpine component, not the data
      // load, so decouple them.
      this._onKeydown = this._handleKeydown.bind(this);
      document.addEventListener("keydown", this._onKeydown);

      // Pointer drag/resize listeners live on window so they survive
      // mouse excursions outside the grid. We own the lifecycle
      // explicitly — using Alpine's @pointermove.window in the template
      // leaked the listener across HTMX morph navigations and threw
      // ReferenceError on the next move (same pattern as dzTable
      // issue #795).
      this._onPointerMove = (e) => {
        this.onPointerMoveDrag(e);
        this.onPointerMoveResize(e);
      };
      this._onPointerUp = (e) => {
        this.endDrag(e);
        this.endResize(e);
      };
      window.addEventListener("pointermove", this._onPointerMove);
      window.addEventListener("pointerup", this._onPointerUp);

      // Re-hydrate from the layout JSON island after any HTMX morph that
      // replaces the workspace content (#875). alpine:init only fires
      // once per component instance, but idiomorph keeps the existing
      // x-data="dzDashboardBuilder()" element across same-route nav
      // re-clicks — so init() doesn't re-run, and cards/catalog stay
      // stale while the data island below has been replaced with fresh
      // JSON. Listen for htmx:afterSettle (NOT afterSwap) — with the
      // morph: extension, afterSwap fires before idiomorph has fully
      // committed child-node textContent, so reading the
      // #dz-workspace-layout <script> too early returns stale JSON and
      // hydrates an empty cards array (#919). afterSettle fires once
      // all DOM mutations + textContent updates are visible.
      this._onHtmxAfterSettle = (e) => {
        const target = e && e.detail && e.detail.target;
        if (!target) return;
        // Only re-hydrate when the swap target contains our data island
        // — avoids work on every region card swap.
        const island = target.querySelector
          ? target.querySelector("#dz-workspace-layout")
          : null;
        if (!island) return;
        this._hydrateFromLayout();
      };
      document.body.addEventListener(
        "htmx:afterSettle",
        this._onHtmxAfterSettle,
      );

      this._hydrateFromLayout();
    },

    _hydrateFromLayout() {
      const el = document.getElementById("dz-workspace-layout");
      if (!el) return;
      try {
        const data = JSON.parse(el.textContent);
        this.cards = data.cards || [];
        this.catalog = data.catalog || [];
        this.workspaceName = data.workspace_name || "";
        this.foldCount = Number.isInteger(data.fold_count)
          ? data.fold_count
          : 0;
        // Reset transient UI state so the multi-state saveState labels
        // don't stack visibly after a re-entry morph (#875). Any pending
        // saved-banner timer is cancelled because the workspace just
        // re-hydrated from server truth.
        this.saveState = "clean";
        this.undoStack = [];
        if (this._savedTimer) {
          clearTimeout(this._savedTimer);
          this._savedTimer = null;
        }
      } catch {
        // Leave listeners in place — the user can still drag / keyboard-
        // edit a stale layout even if the JSON payload was malformed.
      }
    },

    destroy() {
      if (this._onKeydown) {
        document.removeEventListener("keydown", this._onKeydown);
        this._onKeydown = null;
      }
      if (this._onPointerMove) {
        window.removeEventListener("pointermove", this._onPointerMove);
        this._onPointerMove = null;
      }
      if (this._onPointerUp) {
        window.removeEventListener("pointerup", this._onPointerUp);
        this._onPointerUp = null;
      }
      if (this._onHtmxAfterSettle) {
        document.body.removeEventListener(
          "htmx:afterSettle",
          this._onHtmxAfterSettle,
        );
        this._onHtmxAfterSettle = null;
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

      // v0.57.62's CI diagnostic proved the cause of the region-
      // fetch silence: inside a single $nextTick the x-for template
      // has NOT yet inserted the new card — `this.$el.querySelector`
      // returns null, so htmx.process + htmx.ajax never run. Alpine
      // needs multiple frames before x-for finishes DOM insertion
      // and :hx-get / :id bindings have been evaluated.
      //
      // Fix: poll via requestAnimationFrame up to ~500ms for both
      // the wrapper (data-card-id) AND the body slot (computed id
      // matches Alpine's :id="'region-' + card.region + '-' + card.id").
      // Once both exist, htmx.process registers the new subtree and
      // htmx.ajax fires the region fetch explicitly (not relying on
      // hx-trigger="load" which the de-duping MutationObserver may
      // have already consumed before bindings were live).
      if (!this.workspaceName) return;
      const bodyId = "region-" + regionName + "-" + nextId;
      const url =
        "/api/workspaces/" + this.workspaceName + "/regions/" + regionName;

      let attempts = 0;
      const maxAttempts = 30; // ~500ms at 60fps
      const tryFetch = () => {
        attempts += 1;
        const cardEl = document.querySelector(
          '[data-card-id="' + nextId + '"]',
        );
        const bodyEl = document.getElementById(bodyId);
        if (!cardEl || !bodyEl) {
          if (attempts < maxAttempts) {
            requestAnimationFrame(tryFetch);
          } else {
            console.log(
              "[dz-addcard] giving up after " +
                attempts +
                " frames, cardEl=" +
                !!cardEl +
                " bodyEl=" +
                !!bodyEl,
            );
          }
          return;
        }
        if (typeof htmx !== "undefined") {
          htmx.process(cardEl);
          htmx.ajax("GET", url, {
            target: "#" + bodyId,
            swap: "innerHTML",
          });
        }
      };
      requestAnimationFrame(tryFetch);
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
      // Escape during drag — cancel
      if (e.key === "Escape" && this.drag) {
        e.preventDefault();
        this.cancelDrag();
      }
      // Escape during resize — cancel
      if (e.key === "Escape" && this.resize) {
        e.preventDefault();
        this.cancelResize();
      }
    },

    // ── Drag ──
    startDrag(cardId, e) {
      console.log(
        "[dz-drag] startDrag fired cardId=" +
          cardId +
          " button=" +
          e.button +
          " pointerType=" +
          e.pointerType,
      );
      if (e.button && e.button !== 0) return; // left click only
      e.preventDefault();
      // Query `document` not `this.$el` — when this method is called
      // from `@pointerdown="startDrag(...)"` on the drag handle,
      // Alpine's `$el` magic resolves to the handle element (where the
      // directive lives), not the component root. The card wrapper is
      // an ANCESTOR of the handle, so handle.querySelector for the
      // wrapper always returns null. v0.57.64 CI log line
      // "[dz-drag] startDrag: cardEl NOT FOUND for card-0" pinpointed
      // this. Same bug class that killed addCard before #798 fix.
      const cardEl = document.querySelector('[data-card-id="' + cardId + '"]');
      if (!cardEl) {
        console.log("[dz-drag] startDrag: cardEl NOT FOUND for " + cardId);
        return;
      }

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

      this._dragPointerId = e.pointerId;
      console.log(
        "[dz-drag] drag state set, startY=" +
          e.clientY +
          " placeholderIndex=" +
          this.drag.placeholderIndex,
      );
      // Note: we do NOT use setPointerCapture here — it would route
      // pointermove events to the card element instead of window,
      // breaking our @pointermove.window handler on the grid container.
    },

    onPointerMoveDrag(e) {
      if (!this.drag) return;

      // Update cursor position via top-level assignment so Alpine's
      // :style binding on the card (which reads drag.currentX/Y
      // through dragTransform) re-evaluates. Nested-property
      // mutation (this.drag.currentX = ...) can be missed by the
      // effect tree under certain Alpine configurations — pinning
      // reactivity to the top-level `this.drag` write is defensive
      // and costs one object spread per move (issue #797).
      let nextDrag = {
        ...this.drag,
        currentX: e.clientX,
        currentY: e.clientY,
      };

      // Phase transition: pressed → dragging (4px threshold)
      if (nextDrag.phase === "pressed") {
        const dx = e.clientX - nextDrag.startX;
        const dy = e.clientY - nextDrag.startY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 4) {
          this.drag = nextDrag;
          return;
        }
        console.log(
          "[dz-drag] phase transition pressed→dragging, dist=" +
            dist.toFixed(1),
        );
        this._pushUndo();
        nextDrag = { ...nextDrag, phase: "dragging" };
        document.body.classList.add("select-none");
      }

      this.drag = nextDrag;
      if (this.drag.phase !== "dragging") return;

      // Find which card the pointer is over (by midpoint comparison).
      // Query `document` not `this.$el` for the same Alpine `$el`
      // scope reason documented in startDrag — this callback runs via
      // the window `pointermove` listener installed in init, not via
      // a directive, so `this.$el` resolution is unreliable.
      const grid = document.querySelector("[data-grid-container]");
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
            (c) => c.id === wrapper.dataset.cardId,
          );
          if (cardIndex >= 0) targetIndex = cardIndex + 1;
        }
      });

      // Move placeholder in array if position changed
      if (targetIndex !== this.drag.placeholderIndex) {
        console.log(
          "[dz-drag] reorder " +
            this.drag.placeholderIndex +
            " → " +
            targetIndex +
            " (wrappers=" +
            wrappers.length +
            ")",
        );
        const card = this.cards.find((c) => c.id === this.drag.cardId);
        if (card) {
          const filtered = this.cards.filter((c) => c.id !== this.drag.cardId);
          filtered.splice(Math.min(targetIndex, filtered.length), 0, card);
          this.cards = filtered;
          this.drag.placeholderIndex = this.cards.findIndex(
            (c) => c.id === this.drag.cardId,
          );
        }
      }
    },

    endDrag(e) {
      if (!this.drag) return;
      const wasDragging = this.drag.phase === "dragging";
      console.log(
        "[dz-drag] endDrag wasDragging=" +
          wasDragging +
          " finalIndex=" +
          this.drag.placeholderIndex,
      );
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

    // ── Keyboard card move (Space to enter, arrows to move, Enter/Esc to exit) ──
    toggleKeyboardMove(cardId) {
      if (this._keyboardMoveCardId === cardId) {
        this._keyboardMoveCardId = null;
        this._announce("Move mode exited");
        return;
      }
      this._keyboardMoveCardId = cardId;
      this._announce(
        "Move mode. Use arrow keys to reorder. Enter to confirm, Escape to cancel.",
      );
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
      if (e.key === "ArrowDown" && idx < this.cards.length - 1)
        newIdx = idx + 1;

      if (newIdx !== idx) {
        e.preventDefault();
        this._pushUndo();
        const [card] = this.cards.splice(idx, 1);
        this.cards.splice(newIdx, 0, card);
        this._markDirty();
        this._announce("Card moved to position " + (newIdx + 1));

        // Re-focus the card after Alpine re-renders
        this.$nextTick(() => {
          const el = document.querySelector('[data-card-id="' + cardId + '"]');
          if (el) el.focus();
        });
      }
    },

    // ── Resize ──
    startResize(cardId, e) {
      if (e.button && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const grid = document.querySelector("[data-grid-container]");
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

      // No setPointerCapture — we use @pointermove.window on the grid container
      document.body.classList.add("select-none");
      document.body.style.cursor = "col-resize";
    },

    onPointerMoveResize(e) {
      if (!this.resize) return;

      const card = this.cards.find((c) => c.id === this.resize.cardId);
      if (!card) return;

      // Find the card element's left edge
      const cardEl = document.querySelector(
        '[data-card-id="' + this.resize.cardId + '"]',
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
      const resizedCardId = this.resize.cardId;
      this.resize = null;
      document.body.classList.remove("select-none");
      document.body.style.cursor = "";

      if (changed) {
        this._markDirty();
        const card = this.cards.find((c) => c.id === resizedCardId);
        this._announce(
          "Card resized to " + (card ? card.col_span : "") + " columns",
        );
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
          card.col_span +
          " columns.",
      );
    },

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
        if (
          this._keyboardResizeOriginal !== null &&
          card.col_span !== this._keyboardResizeOriginal
        ) {
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

    // ── Helpers ──
    _colSpanClass(span) {
      const s = Math.min(Math.max(span, 3), 12);
      return "grid-column: span " + s + " / span " + s;
    },

    /**
     * v0.61.1 (#864): return True when `card` is above the fold and
     * should use the eager `hx-trigger="load"`. Below-fold cards use
     * `intersect once` only — combining the two triggers previously
     * double-fetched every above-fold region on first paint.
     *
     * row_order is the authoritative fold position (index in the sorted
     * card list). Falls back to True when foldCount is 0 to preserve
     * the pre-fix behaviour for legacy workspaces.
     */
    isEagerCard(card) {
      if (!this.foldCount) return true;
      return (card.row_order ?? 0) < this.foldCount;
    },

    /**
     * Build the hx-trigger expression for one card (#864). SSE triggers
     * always append; the load/intersect split is the only decision.
     */
    cardHxTrigger(card, sseEnabled) {
      const base = this.isEagerCard(card) ? "load" : "intersect once";
      if (!sseEnabled) return base;
      return (
        base + ", sse:entity.created, sse:entity.updated, sse:entity.deleted"
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
  }));
});
