/**
 * dashboard-builder.js — vanilla controller for spec-governed dashboards
 * (Tier F4e: converted from the dzDashboardBuilder Alpine island; a
 * factory per [data-dz-dashboard-builder] root, mounted at load and
 * after htmx settles).
 *
 * #948 server-render migration: cards are server-rendered HTML via
 * `<div class="dz-card-wrapper" data-card-id="..." data-card-region="..."
 * data-card-col-span="...">`. Alpine no longer projects from a JSON
 * island; the DOM is the source of truth for layout. The reactive
 * surface contracts to ephemeral state only:
 *
 *   - `drag`: mid-flight pointer state during card drag
 *   - `resize`: mid-flight pointer state during card resize
 *   - `saveState`: clean | dirty | saving | saved | error
 *   - `_saveError`: error string for the Save button title attr
 *   - `showPicker`: add-card picker visibility
 *   - `_keyboardMoveCardId` / `_keyboardResizeCardId` / `_keyboardResizeOriginal`
 *   - `undoStack`: list of undo operations (DOM-snapshot, not array)
 *
 * The cards array, catalog reactive list, workspaceName, foldCount,
 * and `_hydrateFromLayout()` from the cycle 936/945 architecture are
 * all gone — the morph-staleness bug class (#945) can't manifest
 * without a reactive cards array. The destroy+init handler in
 * dz-alpine.js stays as defense-in-depth for the picker / save-state.
 *
 * Card events are wired via delegation on the grid container so that
 * dynamically-added cards (addCard, undo) work without re-init.
 *
 * Implements: ux-architect/components/dashboard-grid.md
 */
