/** @ts-check */
/**
 * dz.js — Dazzle micro-runtime. Replaces Alpine.js (~15 KB) with ~2 KB of
 * targeted utilities for the patterns Dazzle actually uses.
 *
 * Provides:
 *  - dz.persist(key, fallback)  — localStorage read/write helper
 *  - dz.toggle(el)              — open/close state for dropdowns/modals/panels
 *  - dz.toast(message, type)    — toast notification API
 *  - dz.table(config)           — datatable sort/column/bulk-select state
 *  - Event delegation for [data-dz-*] attributes
 *
 * Zero dependencies. No build step. ~2 KB minified+gzipped.
 */

const dz = (() => {
  "use strict";

  // ── Persistence ──────────────────────────────────────────────────────

  /** @param {string} key @param {*} fallback */
  function persist(key, fallback) {
    const raw = localStorage.getItem(key);
    return raw !== null ? JSON.parse(raw) : fallback;
  }

  /** @param {string} key @param {*} value */
  function save(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  // ── Dark Mode ────────────────────────────────────────────────────────

  function initDarkMode() {
    const dark = persist("dz-dark-mode", false);
    applyDarkMode(dark);

    document.addEventListener("click", (e) => {
      const btn = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-dark-toggle]",
      );
      if (!btn) return;
      const next = !persist("dz-dark-mode", false);
      save("dz-dark-mode", next);
      applyDarkMode(next);
    });
  }

  /** @param {boolean} dark */
  function applyDarkMode(dark) {
    const root = document.documentElement;
    root.setAttribute("data-theme", dark ? "dark" : "light");
    root.classList.toggle("dark", dark);
    // Update icon visibility
    document.querySelectorAll("[data-dz-dark-icon]").forEach((el) => {
      const show = el.getAttribute("data-dz-dark-icon");
      /** @type {HTMLElement} */ (el).style.display =
        (show === "dark") === dark ? "" : "none";
    });
    // Update label text
    document.querySelectorAll("[data-dz-dark-label]").forEach((el) => {
      el.textContent = dark ? "Light mode" : "Dark mode";
    });
  }

  // ── Sidebar ──────────────────────────────────────────────────────────

  function initSidebar() {
    const open = persist("dz-sidebar", true);
    applySidebar(open);

    document.addEventListener("click", (e) => {
      const btn = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-sidebar-toggle]",
      );
      if (!btn) return;
      const action = btn.getAttribute("data-dz-sidebar-toggle");
      const next =
        action === "open"
          ? true
          : action === "close"
            ? false
            : !persist("dz-sidebar", true);
      save("dz-sidebar", next);
      applySidebar(next);
    });
  }

  /** @param {boolean} open */
  function applySidebar(open) {
    const drawer = document.querySelector("[data-dz-sidebar]");
    if (!drawer) return;
    // Use data attribute value — CSS in dz.css handles responsive behavior.
    // DaisyUI CDN does not include lg:drawer-open variant styles, so we
    // replicate them with [data-dz-sidebar="open"] selectors in dz.css.
    drawer.setAttribute("data-dz-sidebar", open ? "open" : "");
    // Show/hide expand button
    document.querySelectorAll("[data-dz-sidebar-expand]").forEach((el) => {
      /** @type {HTMLElement} */ (el).style.display = open ? "none" : "";
    });
  }

  // ── Toggle (dropdowns, modals, panels) ───────────────────────────────

  function initToggles() {
    // Click to toggle
    document.addEventListener("click", (e) => {
      const trigger = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-toggle]",
      );
      if (trigger) {
        e.stopPropagation();
        const targetSel = trigger.getAttribute("data-dz-toggle");
        const target = targetSel
          ? trigger.closest("[data-dz-toggleable]") ||
            document.querySelector(targetSel)
          : trigger.closest("[data-dz-toggleable]");
        if (target) toggleOpen(/** @type {HTMLElement} */ (target));
        return;
      }

      // Click to close
      const closer = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-close]",
      );
      if (closer) {
        const container = closer.closest("[data-dz-toggleable]");
        if (container) setOpen(/** @type {HTMLElement} */ (container), false);
        return;
      }

      // Click-away: close any open toggleable not containing the click target
      document
        .querySelectorAll("[data-dz-toggleable][data-dz-open]")
        .forEach((el) => {
          if (!el.contains(/** @type {Node} */ (e.target))) {
            setOpen(/** @type {HTMLElement} */ (el), false);
          }
        });
    });

    // Escape key closes all
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document
          .querySelectorAll("[data-dz-toggleable][data-dz-open]")
          .forEach((el) => setOpen(/** @type {HTMLElement} */ (el), false));
      }
    });
  }

  /** @param {HTMLElement} el */
  function toggleOpen(el) {
    setOpen(el, !el.hasAttribute("data-dz-open"));
  }

  /** @param {HTMLElement} el @param {boolean} open */
  function setOpen(el, open) {
    if (open) {
      el.setAttribute("data-dz-open", "");
    } else {
      el.removeAttribute("data-dz-open");
    }
    // Show/hide children marked as toggle targets
    el.querySelectorAll("[data-dz-show]").forEach((child) => {
      /** @type {HTMLElement} */ (child).style.display = open ? "" : "none";
    });
    // Toggle chevron rotation
    el.querySelectorAll("[data-dz-rotate]").forEach((child) => {
      /** @type {HTMLElement} */ (child).classList.toggle("rotate-180", open);
    });
  }

  // ── Dialog (native <dialog>) ─────────────────────────────────────────

  function initDialogs() {
    // Open a dialog via event dispatch
    document.addEventListener("click", (e) => {
      const trigger = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-dialog]",
      );
      if (!trigger) return;
      const dialogId = trigger.getAttribute("data-dz-dialog");
      const dialog = /** @type {HTMLDialogElement|null} */ (
        document.getElementById(dialogId || "")
      );
      if (!dialog) return;

      // Pass data to the dialog via dataset
      const message = trigger.getAttribute("data-dz-confirm-message");
      const action = trigger.getAttribute("data-dz-confirm-action");
      const method = trigger.getAttribute("data-dz-confirm-method") || "delete";
      const target = trigger.getAttribute("data-dz-confirm-target") || "";
      const swap = trigger.getAttribute("data-dz-confirm-swap") || "outerHTML";
      if (message) {
        const msgEl = dialog.querySelector("[data-dz-dialog-message]");
        if (msgEl) msgEl.textContent = message;
      }
      dialog.dataset.action = action || "";
      dialog.dataset.method = method;
      dialog.dataset.target = target;
      dialog.dataset.swap = swap;
      // Store reference to triggering element for htmx context
      dialog._dzTrigger = trigger;

      dialog.showModal();
    });

    // Confirm button inside dialog
    document.addEventListener("click", (e) => {
      const btn = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-dialog-confirm]",
      );
      if (!btn) return;
      const dialog = /** @type {HTMLDialogElement} */ (btn.closest("dialog"));
      if (!dialog) return;
      const action = dialog.dataset.action;
      const method = (dialog.dataset.method || "delete").toUpperCase();
      if (!action) return;

      btn.classList.add("loading");
      btn.setAttribute("disabled", "");

      // Build htmx.ajax options
      const opts = /** @type {Object} */ ({});
      const targetSel = dialog.dataset.target;
      if (targetSel) {
        opts.target = targetSel;
        opts.swap = dialog.dataset.swap || "outerHTML";
      } else if (dialog._dzTrigger) {
        // Default: target the trigger's nearest row/container
        const tr = dialog._dzTrigger.closest("tr");
        if (tr) {
          opts.target = tr;
          opts.swap = "outerHTML swap:300ms";
        } else {
          opts.target = "body";
          opts.swap = "innerHTML";
        }
      }

      htmx
        .ajax(method, action, opts)
        .then(() => {
          dialog.close();
          resetConfirmBtn(btn);
          dialog._dzTrigger = null;
        })
        .catch(() => {
          resetConfirmBtn(btn);
        });
    });

    /** @param {HTMLElement} btn */
    function resetConfirmBtn(btn) {
      btn.classList.remove("loading");
      btn.removeAttribute("disabled");
    }
  }

  // ── Slide-over Panel ─────────────────────────────────────────────────

  function initSlideOver() {
    document.addEventListener("open-slide-over", (e) => {
      const panel = document.querySelector("[data-dz-slide-over]");
      if (panel) setOpen(/** @type {HTMLElement} */ (panel), true);
    });
  }

  // ── Toast Notifications ──────────────────────────────────────────────

  /** @param {string} message @param {string} [type] */
  function toast(message, type = "info") {
    const container = document.getElementById("dz-toast");
    if (!container) return;
    const alert = document.createElement("div");
    alert.className = `alert alert-${type} dz-toast-enter`;
    alert.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(alert);
    // Trigger enter animation
    requestAnimationFrame(() => alert.classList.remove("dz-toast-enter"));
    // Auto-remove
    setTimeout(() => {
      alert.classList.add("dz-toast-leave");
      alert.addEventListener("transitionend", () => alert.remove());
      // Fallback removal if transition doesn't fire
      setTimeout(() => alert.remove(), 500);
    }, 4000);
  }

  function initToasts() {
    // Listen for custom event (same API as current Alpine toast)
    window.addEventListener("dz-toast", (e) => {
      const detail = /** @type {CustomEvent} */ (e).detail;
      toast(detail.message, detail.type);
    });
  }

  // ── HTMX Server Events ──────────────────────────────────────────────

  function initHtmxEvents() {
    // Listen for HX-Trigger events from server responses.
    // The server sends JSON triggers like:
    //   {"showToast": {"message": "...", "type": "success"}, "entityCreated": {"entity": "Task"}}
    // HTMX automatically fires these as DOM events on the triggering element,
    // but we listen on the body so we catch them all.

    /** @param {Event} e */
    function handleShowToast(e) {
      const detail = /** @type {CustomEvent} */ (e).detail;
      if (detail && detail.message) {
        toast(detail.message, detail.type || "success");
      }
    }

    document.body.addEventListener("showToast", handleShowToast);
  }

  // ── Inline Edit ──────────────────────────────────────────────────────

  function initInlineEdit() {
    // Click to enter edit mode (supports both <span> and <button> triggers)
    document.addEventListener("click", (e) => {
      const display = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-inline-display]",
      );
      if (!display) return;
      const container = display.closest("[data-dz-inline-edit]");
      if (!container) return;
      const form = container.querySelector("form");
      const input = container.querySelector("input[name]");
      /** @type {HTMLElement} */ (display).style.display = "none";
      if (form) /** @type {HTMLElement} */ (form).style.display = "";
      if (input) /** @type {HTMLInputElement} */ (input).focus();
    });

    // Escape to cancel
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const input = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-inline-edit] input",
      );
      if (!input) return;
      const container = input.closest("[data-dz-inline-edit]");
      if (container) closeInlineEdit(/** @type {HTMLElement} */ (container));
    });

    // Click-away to cancel
    document.addEventListener("click", (e) => {
      document
        .querySelectorAll("[data-dz-inline-edit].dz-editing")
        .forEach((el) => {
          if (!el.contains(/** @type {Node} */ (e.target))) {
            closeInlineEdit(/** @type {HTMLElement} */ (el));
          }
        });
    });
  }

  /** @param {HTMLElement} container */
  function closeInlineEdit(container) {
    const display = container.querySelector("[data-dz-inline-display]");
    const form = container.querySelector("form");
    if (display) /** @type {HTMLElement} */ (display).style.display = "";
    if (form) /** @type {HTMLElement} */ (form).style.display = "none";
    container.classList.remove("dz-editing");
  }

  // ── Search Input (clear button) ──────────────────────────────────────

  function initSearchInputs() {
    document.addEventListener("input", (e) => {
      const input = /** @type {HTMLInputElement} */ (e.target);
      if (!input.matches("[data-dz-search-input]")) return;
      const container = input.closest("[data-dz-search]");
      if (!container) return;
      const clearBtn = container.querySelector("[data-dz-search-clear]");
      if (clearBtn) {
        /** @type {HTMLElement} */ (clearBtn).style.display =
          input.value.length > 0 ? "" : "none";
      }
    });

    document.addEventListener("click", (e) => {
      const btn = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-search-clear]",
      );
      if (!btn) return;
      const container = btn.closest("[data-dz-search]");
      if (!container) return;
      const input = /** @type {HTMLInputElement} */ (
        container.querySelector("[data-dz-search-input]")
      );
      if (input) {
        input.value = "";
        btn.style.display = "none";
        htmx.trigger(input, "keyup");
      }
    });
  }

  // ── Form Loading State ───────────────────────────────────────────────

  function initFormLoading() {
    // HTMX fires htmx:beforeRequest and htmx:afterRequest on the form element
    document.addEventListener("htmx:beforeRequest", (e) => {
      const form = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-form]",
      );
      if (!form) return;
      const btn = form.querySelector("[type=submit]");
      if (btn) {
        btn.setAttribute("disabled", "");
        btn.classList.add("loading");
      }
    });

    document.addEventListener("htmx:afterRequest", (e) => {
      const form = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-form]",
      );
      if (!form) return;
      const btn = form.querySelector("[type=submit]");
      if (btn) {
        btn.removeAttribute("disabled");
        btn.classList.remove("loading");
      }
    });
  }

  // ── Data Table ───────────────────────────────────────────────────────

  /**
   * Initialize a data table with sort, column visibility, and bulk select.
   * Replaces Alpine's dazzleTable() component.
   * @param {HTMLElement} el
   */
  function initTable(el) {
    const tableId = el.id;
    const endpoint = el.dataset.dzTableEndpoint || "";
    const colsKey = `dz-cols-${tableId}`;

    let sortField = el.dataset.dzSortField || "";
    let sortDir = el.dataset.dzSortDir || "asc";
    let hiddenColumns = persist(colsKey, []);
    /** @type {Set<string>} */
    let selected = new Set();

    applyColumnVisibility();
    updateBulkUI();

    // Sort click
    el.addEventListener("click", (e) => {
      const th = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-sort]",
      );
      if (th) {
        const field = th.getAttribute("data-dz-sort") || "";
        if (sortField === field) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortField = field;
          sortDir = "asc";
        }
        updateSortUI();
        reload();
        return;
      }

      // Column toggle
      const colToggle = /** @type {HTMLInputElement} */ (e.target).closest(
        "[data-dz-col-toggle]",
      );
      if (colToggle && colToggle.tagName === "INPUT") {
        const key = colToggle.getAttribute("data-dz-col-toggle") || "";
        const idx = hiddenColumns.indexOf(key);
        if (idx >= 0) hiddenColumns.splice(idx, 1);
        else hiddenColumns.push(key);
        save(colsKey, hiddenColumns);
        applyColumnVisibility();
        return;
      }

      // Select-all checkbox
      const selectAll = /** @type {HTMLInputElement} */ (e.target).closest(
        "[data-dz-select-all]",
      );
      if (selectAll && selectAll.tagName === "INPUT") {
        if (selectAll.checked) {
          el.querySelectorAll("[data-dz-row-id]").forEach((row) =>
            selected.add(row.getAttribute("data-dz-row-id") || ""),
          );
        } else {
          selected.clear();
        }
        syncCheckboxes();
        updateBulkUI();
        return;
      }

      // Row checkbox
      const rowCheck = /** @type {HTMLInputElement} */ (e.target).closest(
        "[data-dz-row-select]",
      );
      if (rowCheck && rowCheck.tagName === "INPUT") {
        const id =
          rowCheck
            .closest("[data-dz-row-id]")
            ?.getAttribute("data-dz-row-id") || "";
        if (rowCheck.checked) selected.add(id);
        else selected.delete(id);
        updateBulkUI();
        return;
      }

      // Bulk clear
      const clearBtn = /** @type {HTMLElement} */ (e.target).closest(
        "[data-dz-bulk-clear]",
      );
      if (clearBtn) {
        selected.clear();
        syncCheckboxes();
        updateBulkUI();
        return;
      }
    });

    // Expose selected IDs for htmx hx-vals
    el.addEventListener("htmx:configRequest", (e) => {
      const detail = /** @type {CustomEvent} */ (e).detail;
      if (
        /** @type {HTMLElement} */ (detail.elt).hasAttribute(
          "data-dz-bulk-action",
        )
      ) {
        detail.parameters["ids"] = Array.from(selected);
      }
    });

    function applyColumnVisibility() {
      el.querySelectorAll("[data-dz-col]").forEach((cell) => {
        const key = cell.getAttribute("data-dz-col");
        /** @type {HTMLElement} */ (cell).style.display =
          hiddenColumns.includes(key || "") ? "none" : "";
      });
      el.querySelectorAll("[data-dz-col-toggle]").forEach((input) => {
        const key = input.getAttribute("data-dz-col-toggle");
        /** @type {HTMLInputElement} */ (input).checked =
          !hiddenColumns.includes(key || "");
      });
    }

    function updateSortUI() {
      el.querySelectorAll("[data-dz-sort]").forEach((th) => {
        const field = th.getAttribute("data-dz-sort");
        const icon = th.querySelector("[data-dz-sort-icon]");
        if (field === sortField) {
          th.setAttribute("aria-sort", sortDir + "ending");
          if (icon) {
            /** @type {HTMLElement} */ (icon).style.display = "";
            icon.classList.toggle("rotate-180", sortDir === "desc");
          }
        } else {
          th.removeAttribute("aria-sort");
          if (icon) /** @type {HTMLElement} */ (icon).style.display = "none";
        }
      });
    }

    function updateBulkUI() {
      const count = selected.size;
      const bar = el.querySelector("[data-dz-bulk-bar]");
      if (bar) {
        /** @type {HTMLElement} */ (bar).style.display =
          count > 0 ? "" : "none";
        const counter = bar.querySelector("[data-dz-bulk-count]");
        if (counter) counter.textContent = String(count);
      }
    }

    function syncCheckboxes() {
      el.querySelectorAll("[data-dz-row-select]").forEach((input) => {
        const id =
          input.closest("[data-dz-row-id]")?.getAttribute("data-dz-row-id") ||
          "";
        /** @type {HTMLInputElement} */ (input).checked = selected.has(id);
      });
    }

    function reload() {
      const target = document.getElementById(`${tableId}-body`);
      if (!target || typeof htmx === "undefined") return;
      const p = new URLSearchParams();
      if (sortField) p.set("sort", sortField);
      p.set("dir", sortDir);
      p.set("page", "1");
      el.querySelectorAll('[name^="filter["]').forEach((input) => {
        if (/** @type {HTMLInputElement} */ (input).value)
          p.set(
            input.getAttribute("name") || "",
            /** @type {HTMLInputElement} */ (input).value,
          );
      });
      const searchInput = /** @type {HTMLInputElement|null} */ (
        el.querySelector("[data-dz-search-input]")
      );
      if (searchInput?.value) p.set("search", searchInput.value);
      htmx.ajax("GET", `${endpoint}?${p}`, {
        target,
        swap: "morph:innerHTML",
        headers: { Accept: "text/html" },
      });
    }
  }

  // ── Money Inputs ───────────────────────────────────────────────────

  /** ISO 4217 currency scales (mirrors money.py CURRENCY_SCALES) */
  const CURRENCY_SCALES = {
    GBP: 2, USD: 2, EUR: 2, AUD: 2, CAD: 2, CHF: 2, CNY: 2, INR: 2,
    NZD: 2, SGD: 2, HKD: 2, SEK: 2, NOK: 2, DKK: 2, ZAR: 2, MXN: 2,
    BRL: 2, JPY: 0, KRW: 0, VND: 0, CLP: 0, ISK: 0, BHD: 3, KWD: 3,
    OMR: 3, TND: 3, JOD: 3, IQD: 3, LYD: 3,
  };

  /**
   * Initialize a single money field container.
   * @param {HTMLElement} container — element with [data-dz-money]
   */
  function initMoneyField(container) {
    const displayInput = /** @type {HTMLInputElement|null} */ (
      container.querySelector("[data-dz-money-display]")
    );
    const hiddenMinor = /** @type {HTMLInputElement|null} */ (
      container.querySelector("[data-dz-money-minor]")
    );
    const currencyEl = container.querySelector("[data-dz-money-currency]");
    if (!displayInput || !hiddenMinor) return;

    function getScale() {
      // For select-based (unpinned), read from selected option
      if (currencyEl && currencyEl.tagName === "SELECT") {
        const opt = /** @type {HTMLSelectElement} */ (currencyEl).selectedOptions[0];
        if (opt && opt.dataset.scale !== undefined) return parseInt(opt.dataset.scale, 10);
      }
      // Fallback: container data-dz-scale or lookup by currency
      const scaleAttr = container.getAttribute("data-dz-scale");
      if (scaleAttr !== null) return parseInt(scaleAttr, 10);
      const code = container.getAttribute("data-dz-currency") || "GBP";
      return CURRENCY_SCALES[code] !== undefined ? CURRENCY_SCALES[code] : 2;
    }

    /** @param {string} val @returns {number} */
    function toMinor(val) {
      const num = parseFloat(val);
      if (isNaN(num)) return 0;
      return Math.round(num * Math.pow(10, getScale()));
    }

    /** @param {string} val @returns {string} */
    function toDisplay(val) {
      const num = parseInt(val, 10);
      if (isNaN(num)) return "";
      const scale = getScale();
      return (num / Math.pow(10, scale)).toFixed(scale);
    }

    // Populate display from hidden minor on load (edit mode)
    if (hiddenMinor.value && !displayInput.value) {
      displayInput.value = toDisplay(hiddenMinor.value);
    }

    // Sync on input
    displayInput.addEventListener("input", () => {
      hiddenMinor.value = String(toMinor(displayInput.value));
    });

    // Format on blur
    displayInput.addEventListener("blur", () => {
      const val = displayInput.value.trim();
      if (val === "") {
        hiddenMinor.value = "";
        return;
      }
      const minor = toMinor(val);
      hiddenMinor.value = String(minor);
      displayInput.value = toDisplay(String(minor));
    });

    // Currency dropdown change (unpinned)
    if (currencyEl && currencyEl.tagName === "SELECT") {
      currencyEl.addEventListener("change", () => {
        const opt = /** @type {HTMLSelectElement} */ (currencyEl).selectedOptions[0];
        // Update container scale attr
        if (opt && opt.dataset.scale !== undefined) {
          container.setAttribute("data-dz-scale", opt.dataset.scale);
        }
        // Update prefix symbol if present
        const prefix = container.querySelector(".dz-money-prefix");
        if (prefix && opt && opt.dataset.symbol) {
          prefix.textContent = opt.dataset.symbol;
        }
        // Re-convert display value with new scale
        if (displayInput.value) {
          const minor = toMinor(displayInput.value);
          hiddenMinor.value = String(minor);
          displayInput.value = toDisplay(String(minor));
        }
      });
    }

    container.dataset.dzMoneyInit = "1";
  }

  function initMoneyInputs() {
    document.querySelectorAll("[data-dz-money]").forEach((el) => {
      if (!/** @type {HTMLElement} */ (el).dataset.dzMoneyInit) {
        initMoneyField(/** @type {HTMLElement} */ (el));
      }
    });
  }

  // ── Utilities ────────────────────────────────────────────────────────

  /** @param {string} str */
  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // ── Init ─────────────────────────────────────────────────────────────

  function init() {
    initDarkMode();
    initSidebar();
    initToggles();
    initDialogs();
    initSlideOver();
    initToasts();
    initHtmxEvents();
    initInlineEdit();
    initSearchInputs();
    initFormLoading();
    initMoneyInputs();

    // Auto-init data tables
    document.querySelectorAll("[data-dz-table]").forEach((el) => {
      initTable(/** @type {HTMLElement} */ (el));
    });

    // Re-init after HTMX swaps.  Navigation uses fragment targeting
    // (#main-content) so sidebar/dark-mode state is preserved.  These
    // restores still fire for full-body swaps (forms, entity row clicks).
    document.addEventListener("htmx:afterSettle", (e) => {
      applySidebar(persist("dz-sidebar", true));
      applyDarkMode(persist("dz-dark-mode", false));

      const target = /** @type {HTMLElement} */ (
        /** @type {CustomEvent} */ (e).detail.elt
      );
      target.querySelectorAll("[data-dz-table]").forEach((el) => {
        if (!(/** @type {HTMLElement} */ (el).dataset.dzInitialized)) {
          initTable(/** @type {HTMLElement} */ (el));
        }
      });
      target.querySelectorAll("[data-dz-money]").forEach((el) => {
        if (!/** @type {HTMLElement} */ (el).dataset.dzMoneyInit) {
          initMoneyField(/** @type {HTMLElement} */ (el));
        }
      });
    });
  }

  // Run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Public API
  return { toast, persist, save };
})();
