/** @ts-check */
/**
 * dz-alpine.js — Alpine.js component registrations for Dazzle.
 *
 * Registers named Alpine.data() components that replace dz.js features.
 * Must load BEFORE alpine.min.js (uses alpine:init event).
 *
 * Components:
 *  - dzToast          — toast notification container
 *  - dzConfirm        — confirmation dialog with htmx.ajax
 *  - dzTable          — data table with sort, column visibility, bulk select
 *  - dzMoney          — multi-currency minor unit field
 *  - dzFileUpload     — drag-and-drop file upload
 *  - dzWizard         — multi-step form wizard
 *  - dzPopover        — anchored floating content panel
 *  - dzTooltip        — rich content tooltip with show/hide delay
 *  - dzContextMenu    — right-click context menu
 *  - dzCommandPalette — spotlight-style command palette (Cmd+K)
 *  - dzSlideOver      — side sheet overlay with width control
 *  - dzToggleGroup    — exclusive or multi-select button group
 *
 * Directives:
 *  - x-flip               — FLIP-style animations for list reorders (#960)
 *  - x-pull-to-refresh    — touch pull-down → refresh CustomEvent (#958)
 */

document.addEventListener("alpine:init", () => {
  const Alpine = window.Alpine;

  // #975: convert Alpine's default plain-object error throws into real
  // `Error` instances so site-fuzz / page-error harnesses get
  // actionable messages + stacks instead of an opaque "Object" event.
  //
  // Alpine 3's default `setErrorHandler` does
  // `setTimeout(() => { throw {message, el, expression} }, 0)`. The
  // thrown value is a plain object — Playwright's `page.on('pageerror')`
  // sees `String(obj)` which strips to `[object Object]`. Real Errors
  // give us message + stack + cause, which surfaces the failing
  // expression in fuzzer reports.
  if (typeof Alpine.setErrorHandler === "function") {
    Alpine.setErrorHandler((rawError, el, expression) => {
      const message = (rawError && rawError.message) || String(rawError);
      const err = new Error(
        `Alpine expression error: ${message}` +
          (expression ? ` (expression: ${expression})` : ""),
      );
      // @ts-expect-error: cause is widely supported in modern browsers
      err.cause = rawError;
      // Preserve Alpine's "throw async via setTimeout" shape so it
      // doesn't break in-flight evaluation.
      setTimeout(() => {
        throw err;
      }, 0);
    });
  }

  // ── x-flip directive (#960 layer 3) ─────────────────────────────────
  //
  // FLIP-style animation for list reorders (insert/remove/move). Apply
  // `x-flip` to a container; each direct child needs a stable
  // `data-flip-key` attribute (the user's row id, etc.) so the
  // directive can match before/after positions across re-renders.
  //
  // Algorithm: snapshot child rects → MutationObserver fires → snapshot
  // again → for each surviving child compute (before - after) delta,
  // apply inverse translate, then transition back to identity. Browser
  // does the heavy lifting via CSS transition on `transform`.
  //
  // Honours `prefers-reduced-motion: reduce` — observer is still wired
  // (so the snapshot stays current) but transitions are skipped.
  if (typeof Alpine.directive === "function") {
    Alpine.directive("flip", (el) => {
      const reduce =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      // Map<flipKey, DOMRect>
      const lastRects = new Map();
      const snapshot = () => {
        const next = new Map();
        for (const child of el.children) {
          const key = child.dataset && child.dataset.flipKey;
          if (!key) continue;
          next.set(key, child.getBoundingClientRect());
        }
        return next;
      };
      // Initial snapshot — captures whatever's already rendered so the
      // first mutation has a "before" to compare against.
      for (const [k, r] of snapshot()) lastRects.set(k, r);

      const onMutation = () => {
        const newRects = snapshot();
        if (!reduce) {
          for (const child of el.children) {
            const key = child.dataset && child.dataset.flipKey;
            if (!key) continue;
            const before = lastRects.get(key);
            const after = newRects.get(key);
            if (!before || !after) continue;
            const dx = before.left - after.left;
            const dy = before.top - after.top;
            if (dx === 0 && dy === 0) continue;
            // Apply inverse instantly (no transition), then in next
            // frame clear and let the transition animate to identity.
            child.style.transition = "none";
            child.style.transform = `translate(${dx}px, ${dy}px)`;
            requestAnimationFrame(() => {
              child.style.transition =
                "transform var(--duration-base) var(--ease-spring-2)";
              child.style.transform = "";
            });
          }
        }
        // Refresh the cache regardless so the next mutation diffs
        // against the current state.
        lastRects.clear();
        for (const [k, r] of newRects) lastRects.set(k, r);
      };

      const observer = new MutationObserver(onMutation);
      observer.observe(el, { childList: true, subtree: false });

      // Cleanup hook for Alpine teardown (component removed from DOM).
      el._dzFlipObserver = observer;
    });

    // ── x-pull-to-refresh directive (#958 cycle 2) ────────────────────
    //
    // Pull-down-to-refresh on touch devices. Apply `x-pull-to-refresh`
    // to a list / dashboard container; the directive listens for a
    // touch-pull beyond `--dz-pull-threshold` (default 80px) and
    // dispatches a `refresh` CustomEvent on the element. Wire it to
    // an htmx swap by adding `hx-trigger="refresh"`:
    //
    //   <div x-pull-to-refresh
    //        hx-get="/users" hx-trigger="refresh"
    //        hx-target="this" hx-swap="innerHTML">
    //
    // Algorithm: capture touch start at scrollTop===0; track Y delta;
    // apply a damped translateY for visual feedback as the user pulls;
    // on release past threshold, fire `refresh`. Below threshold, snap
    // back. `prefers-reduced-motion: reduce` skips the transform but
    // still fires the event so the refresh works regardless.
    //
    // Touch-only via the same `pointer: coarse` rationale as
    // touch-targets.css — desktop mouse users don't get the gesture.
    if (typeof Alpine.directive === "function") {
      Alpine.directive("pull-to-refresh", (el) => {
        // Honour pointer:coarse only — desktop mouse drag would
        // otherwise hijack scroll. Falls back to no-op on
        // matchMedia-less environments.
        const isTouch =
          typeof window.matchMedia === "function" &&
          window.matchMedia("(pointer: coarse)").matches;
        if (!isTouch) return;

        const reduce =
          typeof window.matchMedia === "function" &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const threshold = 80;
        let startY = 0;
        let pulling = false;
        let pullDistance = 0;

        const onStart = (e) => {
          // Only engage when the container is scrolled to the top —
          // otherwise the user wants to scroll up, not refresh.
          if (el.scrollTop > 0) return;
          startY = e.touches[0].clientY;
          pulling = true;
          pullDistance = 0;
        };

        const onMove = (e) => {
          if (!pulling) return;
          pullDistance = Math.max(0, e.touches[0].clientY - startY);
          if (pullDistance > 0 && !reduce) {
            // Damped: pull half the distance, capped at 1.5× threshold.
            const visual = Math.min(pullDistance / 2, threshold * 1.5);
            el.style.transform = "translateY(" + visual + "px)";
          }
        };

        const onEnd = () => {
          if (!pulling) return;
          if (pullDistance >= threshold) {
            // Fire refresh — htmx (or any listener) picks it up.
            // `bubbles:true` so a parent's hx-trigger can also catch it.
            el.dispatchEvent(new CustomEvent("refresh", { bubbles: true }));
          }
          if (!reduce) {
            // Snap back smoothly.
            el.style.transition =
              "transform var(--duration-base) var(--ease-out)";
            el.style.transform = "";
            setTimeout(() => {
              el.style.transition = "";
            }, 200);
          }
          pulling = false;
          pullDistance = 0;
        };

        // Use { passive: true } so the browser doesn't have to wait
        // for our handler before handling native scroll — keeps the
        // page responsive even if the JS hangs.
        el.addEventListener("touchstart", onStart, { passive: true });
        el.addEventListener("touchmove", onMove, { passive: true });
        el.addEventListener("touchend", onEnd, { passive: true });
        el.addEventListener("touchcancel", onEnd, { passive: true });

        // Stash for potential teardown.
        el._dzPullToRefresh = { onStart, onMove, onEnd };
      });
    }
  }

  // ── Toast Notifications ─────────────────────────────────────────────

  Alpine.data("dzToast", () => ({
    toasts: [],
    _nextId: 0,

    init() {
      // Listen for HTMX server-sent showToast triggers
      document.body.addEventListener("showToast", (e) => {
        const d = /** @type {CustomEvent} */ (e).detail;
        if (d && d.message) this.show(d.message, d.type || "success");
      });
      // Listen for Alpine $dispatch('toast', ...) events
      this.$el.addEventListener("toast", (e) => {
        const d = /** @type {CustomEvent} */ (e).detail;
        if (d && d.message) this.show(d.message, d.type || "info");
      });
    },

    show(message, type = "info") {
      const id = ++this._nextId;
      this.toasts.push({ id, message, type, leaving: false });
      setTimeout(() => this.dismiss(id), 4000);
    },

    dismiss(id) {
      const t = this.toasts.find((t) => t.id === id);
      if (t) {
        t.leaving = true;
        setTimeout(() => {
          this.toasts = this.toasts.filter((t) => t.id !== id);
        }, 300);
      }
    },
  }));

  // Global toast function (backward compat with dz.toast)
  window.dz = window.dz || {};
  window.dz.toast = (message, type = "info") => {
    const el = document.getElementById("dz-toast");
    if (el)
      el.dispatchEvent(new CustomEvent("toast", { detail: { message, type } }));
  };

  /**
   * Download a CSV export via fetch + Blob (v0.61.2, #862).
   *
   * `<a download>` is ignored by Safari for same-origin responses with
   * `Content-Type: text/csv` — Safari treats the navigation as a document
   * load and renders the CSV inline, losing the user's workspace context.
   * The server-side `Content-Disposition: attachment` header is set
   * correctly but Safari honours its own heuristic over the header in
   * this case.
   *
   * This helper:
   *   1. Fetches the endpoint with same-origin credentials.
   *   2. Converts the response to a Blob (any Content-Type works).
   *   3. Creates a transient object-URL + synthetic <a download> element.
   *   4. Triggers a programmatic click (always a download, never a nav).
   *   5. Revokes the URL on next tick to free memory.
   *
   * Errors surface via toast + console — callers don't need to wrap.
   */
  window.dz.downloadCsv = async (endpoint, filename) => {
    const url = endpoint.includes("?")
      ? endpoint + "&format=csv"
      : endpoint + "?format=csv";
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        window.dz.toast(
          "CSV export failed: " + response.status + " " + response.statusText,
          "error",
        );
        return;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || "export.csv";
      // Appending to body is required on some browsers before click() works.
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Revoke on next tick so the browser has time to begin the download.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (err) {
      window.dz.toast("CSV export failed: network error", "error");
      console.error("[dz.downloadCsv]", err);
    }
  };

  // ── Confirm Dialog ──────────────────────────────────────────────────

  Alpine.data("dzConfirm", () => ({
    message: "",
    action: "",
    method: "delete",
    targetSel: "",
    swap: "outerHTML",
    loading: false,
    _trigger: null,

    init() {
      // Listen for confirm dispatches from trigger buttons
      window.addEventListener("dz-confirm", (e) => {
        const d = /** @type {CustomEvent} */ (e).detail;
        if (!d) return;
        this.message = d.message || "Are you sure?";
        // Sanitize: only allow safe relative URL paths
        this.action =
          d.action && /^\/[\w/\-?.=&%]+$/.test(d.action) ? d.action : "";
        // Sanitize: only allow known HTTP methods
        this.method = ["delete", "post", "put", "patch"].includes(
          (d.method || "delete").toLowerCase(),
        )
          ? d.method
          : "delete";
        this.targetSel = d.target || "";
        this.swap = d.swap || "outerHTML";
        this._trigger = d.triggerEl || null;
        this.$refs.dialog.showModal();
      });
    },

    async confirm() {
      if (!this.action || !this.action.startsWith("/")) return;
      this.loading = true;

      const opts = {};
      if (this.targetSel) {
        opts.target = this.targetSel;
        opts.swap = this.swap;
      } else if (this._trigger) {
        const tr = this._trigger.closest("tr");
        if (tr) {
          opts.target = tr;
          opts.swap = "outerHTML swap:300ms";
        } else {
          opts.target = "body";
          opts.swap = "innerHTML";
        }
      }

      // #980: guard against htmx not yet loaded. Both htmx.min.js and
      // dz-alpine.js use `defer`, so document order should make htmx
      // available — but cache misses or extension-loaded scripts can
      // still race. Without the guard, the user clicks "Confirm" and
      // gets a silent ReferenceError instead of a graceful failure.
      if (typeof htmx === "undefined") {
        console.error(
          "[dzConfirm] htmx not yet loaded — confirm action cannot proceed",
        );
        this.loading = false;
        this._trigger = null;
        return;
      }
      try {
        await htmx.ajax(this.method.toUpperCase(), this.action, opts);
        this.$refs.dialog.close();
      } finally {
        this.loading = false;
        this._trigger = null;
      }
    },

    cancel() {
      this.$refs.dialog.close();
      this._trigger = null;
    },
  }));

  // ── Data Table ──────────────────────────────────────────────────────

  Alpine.data("dzTable", (tableId, endpoint, config) => ({
    // ── Sort state ──────────────────────────────────────────────────────
    sortField: (config && config.sortField) || "",
    sortDir: (config && config.sortDir) || "asc",

    // ── Column visibility ────────────────────────────────────────────────
    hiddenColumns: JSON.parse(
      localStorage.getItem(`dz-cols-${tableId}`) || "[]",
    ),

    // ── Column widths (resize) ───────────────────────────────────────────
    columnWidths: JSON.parse(
      localStorage.getItem(`dz-widths-${tableId}`) || "{}",
    ),

    // ── Selection ────────────────────────────────────────────────────────
    selected: new Set(),
    bulkCount: 0,

    // ── Inline edit state ────────────────────────────────────────────────
    /** @type {{rowId: string, colKey: string, originalValue: string, saving: boolean, error: string|null}|null} */
    editing: null,

    // ── Column resize drag state ─────────────────────────────────────────
    /** @type {{colKey: string, startX: number, startWidth: number}|null} */
    resize: null,

    // ── Loading / UI state ───────────────────────────────────────────────
    loading: false,
    colMenuOpen: false,

    // ── Config shortcuts ─────────────────────────────────────────────────
    /** @type {string[]} */
    inlineEditable: (config && config.inlineEditable) || [],
    bulkActionsEnabled: !!(config && config.bulkActions),
    entityName: (config && config.entityName) || "",

    // ── Lifecycle ────────────────────────────────────────────────────────
    init() {
      // Store root element reference — $el is contextual in event handlers
      // (it becomes the clicked child), so we capture it here where it is
      // guaranteed to be the x-data component root.
      this._root = this.$el;

      // Validate hiddenColumns against the current table schema (#853).
      // localStorage persists across page loads — if the column set
      // changed (schema migration, persona swap, table id reused) any
      // stale entries would silently hide visible columns. Drop any key
      // that doesn't correspond to a [data-dz-col] in the current DOM
      // and persist the cleaned list back so a single survives-all-loads
      // cleanup happens here, not on every render.
      this._pruneStaleHiddenColumns();

      this.applyColumnVisibility();
      this._applyStoredWidths();

      // Inject selected IDs into htmx bulk action requests
      this.$el.addEventListener("htmx:configRequest", (e) => {
        const detail = /** @type {CustomEvent} */ (e).detail;
        if (detail.elt.hasAttribute("data-dz-bulk-action")) {
          detail.parameters["ids"] = Array.from(this.selected);
        }
      });

      // Loading state driven by HTMX events on the table root
      this.$el.addEventListener("htmx:beforeRequest", () => {
        this.loading = true;
      });
      this.$el.addEventListener("htmx:afterSettle", () => {
        this.loading = false;
      });
      this.$el.addEventListener("htmx:responseError", () => {
        this.loading = false;
      });

      // Resize-drag listeners live on window so they survive mouse excursions
      // outside the table. We own the lifecycle explicitly (rather than using
      // Alpine's @pointermove.window declarative bindings) because HTMX morph
      // navigation tears the component down without reliably firing Alpine's
      // destroy path, leaving the listener pointing at a stale scope and
      // throwing ReferenceError on the next mousemove (issue #795).
      this._onResizeMove = (e) => this.onResizeMove(e);
      this._onEndResize = (e) => this.endResize(e);
      window.addEventListener("pointermove", this._onResizeMove);
      window.addEventListener("pointerup", this._onEndResize);

      // #978: mirror bulkCount to a data attribute on the root + the
      // textContent of `[data-dz-bulk-count-target]` descendants. Two
      // fragments (bulk_actions, table_pagination) previously bound
      // `x-show="bulkCount > 0"` / `x-text="bulkCount"` on children of
      // this scope; idiomorph re-evaluated those bindings on morph
      // before Alpine re-established the dzTable scope, throwing
      // "bulkCount is not defined" — same family as #970/#972. CSS now
      // shows/hides via `[data-dz-bulk-count="0"]` selectors; count
      // text comes from textContent (no Alpine binding on the
      // morphable child).
      const syncBulkCount = (n) => {
        const root = this._root;
        if (!root) return;
        root.setAttribute("data-dz-bulk-count", String(n));
        root.querySelectorAll("[data-dz-bulk-count-target]").forEach((el) => {
          el.textContent = String(n);
        });
      };
      syncBulkCount(this.bulkCount);
      this.$watch("bulkCount", syncBulkCount);
    },

    destroy() {
      // Clean up window-level pointer listeners on component teardown.
      if (this._onResizeMove) {
        window.removeEventListener("pointermove", this._onResizeMove);
        this._onResizeMove = null;
      }
      if (this._onEndResize) {
        window.removeEventListener("pointerup", this._onEndResize);
        this._onEndResize = null;
      }
    },

    // ── Screen reader announce ────────────────────────────────────────────
    _announce(msg) {
      let region = document.getElementById("dz-live-region");
      if (!region) {
        region = document.createElement("div");
        region.id = "dz-live-region";
        region.setAttribute("role", "status");
        region.setAttribute("aria-live", "polite");
        region.setAttribute("aria-atomic", "true");
        Object.assign(region.style, {
          position: "absolute",
          width: "1px",
          height: "1px",
          padding: "0",
          overflow: "hidden",
          clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap",
          border: "0",
        });
        document.body.appendChild(region);
      }
      region.textContent = "";
      // Force re-announcement even if text is the same
      requestAnimationFrame(() => {
        region.textContent = msg;
      });
    },

    // ── Sort ──────────────────────────────────────────────────────────────
    toggleSort(field) {
      if (this.sortField !== field) {
        // New column: start at asc
        this.sortField = field;
        this.sortDir = "asc";
      } else if (this.sortDir === "asc") {
        this.sortDir = "desc";
      } else if (this.sortDir === "desc") {
        // Third click: clear sort
        this.sortField = "";
        this.sortDir = "asc";
      } else {
        this.sortDir = "asc";
      }
      const label = this.sortField
        ? `Sorted by ${this.sortField} ${this.sortDir}ending`
        : "Sort cleared";
      this._announce(label);
      this.reload();
    },

    sortIcon(field) {
      if (this.sortField !== field) return "opacity-0 group-hover:opacity-50";
      return this.sortDir === "desc" ? "rotate-180 opacity-100" : "opacity-100";
    },

    ariaSortDir(field) {
      if (this.sortField !== field) return null;
      return this.sortDir === "asc" ? "ascending" : "descending";
    },

    // ── Column visibility ─────────────────────────────────────────────────
    toggleColumn(key) {
      const idx = this.hiddenColumns.indexOf(key);
      if (idx >= 0) this.hiddenColumns.splice(idx, 1);
      else this.hiddenColumns.push(key);
      localStorage.setItem(
        `dz-cols-${tableId}`,
        JSON.stringify(this.hiddenColumns),
      );
      this.applyColumnVisibility();
    },

    isColumnVisible(key) {
      return !this.hiddenColumns.includes(key);
    },

    applyColumnVisibility() {
      this.$el.querySelectorAll("[data-dz-col]").forEach((cell) => {
        const key = cell.getAttribute("data-dz-col");
        /** @type {HTMLElement} */ (cell).style.display =
          this.hiddenColumns.includes(key || "") ? "none" : "";
      });
    },

    /**
     * Drop hiddenColumns entries that no longer correspond to a real
     * column in the current DOM (#853). Without this, localStorage from
     * an earlier page load could keep cells invisible even after the
     * column has been removed or renamed — manifest as "headers render
     * but cells are empty" because the cells exist with `display:none`.
     *
     * Persists the cleaned list back so the prune happens once on init,
     * not on every applyColumnVisibility call.
     */
    _pruneStaleHiddenColumns() {
      const presentKeys = new Set();
      this.$el.querySelectorAll("[data-dz-col]").forEach((cell) => {
        const key = cell.getAttribute("data-dz-col");
        if (key) presentKeys.add(key);
      });
      // No columns present → either an empty-state render or the table
      // hasn't materialised yet. Don't touch localStorage in that case;
      // the next render-with-rows will prune cleanly.
      if (presentKeys.size === 0) return;
      const cleaned = this.hiddenColumns.filter((k) => presentKeys.has(k));
      if (cleaned.length !== this.hiddenColumns.length) {
        this.hiddenColumns = cleaned;
        localStorage.setItem(
          `dz-cols-${tableId}`,
          JSON.stringify(this.hiddenColumns),
        );
      }
    },

    /**
     * Reset all column visibility — clears hiddenColumns + localStorage.
     * Wire to a "Show all columns" entry in the column-toggle menu so
     * users have an escape hatch when they've hidden too much.
     */
    resetColumnVisibility() {
      this.hiddenColumns = [];
      localStorage.removeItem(`dz-cols-${tableId}`);
      this.applyColumnVisibility();
    },

    // ── Column resize ─────────────────────────────────────────────────────
    _applyStoredWidths() {
      Object.entries(this.columnWidths).forEach(([colKey, width]) => {
        const col = this.$el.querySelector(`col[data-col="${colKey}"]`);
        if (col) /** @type {HTMLElement} */ (col).style.width = `${width}px`;
      });
    },

    startColumnResize(colKey, e) {
      const col = this.$el.querySelector(`col[data-col="${colKey}"]`);
      if (!col) return;
      const currentWidth =
        /** @type {HTMLElement} */ (col).offsetWidth ||
        parseInt(/** @type {HTMLElement} */ (col).style.width || "160", 10);
      this.resize = {
        colKey,
        startX: e.clientX,
        startWidth: currentWidth,
      };
      document.body.style.cursor = "col-resize";
      this.$el.classList.add("select-none");
      e.preventDefault();
    },

    onResizeMove(e) {
      if (!this.resize) return;
      const { colKey, startX, startWidth } = this.resize;
      const raw = startWidth + (e.clientX - startX);
      const clamped = Math.min(800, Math.max(80, raw));
      // Snap to 8px grid
      const snapped = Math.round(clamped / 8) * 8;
      const col = this.$el.querySelector(`col[data-col="${colKey}"]`);
      if (col) /** @type {HTMLElement} */ (col).style.width = `${snapped}px`;
    },

    endResize(e) {
      if (!this.resize) return;
      const { colKey, startX, startWidth } = this.resize;
      const raw = startWidth + (e.clientX - startX);
      const clamped = Math.min(800, Math.max(80, raw));
      const snapped = Math.round(clamped / 8) * 8;
      // Persist to localStorage
      this.columnWidths[colKey] = snapped;
      localStorage.setItem(
        `dz-widths-${tableId}`,
        JSON.stringify(this.columnWidths),
      );
      document.body.style.cursor = "";
      this.$el.classList.remove("select-none");
      this.resize = null;
    },

    // ── Bulk select ───────────────────────────────────────────────────────
    toggleSelectAll(checked) {
      const root = this._root || this.$el;
      if (checked) {
        root
          .querySelectorAll("[data-dz-row-id]")
          .forEach((row) =>
            this.selected.add(row.getAttribute("data-dz-row-id") || ""),
          );
      } else {
        this.selected.clear();
      }
      this.syncCheckboxes();
      this.bulkCount = this.selected.size;
    },

    toggleRow(id, checked) {
      if (checked) this.selected.add(id);
      else this.selected.delete(id);
      this.bulkCount = this.selected.size;
    },

    clearSelection() {
      this.selected.clear();
      this.syncCheckboxes();
      this.bulkCount = this.selected.size;
    },

    syncCheckboxes() {
      (this._root || this.$el)
        .querySelectorAll("[data-dz-row-select]")
        .forEach((input) => {
          const id =
            input.closest("[data-dz-row-id]")?.getAttribute("data-dz-row-id") ||
            "";
          /** @type {HTMLInputElement} */ (input).checked =
            this.selected.has(id);
        });
    },

    // ── Inline edit ────────────────────────────────────────────────────────
    isEditing(rowId, colKey) {
      return (
        this.editing !== null &&
        this.editing.rowId === rowId &&
        this.editing.colKey === colKey
      );
    },

    startEdit(rowId, colKey, currentValue) {
      if (!this.inlineEditable.includes(colKey)) return;
      this.editing = {
        rowId,
        colKey,
        originalValue: String(currentValue ?? ""),
        saving: false,
        error: null,
      };
    },

    async commitEdit(newValue) {
      if (!this.editing) return;
      const { rowId, colKey } = this.editing;
      this.editing.saving = true;
      this.editing.error = null;
      try {
        const entityPath = this.entityName || tableId;
        const resp = await fetch(
          `/api/${entityPath}/${rowId}/field/${colKey}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({ value: String(newValue) }),
          },
        );
        if (!resp.ok) {
          const text = await resp.text().catch(() => "Server error");
          this.editing.saving = false;
          this.editing.error = text || `Error ${resp.status}`;
          return;
        }
        this.editing = null;
        this._announce("Saved");
        // Reload the row to reflect the saved value
        this.reload();
      } catch (err) {
        if (this.editing) {
          this.editing.saving = false;
          this.editing.error =
            err instanceof Error ? err.message : "Network error";
        }
      }
    },

    cancelEdit() {
      this.editing = null;
    },

    handleEditKeydown(e) {
      if (!this.editing) return;
      const input = /** @type {HTMLInputElement} */ (e.target);
      if (e.key === "Enter") {
        e.preventDefault();
        this.commitEdit(input.value);
      } else if (e.key === "Escape") {
        e.preventDefault();
        this.cancelEdit();
      } else if (e.key === "Tab") {
        e.preventDefault();
        const value = input.value;
        const { rowId, colKey } = this.editing;
        const direction = e.shiftKey ? "prev" : "next";
        const next = this.nextEditableCell(rowId, colKey, direction);
        this.commitEdit(value).then(() => {
          if (next) this.startEdit(next.rowId, next.colKey, "");
        });
      }
    },

    nextEditableCell(rowId, colKey, direction) {
      const editable = this.inlineEditable;
      if (!editable.length) return null;
      const colIdx = editable.indexOf(colKey);
      if (direction === "next") {
        if (colIdx < editable.length - 1) {
          return { rowId, colKey: editable[colIdx + 1] };
        }
        // Move to first editable cell in next row
        const rows = /** @type {NodeListOf<HTMLElement>} */ (
          this.$el.querySelectorAll("[data-dz-row-id]")
        );
        const rowIds = Array.from(rows).map(
          (r) => r.getAttribute("data-dz-row-id") || "",
        );
        const rowIdx = rowIds.indexOf(rowId);
        if (rowIdx >= 0 && rowIdx < rowIds.length - 1) {
          return { rowId: rowIds[rowIdx + 1], colKey: editable[0] };
        }
        return null;
      } else {
        // prev
        if (colIdx > 0) {
          return { rowId, colKey: editable[colIdx - 1] };
        }
        const rows = /** @type {NodeListOf<HTMLElement>} */ (
          this.$el.querySelectorAll("[data-dz-row-id]")
        );
        const rowIds = Array.from(rows).map(
          (r) => r.getAttribute("data-dz-row-id") || "",
        );
        const rowIdx = rowIds.indexOf(rowId);
        if (rowIdx > 0) {
          return {
            rowId: rowIds[rowIdx - 1],
            colKey: editable[editable.length - 1],
          };
        }
        return null;
      }
    },

    // ── Bulk delete ───────────────────────────────────────────────────────
    async bulkDelete() {
      const count = this.selected.size;
      if (!count) return;
      if (!confirm(`Delete ${count} item${count === 1 ? "" : "s"}?`)) return;
      const entityPath = this.entityName || tableId;
      try {
        const resp = await fetch(`/api/${entityPath}/bulk-delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: Array.from(this.selected) }),
        });
        if (!resp.ok) {
          window.dz?.toast("Delete failed. Please try again.", "error");
          return;
        }
        this.clearSelection();
        this.reload();
        this._announce(`${count} item${count === 1 ? "" : "s"} deleted`);
      } catch (err) {
        window.dz?.toast("Network error during delete.", "error");
      }
    },

    // ── HTMX reload with current state ────────────────────────────────────
    reload() {
      const target = document.getElementById(`${tableId}-body`);
      if (!target || typeof htmx === "undefined") return;
      const p = new URLSearchParams();
      if (this.sortField) p.set("sort", this.sortField);
      p.set("dir", this.sortDir);
      p.set("page", "1");
      this.$el.querySelectorAll('[name^="filter["]').forEach((input) => {
        if (/** @type {HTMLInputElement} */ (input).value)
          p.set(
            input.getAttribute("name") || "",
            /** @type {HTMLInputElement} */ (input).value,
          );
      });
      const searchInput = /** @type {HTMLInputElement|null} */ (
        this.$el.querySelector("input[name='search']")
      );
      if (searchInput?.value) p.set("search", searchInput.value);
      htmx.ajax("GET", `${endpoint}?${p}`, {
        target,
        swap: "morph:innerHTML",
        headers: { Accept: "text/html" },
      });
    },
  }));

  // ── Money Field ─────────────────────────────────────────────────────

  const CURRENCY_SCALES = {
    GBP: 2,
    USD: 2,
    EUR: 2,
    AUD: 2,
    CAD: 2,
    CHF: 2,
    CNY: 2,
    INR: 2,
    NZD: 2,
    SGD: 2,
    HKD: 2,
    SEK: 2,
    NOK: 2,
    DKK: 2,
    ZAR: 2,
    MXN: 2,
    BRL: 2,
    JPY: 0,
    KRW: 0,
    VND: 0,
    CLP: 0,
    ISK: 0,
    BHD: 3,
    KWD: 3,
    OMR: 3,
    TND: 3,
    JOD: 3,
    IQD: 3,
    LYD: 3,
  };

  Alpine.data("dzMoney", () => ({
    displayValue: "",
    minorValue: "",
    _scale: 2,

    init() {
      // Determine scale from container attributes
      this._scale = this._getScale();
      // Populate display from minor on load (edit mode)
      if (this.minorValue && !this.displayValue) {
        this.displayValue = this._toDisplay(this.minorValue);
      }
    },

    onInput() {
      this.minorValue = String(this._toMinor(this.displayValue));
    },

    onBlur() {
      if (!this.displayValue.trim()) {
        this.minorValue = "";
        return;
      }
      const minor = this._toMinor(this.displayValue);
      this.minorValue = String(minor);
      this.displayValue = this._toDisplay(String(minor));
    },

    onCurrencyChange(event) {
      const opt = event.target.selectedOptions[0];
      if (opt && opt.dataset.scale !== undefined) {
        this._scale = parseInt(opt.dataset.scale, 10);
      }
      // Update prefix symbol
      const prefix = this.$el.querySelector(".dz-money-prefix");
      if (prefix && opt && opt.dataset.symbol) {
        prefix.textContent = opt.dataset.symbol;
      }
      // Re-convert with new scale
      if (this.displayValue) {
        const minor = this._toMinor(this.displayValue);
        this.minorValue = String(minor);
        this.displayValue = this._toDisplay(String(minor));
      }
    },

    _getScale() {
      const scaleAttr = this.$el.getAttribute("data-dz-scale");
      if (scaleAttr !== null) return parseInt(scaleAttr, 10);
      const code = this.$el.getAttribute("data-dz-currency") || "GBP";
      return CURRENCY_SCALES[code] !== undefined ? CURRENCY_SCALES[code] : 2;
    },

    _toMinor(val) {
      const num = parseFloat(val);
      if (isNaN(num)) return 0;
      return Math.round(num * Math.pow(10, this._scale));
    },

    _toDisplay(val) {
      const num = parseInt(val, 10);
      if (isNaN(num)) return "";
      return (num / Math.pow(10, this._scale)).toFixed(this._scale);
    },
  }));

  // ── File Upload ─────────────────────────────────────────────────────

  Alpine.data("dzFileUpload", () => ({
    filename: "",
    hasFile: false,
    uploading: false,
    error: "",
    dragging: false,

    selectFile(event) {
      const files = event.target.files;
      if (files && files[0]) this.upload(files[0]);
    },

    onDrop(event) {
      event.preventDefault();
      this.dragging = false;
      if (event.dataTransfer?.files?.[0]) {
        this.upload(event.dataTransfer.files[0]);
      }
    },

    async upload(file) {
      this.error = "";
      this.uploading = true;

      const formData = new FormData();
      formData.append("file", file);

      // Add entity context from form
      const form = this.$el.closest("form");
      const entityName = form?.dataset.dazzleForm || "";
      const fieldName = this.$el.dataset.dzFile || "";
      if (entityName) formData.append("entity", entityName);
      if (fieldName) formData.append("field", fieldName);

      try {
        const resp = await fetch("/files/upload", {
          method: "POST",
          body: formData,
        });
        if (!resp.ok) {
          const errBody = await resp.json().catch(() => ({}));
          throw new Error(errBody.detail || "Upload failed");
        }
        const data = await resp.json();
        this.filename = data.filename || file.name;
        this.hasFile = true;
        // Set hidden input value
        const hidden = this.$el.querySelector("[data-dz-file-value]");
        if (hidden) hidden.value = data.url || data.id;
      } catch (err) {
        this.error = err.message || "Upload failed";
      } finally {
        this.uploading = false;
      }
    },

    clear() {
      this.filename = "";
      this.hasFile = false;
      this.error = "";
      const hidden = this.$el.querySelector("[data-dz-file-value]");
      if (hidden) hidden.value = "";
      const fileInput = this.$el.querySelector("[data-dz-file-input]");
      if (fileInput) fileInput.value = "";
    },
  }));

  // ── Wizard Form ─────────────────────────────────────────────────────

  Alpine.data("dzWizard", (totalSteps) => ({
    step: 0,
    total: totalSteps,

    showStage(idx) {
      this.step = idx;
    },

    next() {
      if (this.validateStage(this.step) && this.step < this.total - 1) {
        this.step++;
      }
    },

    prev() {
      if (this.step > 0) this.step--;
    },

    goToStep(idx) {
      if (idx <= this.step) {
        this.step = idx;
      } else if (idx === this.step + 1 && this.validateStage(this.step)) {
        this.step = idx;
      }
    },

    validateStage(idx) {
      const stages = this.$el.querySelectorAll("[data-dz-stage]");
      if (!stages[idx]) return true;
      const inputs = stages[idx].querySelectorAll(
        "input[required], select[required], textarea[required]",
      );
      let valid = true;
      inputs.forEach((input) => {
        if (!(/** @type {HTMLInputElement} */ (input).value)) {
          /** @type {HTMLInputElement} */ (input).reportValidity();
          valid = false;
        }
      });
      return valid;
    },

    isActive(idx) {
      return idx <= this.step;
    },
    isCurrent(idx) {
      return idx === this.step;
    },
  }));

  // ── Confirm gate ──────────────────────────────────────────────────────
  // v0.61.72 (#6) — confirm_action_panel checklist gate. Tracks the
  // count of required checkboxes that have been ticked; the primary
  // action enables only when `tickedRequired === requiredCount`. The
  // template binds via `enabled` (computed from the count).
  Alpine.data("dzConfirmGate", (totalRows) => ({
    total: totalRows,
    tickedRequired: 0,
    requiredCount: 0,

    init() {
      // Count required rows from the data-dz-required-count attribute
      // on the gate's root element. Falls back to scanning if absent.
      const declared = parseInt(
        this.$el.getAttribute("data-dz-required-count") || "0",
        10,
      );
      if (declared > 0) {
        this.requiredCount = declared;
      } else {
        const reqInputs = this.$el.querySelectorAll(
          'input[type="checkbox"][data-dz-required="true"]',
        );
        this.requiredCount = reqInputs.length;
      }
    },

    onToggle(event) {
      const target = event.target;
      if (!target || target.dataset.dzRequired !== "true") return;
      this.tickedRequired += target.checked ? 1 : -1;
      if (this.tickedRequired < 0) this.tickedRequired = 0;
    },

    get enabled() {
      // No required rows = always enabled (low-friction flow with
      // only optional checkboxes or no checkboxes at all).
      if (this.requiredCount === 0) return true;
      return this.tickedRequired >= this.requiredCount;
    },
  }));

  // ── Popover ───────────────────────────────────────────────────────────

  Alpine.data("dzPopover", () => ({
    open: false,

    toggle() {
      this.open = !this.open;
    },
    show() {
      this.open = true;
    },
    hide() {
      this.open = false;
      this.$dispatch("dz:close");
    },

    init() {
      // Close on Escape
      this.$el.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.open) this.hide();
      });
      // Close on click outside
      document.addEventListener("click", (e) => {
        if (this.open && !this.$el.contains(e.target)) this.hide();
      });
    },
  }));

  // ── Rich Tooltip ──────────────────────────────────────────────────────

  Alpine.data("dzTooltip", () => ({
    visible: false,
    _showTimer: null,
    _hideTimer: null,

    showDelay() {
      return parseInt(this.$el.dataset.dzDelay || "200", 10);
    },
    hideDelay() {
      return parseInt(this.$el.dataset.dzHideDelay || "100", 10);
    },

    show() {
      clearTimeout(this._hideTimer);
      this._showTimer = setTimeout(() => {
        this.visible = true;
      }, this.showDelay());
    },
    hide() {
      clearTimeout(this._showTimer);
      this._hideTimer = setTimeout(() => {
        this.visible = false;
      }, this.hideDelay());
    },
  }));

  // ── Context Menu ──────────────────────────────────────────────────────

  Alpine.data("dzContextMenu", () => ({
    open: false,
    x: 0,
    y: 0,

    onContextMenu(e) {
      e.preventDefault();
      this.x = e.clientX;
      this.y = e.clientY;
      this.open = true;
    },
    close() {
      this.open = false;
    },

    init() {
      this.$el.addEventListener("contextmenu", (e) => this.onContextMenu(e));
      document.addEventListener("click", () => {
        if (this.open) this.close();
      });
      this.$el.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.open) this.close();
      });
    },
  }));

  // ── Command Palette ───────────────────────────────────────────────────

  Alpine.data("dzCommandPalette", () => ({
    open: false,
    query: "",
    selectedIndex: 0,
    actions: [],

    get filtered() {
      if (!this.query) return this.actions;
      const q = this.query.toLowerCase();
      return this.actions.filter(
        (a) =>
          a.label.toLowerCase().includes(q) ||
          (a.group && a.group.toLowerCase().includes(q)),
      );
    },

    toggle() {
      this.open = !this.open;
      if (this.open) {
        this.query = "";
        this.selectedIndex = 0;
        this.$nextTick(() => this.$refs.searchInput?.focus());
      }
    },
    close() {
      this.open = false;
      this.query = "";
    },
    select(action) {
      this.close();
      if (action.url) window.location.href = action.url;
      if (action.handler) action.handler();
      this.$dispatch("dz:select", { action });
    },

    onKeyDown(e) {
      const items = this.filtered;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
      } else if (e.key === "Enter" && items.length > 0) {
        e.preventDefault();
        this.select(items[this.selectedIndex]);
      }
    },

    init() {
      // Parse actions from data attribute
      try {
        this.actions = JSON.parse(this.$el.dataset.dzActions || "[]");
      } catch (_) {
        this.actions = [];
      }
      // Global keyboard shortcut: Cmd+K / Ctrl+K
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "k") {
          e.preventDefault();
          this.toggle();
        }
        if (e.key === "Escape" && this.open) this.close();
      });
    },
  }));

  // ── Slide-Over (Enhanced) ─────────────────────────────────────────────

  Alpine.data("dzSlideOver", () => ({
    open: false,
    _width: "md",

    widthClass() {
      const map = {
        sm: "max-w-sm",
        md: "max-w-md",
        lg: "max-w-lg",
        xl: "max-w-xl",
        full: "max-w-full",
      };
      return map[this._width] || "max-w-md";
    },

    show() {
      this.open = true;
      this.$dispatch("dz:open");
    },
    hide() {
      this.open = false;
      this.$dispatch("dz:close");
    },

    init() {
      this._width = this.$el.dataset.dzWidth || "md";
      // Listen for open event from HTMX triggers
      window.addEventListener("dz:slideover-open", () => this.show());
      this.$el.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.open) this.hide();
      });
    },
  }));

  // ── Toggle Group ──────────────────────────────────────────────────────

  Alpine.data("dzToggleGroup", () => ({
    value: null,
    multi: false,

    init() {
      this.multi = this.$el.dataset.dzMulti === "true";
      const initial = this.$el.dataset.dzValue;
      if (initial) {
        this.value = this.multi ? initial.split(",") : initial;
      } else {
        this.value = this.multi ? [] : null;
      }
    },

    isSelected(val) {
      return this.multi ? (this.value || []).includes(val) : this.value === val;
    },

    toggle(val) {
      if (this.multi) {
        const arr = this.value || [];
        const idx = arr.indexOf(val);
        this.value = idx >= 0 ? arr.filter((v) => v !== val) : [...arr, val];
      } else {
        this.value = this.value === val ? null : val;
      }
      // Sync to hidden input
      const hidden = this.$el.querySelector("input[type=hidden]");
      if (hidden)
        hidden.value = this.multi
          ? (this.value || []).join(",")
          : this.value || "";
      this.$dispatch("dz:select", { value: this.value });
    },
  }));

  // ── Theme Switcher ──────────────────────────────────────────────────
  //
  // Phase C Patch 3: live app-shell theme switching.
  //
  // Server emits a `<script type="application/json" id="dz-app-themes">`
  // map of `{<theme_name>: [<url>, ...]}` (chain order, parent → leaf)
  // covering every theme discovered at startup. The component reads
  // the active theme from `<html data-theme-name>` (server-set), then
  // on `setTheme(name)` swaps the `<link data-theme-link>` chain to
  // the new theme's URLs and persists the choice via `dzPrefs` (or
  // localStorage as fallback for unauthenticated users).
  //
  // Usage in a template:
  //   <div x-data="dzThemeSwitcher">
  //     <template x-for="t in themes" :key="t">
  //       <button @click="setTheme(t)" :aria-pressed="active === t"
  //               x-text="t"></button>
  //     </template>
  //   </div>
  Alpine.data("dzThemeSwitcher", () => ({
    /** @type {string[]} */
    themes: [],
    /** @type {string} */
    active: "",

    init() {
      // Active theme = server-rendered `<html data-theme-name="...">`.
      this.active = document.documentElement.dataset.themeName || "";
      // Theme map shipped as inline JSON.
      const mapEl = document.getElementById("dz-app-themes");
      if (!mapEl) return;
      try {
        const map = JSON.parse(mapEl.textContent || "{}");
        this.themes = Object.keys(map).sort();
        this._urls = map; // { name: ['/static/css/themes/x.css', ...] }
      } catch (e) {
        /* malformed JSON — leave themes empty */
      }
      // Restore persisted choice (overrides server-rendered default
      // for THIS request only — server still honours its own resolution
      // for first-paint flash prevention on next navigation).
      const persisted = this._readPersisted();
      if (persisted && persisted !== this.active && this._urls[persisted]) {
        this.setTheme(persisted);
      }
    },

    setTheme(name) {
      if (!this._urls[name]) return; // unknown — silently ignore
      // Remove existing theme links
      document
        .querySelectorAll("link[data-theme-link]")
        .forEach((el) => el.parentNode && el.parentNode.removeChild(el));
      // Inject the new chain in cascade order (parent first → leaf last).
      // Defence in depth: even though the server emits the URL list as
      // inline JSON (see init()), validate each URL matches the
      // expected theme-CSS shape before assigning to `link.href`.
      // Closes CodeQL js/xss-through-dom (#81) — and rejects any
      // `javascript:` / `data:` payload that would otherwise reach the
      // DOM sink.
      const SAFE_THEME_URL = /^\/(?:static\/)?(?:css\/)?themes\/[\w-]+\.css$/;
      const head = document.head;
      this._urls[name].forEach((url) => {
        if (typeof url !== "string" || !SAFE_THEME_URL.test(url)) return;
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        link.dataset.themeLink = name;
        head.appendChild(link);
      });
      this.active = name;
      document.documentElement.dataset.themeName = name;
      this._persist(name);
      // Notify any listeners (e.g. data-island re-renders) that the
      // theme changed. Alpine bridges `dz:` events naturally.
      window.dispatchEvent(
        new CustomEvent("dz:theme-changed", { detail: { name } }),
      );
    },

    _persist(name) {
      // Prefer server-backed prefs (auth users); fall back to localStorage.
      if (window.dzPrefs && typeof window.dzPrefs.set === "function") {
        window.dzPrefs.set("app_theme", name);
      } else {
        try {
          localStorage.setItem("dz.app_theme", name);
        } catch (e) {
          /* private browsing — ignore */
        }
      }
    },

    _readPersisted() {
      // Try server prefs first (instant for auth users)
      if (window.dzPrefs && typeof window.dzPrefs.get === "function") {
        const v = window.dzPrefs.get("app_theme", null);
        if (v) return v;
      }
      try {
        return localStorage.getItem("dz.app_theme") || null;
      } catch (e) {
        return null;
      }
    },
  }));
});