function createDzDashboardBuilder(root) {
  // Tier F4e: plain factory (was Alpine.data("dzDashboardBuilder")).
  // State is in the DOM: `showPicker`/`saveState` are accessor
  // properties (defined after the literal) whose setters mirror to
  // `data-show-picker` on the root and `data-dz-save-state` on the
  // save button — CSS drives the picker + toolbar-span visibility.
  const builder = {
    // ── Ephemeral UI state (backing fields for the accessors) ──
    _showPicker: false,
    _saveState: "clean", // clean | dirty | saving | saved | error
    _saveError: "",
    undoStack: [],

    // Mid-flight pointer state (null when idle)
    drag: null,
    resize: null,

    // Keyboard move/resize state
    _keyboardMoveCardId: null,
    _keyboardResizeCardId: null,
    _keyboardResizeOriginal: null,

    // Resize snap points (in 12-col grid)
    _resizeSnaps: [3, 4, 6, 8, 12],

    // Timers
    _savedTimer: null,

    // Listener handles (for explicit cleanup in destroy())
    _onKeydown: null,
    _onPointerMove: null,
    _onPointerUp: null,
    _onGridPointerDown: null,
    _onGridClick: null,
    _onGridKeydown: null,

    // ── Init / destroy ──
    init() {
      this._onKeydown = this._handleKeydown.bind(this);
      document.addEventListener("keydown", this._onKeydown);

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

      // Event delegation on the grid container so cards added at
      // runtime (addCard, undo) automatically get drag/resize/click
      // handling without re-init. The cards themselves are pure
      // server-rendered HTML — no Alpine `@` directives on them.
      this._onGridPointerDown = (e) => {
        const dragHandle = e.target.closest(
          '[data-test-id="dz-card-drag-handle"]',
        );
        const resizeHandle = e.target.closest(".dz-card-resize");
        if (dragHandle) {
          const cardEl = dragHandle.closest("[data-card-id]");
          if (cardEl) this.startDrag(cardEl, e);
        } else if (resizeHandle) {
          const cardEl = resizeHandle.closest("[data-card-id]");
          if (cardEl) this.startResize(cardEl, e);
        }
      };
      this._onGridClick = (e) => {
        const removeBtn = e.target.closest('[data-test-id="dz-card-remove"]');
        if (removeBtn) {
          e.stopPropagation();
          const cardEl = removeBtn.closest("[data-card-id]");
          if (cardEl) this.removeCard(cardEl);
        }
      };
      this._onGridKeydown = (e) => {
        const cardEl = e.target.closest("[data-card-id]");
        if (cardEl) this.handleCardKeydown(cardEl, e);
      };

      const grid = document.querySelector("[data-grid-container]");
      if (grid) {
        grid.addEventListener("pointerdown", this._onGridPointerDown);
        grid.addEventListener("click", this._onGridClick);
        grid.addEventListener("keydown", this._onGridKeydown);
      }

      // #982: mirror showPicker to a data attribute on the workspace
      // root + drive picker visibility from CSS. Pre-fix the picker
      // div (a deep descendant of `x-data="dzDashboardBuilder()"`)
      // bound `x-show="showPicker"` and `@click.away="showPicker = false"`;
      // on htmx morph idiomorph re-evaluated those bindings before
      // Alpine re-established the parent scope, throwing
      // "showPicker is not defined" — fourth ADR-0022 instance after
      // #970 / #972 / #978. Same cure: data-attribute + CSS.
      root.dataset.showPicker = this._showPicker ? "1" : "";

      // Toolbar + add-card delegation (replaces the Alpine @click
      // bindings): one listener on the root.
      this._onActionClick = (e) => {
        const btn = e.target.closest("[data-dz-action]");
        if (!btn || !root.contains(btn)) return;
        const action = btn.getAttribute("data-dz-action");
        if (action === "reset") this.resetLayout();
        else if (action === "save") this.save();
        else if (action === "toggle-picker") this.showPicker = !this.showPicker;
      };
      // picker entries carry data-dz-add-region (was an Alpine @click)
      this._onAddRegionClick = (e) => {
        const entry = e.target.closest("[data-dz-add-region]");
        if (!entry || !root.contains(entry)) return;
        this.addCard(entry.getAttribute("data-dz-add-region"));
      };
      root.addEventListener("click", this._onAddRegionClick);
      root.addEventListener("click", this._onActionClick);

      // Click-outside handler for the picker. Replaces the pre-fix
      // `@click.away="showPicker = false"` Alpine binding which evaluated
      // its expression on a child of the morphable subtree. This handler
      // checks the click target against the picker + the toggle button
      // (so clicking the toggle doesn't immediately close what it just
      // opened) and toggles `this.showPicker = false` when the click
      // lands outside both. Detached in destroy().
      this._onPickerClickOutside = (e) => {
        if (!this.showPicker) return;
        const picker = root.querySelector(".dz-card-picker");
        const toggle = root.querySelector(
          '[data-test-id="dz-add-card-trigger"]',
        );
        if (picker && picker.contains(e.target)) return;
        if (toggle && toggle.contains(e.target)) return;
        this.showPicker = false;
      };
      document.addEventListener("click", this._onPickerClickOutside);
    },

    destroy() {
      if (this._onActionClick) {
        root.removeEventListener("click", this._onActionClick);
        this._onActionClick = null;
      }
      if (this._onAddRegionClick) {
        root.removeEventListener("click", this._onAddRegionClick);
        this._onAddRegionClick = null;
      }
      if (this._onKeydown) {
        document.removeEventListener("keydown", this._onKeydown);
        this._onKeydown = null;
      }
      if (this._onPickerClickOutside) {
        document.removeEventListener("click", this._onPickerClickOutside);
        this._onPickerClickOutside = null;
      }
      if (this._onPointerMove) {
        window.removeEventListener("pointermove", this._onPointerMove);
        this._onPointerMove = null;
      }
      if (this._onPointerUp) {
        window.removeEventListener("pointerup", this._onPointerUp);
        this._onPointerUp = null;
      }
      const grid = document.querySelector("[data-grid-container]");
      if (grid) {
        if (this._onGridPointerDown) {
          grid.removeEventListener("pointerdown", this._onGridPointerDown);
          this._onGridPointerDown = null;
        }
        if (this._onGridClick) {
          grid.removeEventListener("click", this._onGridClick);
          this._onGridClick = null;
        }
        if (this._onGridKeydown) {
          grid.removeEventListener("keydown", this._onGridKeydown);
          this._onGridKeydown = null;
        }
      }
    },

    // ── DOM helpers ──
    _allCards() {
      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return [];
      return Array.from(grid.querySelectorAll("[data-card-id]"));
    },

    _cardById(cardId) {
      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return null;
      return grid.querySelector('[data-card-id="' + cardId + '"]');
    },

    _cardIndex(cardEl) {
      const all = this._allCards();
      return all.indexOf(cardEl);
    },

    _cardSpan(cardEl) {
      return parseInt(cardEl.getAttribute("data-card-col-span"), 10) || 6;
    },

    _setCardSpan(cardEl, span) {
      cardEl.setAttribute("data-card-col-span", String(span));
      cardEl.style.gridColumn = "span " + span + " / span " + span;
    },

    _workspaceName() {
      const root = document.querySelector("[data-workspace-name]");
      return root ? root.getAttribute("data-workspace-name") : "";
    },

    _catalog() {
      // Catalog is a JSON blob on the picker — only consumed at
      // open-picker time, so it doesn't need to be reactive.
      const el = document.querySelector("[data-card-catalog]");
      if (!el) return [];
      try {
        return JSON.parse(el.getAttribute("data-card-catalog") || "[]");
      } catch {
        return [];
      }
    },

    // ── Save lifecycle ──
    _markDirty() {
      if (this.saveState !== "dirty") {
        this.saveState = "dirty";
      }
    },

    async save() {
      if (this.saveState !== "dirty" && this.saveState !== "error") return;
      this.saveState = "saving";

      const cards = this._allCards().map((el, i) => ({
        id: el.getAttribute("data-card-id"),
        region: el.getAttribute("data-card-region"),
        col_span: this._cardSpan(el),
        row_order: i,
      }));
      const layout = { version: 2, cards };
      const wsName = this._workspaceName();
      const key = "workspace." + wsName + ".layout";
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
        // _saveError first — the saveState setter mirrors it into the
        // save button's title.
        this._saveError = err.message || "Failed to save";
        this.saveState = "error";
      }
    },

    resetLayout() {
      if (this.saveState === "dirty" && !confirm("Discard unsaved changes?")) {
        return;
      }
      const wsName = this._workspaceName();
      if (!wsName) return;
      const key = "workspace." + wsName + ".layout";
      fetch("/auth/preferences/" + encodeURIComponent(key), {
        method: "DELETE",
      }).then(() => location.reload());
    },

    // ── Card management ──
    addCard(regionName) {
      const wsName = this._workspaceName();
      if (!wsName) return;
      const catalog = this._catalog();
      const entry = catalog.find((c) => c.name === regionName);
      if (!entry) return;

      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return;

      const newId = "card-" + Date.now();
      const cardEl = this._buildCardElement(
        {
          id: newId,
          region: regionName,
          title: entry.title || regionName,
          col_span: 6,
          display: entry.display || "list",
        },
        wsName,
      );

      grid.appendChild(cardEl);
      this._pushUndo({ type: "add", cardId: newId });

      if (typeof htmx !== "undefined") {
        htmx.process(cardEl);
        const bodyEl = cardEl.querySelector(".dz-card-body");
        if (bodyEl) {
          // #1494: mark this as a picker-added card so the server skips the
          // `when_empty` auto self-demote default — a user who explicitly adds
          // a card should see its empty-state, not have it immediately collapse.
          htmx.ajax(
            "GET",
            "/api/workspaces/" + wsName + "/regions/" + regionName + "?added=1",
            { target: "#" + bodyEl.id, swap: "innerHTML" },
          );
        }
      }
      this.showPicker = false;
      this._markDirty();
    },

    removeCard(cardEl) {
      // Capture a structured snapshot for undo. We rebuild from
      // attributes rather than serialising outerHTML — innerHTML
      // round-trips can pick up cross-site script payloads from
      // user-supplied content (cycle 942 had a similar concern with
      // panel_html). All card content is server-rendered initially,
      // so the data attributes are the trustworthy source of truth.
      const titleEl = cardEl.querySelector(".dz-card-title");
      const snapshot = {
        type: "remove",
        index: this._cardIndex(cardEl),
        card: {
          id: cardEl.getAttribute("data-card-id"),
          region: cardEl.getAttribute("data-card-region"),
          col_span: this._cardSpan(cardEl),
          title: titleEl
            ? titleEl.textContent
            : cardEl.getAttribute("data-card-region"),
        },
      };
      this._pushUndo(snapshot);
      cardEl.remove();
      this._markDirty();
    },

    _buildCardElement(card, wsName) {
      // Build a card DOM tree using safe DOM methods (no innerHTML)
      // so the title and any project-controlled fields can't smuggle
      // markup. The chrome shape mirrors the server-rendered template
      // in `workspace/_content.html`. Drag/resize/remove handlers
      // reach this card via delegation on the grid container, so no
      // per-card listener wiring is needed here.
      const wrapper = document.createElement("div");
      wrapper.setAttribute("data-card-id", card.id);
      wrapper.setAttribute("data-card-region", card.region);
      wrapper.setAttribute("data-card-col-span", String(card.col_span));
      wrapper.setAttribute("tabindex", "0");
      wrapper.className = "dz-card-wrapper";
      wrapper.style.gridColumn =
        "span " + card.col_span + " / span " + card.col_span;

      const article = document.createElement("article");
      article.className = "dz-card";
      article.setAttribute("role", "article");

      const header = document.createElement("div");
      header.className = "dz-card-header";
      header.setAttribute("data-test-id", "dz-card-drag-handle");

      const titles = document.createElement("div");
      titles.className = "dz-card-titles";
      const titleH3 = document.createElement("h3");
      titleH3.className = "dz-card-title";
      titleH3.textContent = card.title;
      titles.appendChild(titleH3);
      header.appendChild(titles);

      // #1204: edit-mode chrome is permission-gated. Mirror the server-
      // side `_emit_dashboard_card` gate by reading `data-grid-editable`
      // on the grid container — set by `_emit_dashboard_grid_impl` from
      // `DashboardGrid.edit_enabled`. When the grid is not editable we
      // omit the dz-card-actions div entirely (no hover-flash, no a11y
      // tab target, no surprise screen-reader click).
      const grid = document.querySelector("[data-grid-container]");
      const gridEditable =
        grid && grid.getAttribute("data-grid-editable") === "true";
      if (gridEditable) {
        const actions = document.createElement("div");
        actions.className = "dz-card-actions";
        const removeBtn = document.createElement("button");
        removeBtn.setAttribute("data-test-id", "dz-card-remove");
        removeBtn.setAttribute("aria-label", "Remove card");
        removeBtn.className = "dz-card-action-button";
        removeBtn.textContent = "×";
        actions.appendChild(removeBtn);
        header.appendChild(actions);
      }

      article.appendChild(header);

      const body = document.createElement("div");
      body.className = "dz-card-body";
      body.id = "region-" + card.region + "-" + card.id;
      // #962: data-display drives the per-mode min-height reservation in dashboard.css
      body.setAttribute("data-display", (card.display || "list").toLowerCase());
      body.setAttribute(
        "hx-get",
        "/api/workspaces/" + wsName + "/regions/" + card.region,
      );
      body.setAttribute("hx-trigger", "load");
      body.setAttribute("hx-swap", "innerHTML");

      const skeleton = document.createElement("div");
      skeleton.className = "dz-card-skeleton";
      ["w-3-4", "is-thin", "is-thin w-5-6"].forEach((cls) => {
        const line = document.createElement("div");
        line.className = "dz-card-skeleton-line " + cls;
        skeleton.appendChild(line);
      });
      body.appendChild(skeleton);
      article.appendChild(body);

      wrapper.appendChild(article);

      const resize = document.createElement("div");
      resize.className = "dz-card-resize";
      resize.setAttribute("aria-hidden", "true");
      wrapper.appendChild(resize);

      return wrapper;
    },

    // ── Undo ──
    _pushUndo(op) {
      this.undoStack.push(op);
      if (this.undoStack.length > 20) this.undoStack.shift();
    },

    undo() {
      const op = this.undoStack.pop();
      if (!op) return;
      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return;

      if (op.type === "add") {
        const cardEl = this._cardById(op.cardId);
        if (cardEl) cardEl.remove();
      } else if (op.type === "remove") {
        // Rebuild from the structured snapshot rather than from a
        // serialised HTML string. Defends against any drift if the
        // template shape changes between snapshot and undo.
        const wsName = this._workspaceName();
        const cardEl = this._buildCardElement(op.card, wsName);
        const refNode = grid.children[op.index] || null;
        grid.insertBefore(cardEl, refNode);
        if (typeof htmx !== "undefined") htmx.process(cardEl);
      } else if (op.type === "reorder") {
        const cardEl = this._cardById(op.cardId);
        if (cardEl) {
          const refNode = grid.children[op.fromIndex] || null;
          grid.insertBefore(cardEl, refNode);
        }
      } else if (op.type === "resize") {
        const cardEl = this._cardById(op.cardId);
        if (cardEl) this._setCardSpan(cardEl, op.fromSpan);
      }
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

    handleCardKeydown(cardEl, e) {
      const cardId = cardEl.getAttribute("data-card-id");

      // Space toggles keyboard move; Enter confirms move
      if (e.key === " " || e.key === "Enter") {
        if (e.key === " ") {
          e.preventDefault();
          this._toggleKeyboardMove(cardId);
        } else if (this._keyboardMoveCardId === cardId) {
          e.preventDefault();
          this._keyboardMoveCardId = null;
          this._announce("Position confirmed");
        }
        return;
      }

      // Escape exits move mode
      if (e.key === "Escape") {
        if (this._keyboardMoveCardId === cardId) {
          e.preventDefault();
          this._keyboardMoveCardId = null;
          this._announce("Move cancelled");
          return;
        }
      }

      // Arrow keys — move (when in keyboard-move mode)
      if (this._keyboardMoveCardId === cardId) {
        const idx = this._cardIndex(cardEl);
        let newIdx = idx;
        if (e.key === "ArrowUp" && idx > 0) newIdx = idx - 1;
        if (e.key === "ArrowDown" && idx < this._allCards().length - 1) {
          newIdx = idx + 1;
        }
        if (newIdx !== idx) {
          e.preventDefault();
          this._pushUndo({ type: "reorder", cardId, fromIndex: idx });
          const grid = document.querySelector("[data-grid-container]");
          if (grid) {
            // To move down: insert before the (newIdx+1)th element
            // so we land in the (newIdx)th slot. To move up: insert
            // before the (newIdx)th. The +1 adjustment for downward
            // moves accounts for the dragged element occupying its
            // current slot before the reorder.
            const refNode =
              newIdx > idx
                ? grid.children[newIdx + 1] || null
                : grid.children[newIdx];
            grid.insertBefore(cardEl, refNode);
          }
          this._markDirty();
          this._announce("Card moved to position " + (newIdx + 1));
          // Restore focus after the move
          requestAnimationFrame(() => cardEl.focus());
        }
        return;
      }

      // 'r' — toggle keyboard resize mode
      if (e.key === "r" || e.key === "R") {
        this._toggleKeyboardResize(cardEl);
        return;
      }

      // Resize mode: arrows change col_span via snap points
      if (this._keyboardResizeCardId === cardId) {
        this._handleResizeArrow(cardEl, e);
      }
    },

    _toggleKeyboardMove(cardId) {
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

    _toggleKeyboardResize(cardEl) {
      const cardId = cardEl.getAttribute("data-card-id");
      if (this._keyboardResizeCardId === cardId) {
        this._keyboardResizeCardId = null;
        this._announce("Resize mode exited");
        return;
      }
      this._keyboardResizeCardId = cardId;
      this._announce(
        "Resize mode. Left/Right arrow to change width. Enter to confirm, Escape to cancel. Current: " +
          this._cardSpan(cardEl) +
          " columns.",
      );
    },

    _handleResizeArrow(cardEl, e) {
      const cardId = cardEl.getAttribute("data-card-id");

      if (e.key === "Escape") {
        e.preventDefault();
        if (this._keyboardResizeOriginal !== null) {
          this._setCardSpan(cardEl, this._keyboardResizeOriginal);
        }
        this._keyboardResizeCardId = null;
        this._keyboardResizeOriginal = null;
        this._announce("Resize cancelled");
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        const span = this._cardSpan(cardEl);
        if (
          this._keyboardResizeOriginal !== null &&
          span !== this._keyboardResizeOriginal
        ) {
          this._pushUndo({
            type: "resize",
            cardId,
            fromSpan: this._keyboardResizeOriginal,
          });
          this._markDirty();
        }
        this._keyboardResizeCardId = null;
        this._keyboardResizeOriginal = null;
        this._announce("Resize confirmed: " + span + " columns");
        return;
      }

      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const currentSpan = this._cardSpan(cardEl);
        if (this._keyboardResizeOriginal === null) {
          this._keyboardResizeOriginal = currentSpan;
        }
        const snaps = this._resizeSnaps;
        const currentIdx = snaps.indexOf(currentSpan);
        let newIdx = currentIdx;
        if (e.key === "ArrowRight" && currentIdx < snaps.length - 1) newIdx++;
        if (e.key === "ArrowLeft" && currentIdx > 0) newIdx--;
        if (newIdx !== currentIdx) {
          this._setCardSpan(cardEl, snaps[newIdx]);
          this._announce(snaps[newIdx] + " columns");
        }
      }
    },

    // ── Drag (pointer) ──
    startDrag(cardEl, e) {
      if (e.button && e.button !== 0) return;
      e.preventDefault();
      const rect = cardEl.getBoundingClientRect();
      this.drag = {
        cardId: cardEl.getAttribute("data-card-id"),
        startX: e.clientX,
        startY: e.clientY,
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        width: rect.width,
        height: rect.height,
        currentX: e.clientX,
        currentY: e.clientY,
        phase: "pressed",
        originalIndex: this._cardIndex(cardEl),
      };
    },

    onPointerMoveDrag(e) {
      if (!this.drag) return;
      const drag = this.drag;
      drag.currentX = e.clientX;
      drag.currentY = e.clientY;

      // Phase transition: pressed → dragging (4px threshold)
      if (drag.phase === "pressed") {
        const dx = e.clientX - drag.startX;
        const dy = e.clientY - drag.startY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 4) return;
        drag.phase = "dragging";
        document.body.classList.add("select-none");
        this._pushUndo({
          type: "reorder",
          cardId: drag.cardId,
          fromIndex: drag.originalIndex,
        });
      }

      if (drag.phase !== "dragging") return;

      // Apply transform directly to the dragged card (no reactive
      // binding; same CSS shape as the cycle 2a `dragTransform()`
      // helper — this is just imperative instead of declarative).
      this._applyDragTransform();

      // Reorder DOM if pointer crossed a sibling's midpoint
      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return;
      const dragEl = this._cardById(drag.cardId);
      if (!dragEl) return;

      const wrappers = this._allCards();
      let targetIndex = wrappers.indexOf(dragEl);
      wrappers.forEach((wrapper, i) => {
        if (wrapper === dragEl) return;
        const rect = wrapper.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        if (e.clientY > midY) {
          targetIndex = i + 1;
        }
      });

      const currentIndex = wrappers.indexOf(dragEl);
      if (targetIndex !== currentIndex) {
        let ref;
        if (targetIndex >= wrappers.length) {
          ref = null;
        } else {
          ref = wrappers[targetIndex] || null;
          // Skip past the dragged element if it lands at the ref
          if (ref === dragEl) ref = wrappers[targetIndex + 1] || null;
        }
        grid.insertBefore(dragEl, ref);
      }
    },

    _applyDragTransform() {
      if (!this.drag || this.drag.phase !== "dragging") return;
      const cardEl = this._cardById(this.drag.cardId);
      if (!cardEl) return;
      const x = this.drag.currentX - this.drag.offsetX;
      const y = this.drag.currentY - this.drag.offsetY;
      cardEl.style.cssText =
        "position:fixed;left:0;top:0;width:" +
        this.drag.width +
        "px;height:" +
        this.drag.height +
        "px;transform:translate(" +
        x +
        "px," +
        y +
        "px) scale(1.02);z-index:500;opacity:0.95;pointer-events:none;" +
        "box-shadow:0 12px 24px rgb(0 0 0/0.12),0 4px 8px rgb(0 0 0/0.06);";
    },

    endDrag(_e) {
      if (!this.drag) return;
      const wasDragging = this.drag.phase === "dragging";
      const cardEl = this._cardById(this.drag.cardId);
      if (cardEl) {
        // Restore default styling, restore grid-column.
        cardEl.style.cssText = "";
        this._setCardSpan(cardEl, this._cardSpan(cardEl));
      }
      this.drag = null;
      document.body.classList.remove("select-none");

      if (wasDragging) {
        this._markDirty();
        this._announce("Card moved");
      }
    },

    cancelDrag() {
      if (!this.drag) return;
      const cardEl = this._cardById(this.drag.cardId);
      if (cardEl) {
        cardEl.style.cssText = "";
        this._setCardSpan(cardEl, this._cardSpan(cardEl));
      }
      // Pop the undo to restore the original position
      if (this.drag.phase === "dragging" && this.undoStack.length > 0) {
        this.undo();
      }
      this.drag = null;
      document.body.classList.remove("select-none");
    },

    // ── Resize (pointer) ──
    startResize(cardEl, e) {
      if (e.button && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const grid = document.querySelector("[data-grid-container]");
      if (!grid) return;

      const startSpan = this._cardSpan(cardEl);
      this._pushUndo({
        type: "resize",
        cardId: cardEl.getAttribute("data-card-id"),
        fromSpan: startSpan,
      });

      const gridRect = grid.getBoundingClientRect();
      this.resize = {
        cardId: cardEl.getAttribute("data-card-id"),
        startX: e.clientX,
        startColSpan: startSpan,
        currentColSpan: startSpan,
        gridWidth: gridRect.width,
        gridLeft: gridRect.left,
      };

      document.body.classList.add("select-none");
      document.body.style.cursor = "col-resize";
    },

    onPointerMoveResize(e) {
      if (!this.resize) return;
      const cardEl = this._cardById(this.resize.cardId);
      if (!cardEl) return;
      const cardLeft = cardEl.getBoundingClientRect().left;
      const width = e.clientX - cardLeft;
      const colWidth = this.resize.gridWidth / 12;
      const rawCols = Math.round(width / colWidth);

      let best = this._resizeSnaps[0];
      let bestDist = Math.abs(rawCols - best);
      for (const snap of this._resizeSnaps) {
        const dist = Math.abs(rawCols - snap);
        if (dist < bestDist) {
          best = snap;
          bestDist = dist;
        }
      }

      this._setCardSpan(cardEl, best);
      this.resize.currentColSpan = best;
    },

    endResize(_e) {
      if (!this.resize) return;
      const changed = this.resize.currentColSpan !== this.resize.startColSpan;
      const span = this.resize.currentColSpan;
      this.resize = null;
      document.body.classList.remove("select-none");
      document.body.style.cursor = "";

      if (changed) {
        this._markDirty();
        this._announce("Card resized to " + span + " columns");
      } else {
        // No change — drop the undo we pushed
        this.undoStack.pop();
      }
    },

    cancelResize() {
      if (!this.resize) return;
      const cardEl = this._cardById(this.resize.cardId);
      if (cardEl) this._setCardSpan(cardEl, this.resize.startColSpan);
      this.resize = null;
      document.body.classList.remove("select-none");
      document.body.style.cursor = "";
      this.undoStack.pop();
    },

    // ── Helpers ──
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
  };

  Object.defineProperty(builder, "showPicker", {
    get() {
      return this._showPicker;
    },
    set(v) {
      this._showPicker = v;
      root.dataset.showPicker = v ? "1" : "";
    },
  });

  Object.defineProperty(builder, "saveState", {
    get() {
      return this._saveState;
    },
    set(v) {
      this._saveState = v;
      const btn = root.querySelector(".dz-workspace-save");
      if (btn) {
        btn.setAttribute("data-dz-save-state", v);
        btn.disabled = v === "clean" || v === "saving" || v === "saved";
        btn.title = v === "error" ? this._saveError : "";
      }
    },
  });

  return builder;
}

