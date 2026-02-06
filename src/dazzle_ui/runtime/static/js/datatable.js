/** @ts-check */
/* eslint-disable no-undef */

/**
 * Alpine.js data component for DataTable interactions.
 * Manages sort state, column visibility, and coordinated filter/search reloads.
 *
 * @param {{ tableId: string, columns: Array<{key: string, label: string}>, sortField: string, sortDir: string, apiEndpoint: string }} config
 */
function dazzleTable(config) {
  const storageKey = `dz-cols-${config.tableId}`;
  const saved = localStorage.getItem(storageKey);
  return {
    tableId: config.tableId,
    allColumns: config.columns || [],
    sortField: config.sortField || "",
    sortDir: config.sortDir || "asc",
    apiEndpoint: config.apiEndpoint || "",
    hiddenColumns: saved ? JSON.parse(saved) : [],
    colMenuOpen: false,

    /** Toggle sort on a column header click. */
    toggleSort(field) {
      if (this.sortField === field) {
        this.sortDir = this.sortDir === "asc" ? "desc" : "asc";
      } else {
        this.sortField = field;
        this.sortDir = "asc";
      }
      this.reload();
    },

    /** Toggle visibility of a column by key. */
    toggleColumn(key) {
      const idx = this.hiddenColumns.indexOf(key);
      if (idx >= 0) {
        this.hiddenColumns.splice(idx, 1);
      } else {
        this.hiddenColumns.push(key);
      }
      localStorage.setItem(storageKey, JSON.stringify(this.hiddenColumns));
    },

    /** Check if a column is visible. */
    isVisible(key) {
      return !this.hiddenColumns.includes(key);
    },

    /** Trigger an HTMX reload of the table body with current state. */
    reload() {
      const target = document.getElementById(`${this.tableId}-body`);
      if (target && typeof htmx !== "undefined") {
        htmx.ajax("GET", this.buildUrl(), {
          target,
          swap: "innerHTML",
          headers: { Accept: "text/html" },
        });
      }
    },

    /** Build the API URL with current sort/filter/search state. */
    buildUrl() {
      const p = new URLSearchParams();
      if (this.sortField) p.set("sort", this.sortField);
      p.set("dir", this.sortDir);
      p.set("page", "1");

      const el = document.getElementById(this.tableId);
      if (el) {
        el.querySelectorAll('[name^="filter["]').forEach(function (input) {
          if (input.value) p.set(input.name, input.value);
        });
        const searchInput = el.querySelector('[name="search"]');
        if (searchInput && searchInput.value) {
          p.set("search", searchInput.value);
        }
      }
      return `${this.apiEndpoint}?${p.toString()}`;
    },
  };
}