// ── HTMX morph-swap → Alpine.initTree bridge (#924) ───────────────────
//
// htmx-morph swaps mutate the DOM in-place — they don't fire the
// MutationObserver patterns Alpine relies on for auto-discovery of new
// `x-data` roots. When a sidebar workspace link morphs `#main-content`
// from one workspace to another, the new `<div x-data="dzDashboardBuilder()">`
// element lands in the DOM but Alpine never calls `init()` on it, so
// `<template x-for>` directives stay inert and the JSON layout island
// renders as raw text.
//
// The fix is the standard Alpine + HTMX bridge: after every swap settles,
// walk the swapped subtree and call `Alpine.initTree(target)`. Alpine
// tags processed elements internally so re-initing inited components is
// a no-op — safe to fire on every settle.
//
// Listen on `htmx:afterSettle` (not `afterSwap`) for the same reason as
// the per-component listener in dashboard-builder.js: under the morph
// extension `afterSwap` fires before idiomorph commits child-node text,
// so the JSON data island still holds stale text at that point. See
// #919 (the original fix) and #924 (this follow-up).
document.body.addEventListener("htmx:afterSettle", (e) => {
  const target = e && e.detail && e.detail.target;
  if (!target) return;
  if (window.Alpine && typeof window.Alpine.initTree === "function") {
    window.Alpine.initTree(target);
  }

  // #936 → #945 → #948: workspace component re-hydration on same-URL morph.
  //
  // Same-URL morph (clicking the active workspace's sidebar link)
  // keeps the `<div x-data="dzDashboardBuilder()">` element in place.
  // The initial `Alpine.initTree(target)` above is a no-op for it
  // (Alpine sees the root as already-initialised), so the watcher
  // graph stays bound to the ORIGINAL Alpine proxy.
  //
  // Pre-#948 this would silently break `<template x-for="card in cards">`
  // because the cards reactive array's watcher detached from the new
  // proxy. Cards collapsed to 0. Cycle 945 fixed it via destroy +
  // re-init.
  //
  // Post-#948: cards are server-rendered HTML and the DOM is the
  // source of truth for layout — no cards array, no x-for, no
  // staleness bug class. The destroy + re-init still does the right
  // thing for ephemeral state (resets stale `saveState` / `showPicker`
  // and re-attaches the grid-container event delegation listeners),
  // so we keep the pattern as defense-in-depth. The trigger is now
  // the workspace root's `data-workspace-name` attribute rather than
  // the (removed) `#dz-workspace-layout` data island.
  const root =
    (target.querySelector && target.querySelector("[data-workspace-name]")) ||
    document.querySelector("[data-workspace-name]");
  if (!root || !window.Alpine) return;
  // Skip when the swap target isn't the root or its parent — avoids
  // re-init on unrelated swaps (e.g. drawer content) that happen to
  // share a page with the workspace root.
  if (target !== root && !target.contains(root) && !root.contains(target)) {
    return;
  }

  if (
    typeof window.Alpine.destroyTree === "function" &&
    typeof window.Alpine.initTree === "function"
  ) {
    window.Alpine.destroyTree(root);
    window.Alpine.initTree(root);
  }
});

