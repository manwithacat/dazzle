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
            const ids = [];
            grid.querySelectorAll("[data-card-id]").forEach((el) => {
              ids.push(el.dataset.cardId);
            });
            const cardMap = {};
            this.cards.forEach((c) => {
              cardMap[c.id] = c;
            });
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
