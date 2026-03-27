/**
 * workspace-editor.js — Alpine.js component for workspace layout customization.
 *
 * Manages edit mode: drag-to-reorder (via alpine-sort), show/hide toggle,
 * and col-span width snapping. Persists layout to user preferences.
 */

document.addEventListener("alpine:init", () => {
  Alpine.data("dzWorkspaceEditor", (workspaceName) => ({
    editing: false,
    // Read layout from <script type="application/json"> data island to avoid
    // JSON-in-HTML-attribute escaping issues (#635).
    regions: (() => {
      const el = document.getElementById("dz-workspace-layout");
      if (!el) return [];
      try {
        return JSON.parse(el.textContent).regions || [];
      } catch {
        return [];
      }
    })(),
    _snapshot: null,

    toggleEdit() {
      this._snapshot = JSON.parse(JSON.stringify(this.regions));
      this.editing = true;
    },

    onReorder(item, position) {
      const names = [];
      this.$el.querySelectorAll("[data-region-name]").forEach((el) => {
        names.push(el.dataset.regionName);
      });
      const regionMap = {};
      this.regions.forEach((r) => {
        regionMap[r.name] = r;
      });
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
      this.regions.forEach((r) => {
        layout.widths[r.name] = r.col_span;
      });
      const key = "workspace." + workspaceName + ".layout";
      const prefs = {};
      prefs[key] = JSON.stringify(layout);
      fetch("/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: prefs }),
      }).then(() => {
        this.editing = false;
        if (window.dz?.toast) window.dz.toast("Layout saved", "success");
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