// #964: skip Alpine event-listener directives during idiomorph attribute morph.
//
// idiomorph's attribute-morph loop (`s.value of newElement.attributes`) calls
// `target.setAttribute(s.name, s.value)` for every attribute. Alpine's
// event-listener shorthand uses `@`-prefixed attribute names (`@click`,
// `@click.away`, etc.). Chromium enforces the HTML attribute-name production
// strictly and rejects `@` — Firefox / Safari accept it silently. The
// resulting `InvalidCharacterError` is logged once per morph; functionally
// the page still renders because Alpine has already wired the event listener
// at init time and doesn't need the attribute mirrored.
//
// The fix is to install a one-time `beforeAttributeUpdated` callback on
// `Idiomorph.defaults.callbacks` that returns `false` for any `@`-prefixed
// attribute name. The skip is safe because Alpine event directives are
// `addEventListener` registrations, not attribute state — there's nothing
// to morph. The same callback is the idiomatic surface for `value` /
// `ignoreActiveValue` skips inside idiomorph itself, so this isn't a hack.
//
// Guard for late Idiomorph loads via DOMContentLoaded; in practice Idiomorph
// is bundled in `dazzle.min.js` ahead of this file, so the patch installs
// synchronously on first script execution.
(function patchIdiomorphForAlpineDirectives() {
  function install() {
    const Idiomorph = /** @type {any} */ (window).Idiomorph;
    if (!Idiomorph || !Idiomorph.defaults || !Idiomorph.defaults.callbacks) {
      return false;
    }
    const callbacks = Idiomorph.defaults.callbacks;
    const original = callbacks.beforeAttributeUpdated;
    if (callbacks.__dzAlpinePatched) return true;
    callbacks.beforeAttributeUpdated = function (name, element, mutationType) {
      // Alpine event directives never need to be morphed — they're managed
      // via addEventListener. Returning false signals idiomorph to skip.
      if (typeof name === "string" && name.charCodeAt(0) === 64 /* '@' */) {
        return false;
      }
      // Defer to any previously-installed callback for non-@ attributes.
      if (typeof original === "function") {
        return original.call(this, name, element, mutationType);
      }
      return undefined;
    };
    callbacks.__dzAlpinePatched = true;
    return true;
  }
  if (!install()) {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  }
})();

