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
 */

document.addEventListener("alpine:init", () => {
  const Alpine = window.Alpine;

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

  Alpine.data("dzTable", (tableId, endpoint, initSortField, initSortDir) => ({
    sortField: initSortField || "",
    sortDir: initSortDir || "asc",
    hiddenColumns: JSON.parse(
      localStorage.getItem(`dz-cols-${tableId}`) || "[]",
    ),
    selected: new Set(),
    bulkCount: 0,
    colMenuOpen: false,

    init() {
      this.applyColumnVisibility();
      // Inject selected IDs into htmx bulk action requests
      this.$el.addEventListener("htmx:configRequest", (e) => {
        const detail = /** @type {CustomEvent} */ (e).detail;
        if (detail.elt.hasAttribute("data-dz-bulk-action")) {
          detail.parameters["ids"] = Array.from(this.selected);
        }
      });
    },

    // Sort
    toggleSort(field) {
      if (this.sortField === field) {
        this.sortDir = this.sortDir === "asc" ? "desc" : "asc";
      } else {
        this.sortField = field;
        this.sortDir = "asc";
      }
      this.reload();
    },

    sortIcon(field) {
      if (this.sortField !== field) return "hidden";
      return this.sortDir === "desc" ? "rotate-180" : "";
    },

    ariaSortDir(field) {
      if (this.sortField !== field) return null;
      return this.sortDir + "ending";
    },

    // Column visibility
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

    // Bulk select
    toggleSelectAll(checked) {
      if (checked) {
        this.$el
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
      this.$el.querySelectorAll("[data-dz-row-select]").forEach((input) => {
        const id =
          input.closest("[data-dz-row-id]")?.getAttribute("data-dz-row-id") ||
          "";
        /** @type {HTMLInputElement} */ (input).checked = this.selected.has(id);
      });
    },

    // HTMX reload with current state
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
});