// ── Mount lifecycle ────────────────────────────────────────────────
// Alpine used to init/destroy per x-data element; we mount on every
// `[data-dz-dashboard-builder]` root at load and after htmx settles
// (the #919/#924 morph seam), destroying builders whose root left the
// DOM so document/window listeners don't leak across swaps.
(function () {
  "use strict";
  const live = [];

  function mountAll(scope) {
    for (let i = live.length - 1; i >= 0; i--) {
      if (!live[i].root.isConnected) {
        live[i].builder.destroy();
        live.splice(i, 1);
      }
    }
    const host = scope || document;
    const roots = Array.from(
      host.querySelectorAll("[data-dz-dashboard-builder]"),
    );
    // querySelectorAll excludes the scope element itself (Alpine's
    // initTree included it) — cover an hx-target that IS the root.
    if (host.matches && host.matches("[data-dz-dashboard-builder]"))
      roots.push(host);
    roots.forEach((root) => {
      if (root._dzBuilderMounted) return;
      root._dzBuilderMounted = true;
      const builder = createDzDashboardBuilder(root);
      // exposed for harness/debug introspection (Alpine.$data parity)
      root._dzBuilder = builder;
      live.push({ root, builder });
      builder.init();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountAll(document));
  } else {
    mountAll(document);
  }
  document.body &&
    document.body.addEventListener("htmx:after:settle", (e) => {
      mountAll((e.detail && e.detail.target) || document);
    });
})();