// #967: silence console errors from htmx-ext-preload speculative fetches
// that hit a 401/403.
//
// `htmx-ext-preload` fires on hover/mousedown for any link annotated with
// `hx-boost` (or explicit `preload`), warming the cache so the real
// navigation feels instant. Each prefetch carries `HX-Preloaded: true` so
// the server can identify it. When a low-privilege persona hovers a link
// they don't have permission for, the prefetch returns 401/403 — and
// htmx's standard `htmx:responseError` event bubbles to the browser
// console as a logged error. The user never clicked anything; the noise
// is pure speculative-fetch artifact and drowns real signal.
//
// Fix: a `htmx:responseError` listener that consumes (preventDefault) the
// event when (a) the request was a prefetch (HX-Preloaded header) AND
// (b) the status is 401 or 403. Real user-clicked navigations to a
// 401/403 still log normally — those are signal, not noise.
document.body.addEventListener("htmx:responseError", (e) => {
  const detail = /** @type {any} */ (e).detail;
  if (!detail || !detail.xhr || !detail.requestConfig) return;
  const status = detail.xhr.status;
  if (status !== 401 && status !== 403) return;
  const headers = detail.requestConfig.headers || {};
  if (headers["HX-Preloaded"] !== "true") return;
  // Speculative prefetch + auth denied — silently consume.
  e.preventDefault();
  e.stopPropagation();
});

// #970: ref-entity filter dropdown population.
//
// Previously this was inline `<template x-for="opt in options">` inside
// the `<select>`. Idiomorph's attribute-morph loop evaluated the cloned
// `<option>` elements' `:value` / `x-text` bindings before Alpine
// re-established the x-for scope, throwing
// `Alpine Expression Error: opt is not defined` once per option per
// morph (300 errors / 5min in AegisMark site-fuzz on v0.63.11).
//
// Fix: render `<option>` elements via direct DOM manipulation in this
// helper. `x-init="dzFilterRefSelect($el)"` invokes it once when Alpine
// first hydrates the `<select>`. The morph then sees ordinary DOM nodes
// with no Alpine attributes — nothing for idiomorph to evaluate
// prematurely. Same fix shape as #964 (skip Alpine event attrs in
// morph) and #968 (single-quote attrs containing tojson) — all
// "remove the surface idiomorph trips on" rather than "make idiomorph
// understand Alpine."
//
// Reads two data-* attributes from the <select>:
//   - data-ref-api: API endpoint (e.g. /clients) to fetch options from
//   - data-selected-value: the persisted filter value to pre-select
//
// Both are HTML-escaped server-side (no tojson-in-attr footgun).
window.dz = window.dz || {};
window.dz.filterRefSelect = function (selectEl) {
  if (!selectEl || selectEl.tagName !== "SELECT") return;
  const refApi = selectEl.dataset.refApi;
  if (!refApi) return;
  const selectedValue = selectEl.dataset.selectedValue || "";
  // #973 (round 2): wire AbortController to both htmx:beforeSwap and
  // pagehide. Round 1 only checked `document.body.contains(selectEl)`
  // in .catch — that worked for in-page htmx swaps but not for full
  // browser navigation (Playwright `page.goto`, link clicks, form
  // submits). On full nav the fetch rejects with `TypeError: Failed
  // to fetch` BEFORE the element leaves the DOM, so the contains-
  // check fired too early and the warn still logged.
  //
  // The robust discriminator is an explicit AbortController. We trip
  // it on:
  //   - htmx:beforeSwap (htmx is about to morph the DOM under us)
  //   - pagehide (full browser navigation, also covers BFCache)
  // Both fire BEFORE the fetch is cancelled, so the rejection arrives
  // as a known AbortError we can swallow cleanly.
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  window.addEventListener("htmx:beforeSwap", onAbort, { once: true });
  window.addEventListener("pagehide", onAbort, { once: true });

  fetch(refApi + "?page_size=100", {
    headers: { Accept: "application/json" },
    signal: controller.signal,
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const items = data.items || [];
      const display = (item) => {
        return (
          item.__display__ ||
          item.name ||
          item.company_name ||
          ((item.first_name || "") + " " + (item.last_name || "")).trim() ||
          item.title ||
          item.label ||
          item.email ||
          item.id ||
          ""
        );
      };
      const fragment = document.createDocumentFragment();
      for (const item of items) {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = display(item);
        if (String(item.id) === String(selectedValue)) {
          opt.selected = true;
        }
        fragment.appendChild(opt);
      }
      selectEl.appendChild(fragment);
    })
    .catch((err) => {
      // Explicit AbortError from our controller — silent. Covers both
      // htmx swap and full-browser-nav cancellation paths.
      if (err && err.name === "AbortError") return;
      // Defense-in-depth: if the element is gone (e.g. ancestor
      // removed without firing one of our abort signals), still
      // swallow.
      if (!document.body.contains(selectEl)) return;
      console.warn("Filter ref-entity load failed for", refApi, ":", err);
    })
    .finally(() => {
      // Detach listeners — listener accumulation across many filter
      // dropdowns on one page would otherwise grow unbounded. After
      // pagehide this is moot (page going away) but harmless.
      window.removeEventListener("htmx:beforeSwap", onAbort);
      window.removeEventListener("pagehide", onAbort);
    });
};
// Alpine x-init reads the function from the global scope by bare name.
window.dzFilterRefSelect = window.dz.filterRefSelect;
