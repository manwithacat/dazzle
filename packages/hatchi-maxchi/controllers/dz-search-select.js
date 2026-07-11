/* HYPERPART: search-select */
/*
 * dz-search-select — open/close for the typeahead combobox.
 *
 * Contract:
 *   - root: `[data-dz-widget="search_select"]` (class `dz-search-select`)
 *   - open:  runtime `data-dz-open` on the root (CSS hides results off it)
 *
 * Timing (attrs on the root; namespaced form is `data-dz-*`, gallery may strip):
 *   - data-dz-blur-grace-ms (default 200): after focus leaves, wait before
 *     closing so a result-row click (blur-then-click) can fire htmx.
 *   - data-dz-confirm-hold-ms (default 1500): after a select exchange paints
 *     `.dz-select-result-confirm`, keep the panel open this long so the
 *     confirmation is readable; then close. 0 = no hold (close with blur).
 *     Alias: data-dz-confirm-dwell-ms (same meaning).
 *
 * All close paths share one timer (scheduleClose). Select hold always
 * cancels a pending blur-grace close — the previous race left blur on a
 * raw setTimeout that clearCloseTimer could not cancel.
 *
 * pointerdown on a result row marks "selecting" so blur-grace will not
 * close before the swap; after:swap then starts the confirm hold.
 */
(function () {
  "use strict";

  var DEFAULT_BLUR_GRACE_MS = 200;
  var DEFAULT_CONFIRM_HOLD_MS = 1500;

  /** @type {WeakMap<Element, number>} */
  var closeTimers = new WeakMap();
  /** @type {WeakMap<Element, boolean>} */
  var selecting = new WeakMap();

  function readMs(root, attrs, fallback) {
    var list = typeof attrs === "string" ? [attrs] : attrs;
    for (var i = 0; i < list.length; i++) {
      var raw = root.getAttribute(list[i]);
      if (raw === null || raw === "") continue;
      var n = parseInt(raw, 10);
      if (!isNaN(n) && n >= 0) return n;
    }
    return fallback;
  }

  function blurGraceMs(root) {
    return readMs(
      root,
      ["data-dz-blur-grace-ms", "data-blur-grace-ms"],
      DEFAULT_BLUR_GRACE_MS
    );
  }

  function confirmHoldMs(root) {
    // hold = preferred; dwell = documented alias
    return readMs(
      root,
      [
        "data-dz-confirm-hold-ms",
        "data-confirm-hold-ms",
        "data-dz-confirm-dwell-ms",
        "data-confirm-dwell-ms",
      ],
      DEFAULT_CONFIRM_HOLD_MS
    );
  }

  function setOpen(root, open) {
    if (open) root.setAttribute("data-dz-open", "true");
    else root.removeAttribute("data-dz-open");
    var input = root.querySelector(".dz-search-select-input");
    if (input) input.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function clearCloseTimer(root) {
    var id = closeTimers.get(root);
    if (id !== undefined) {
      clearTimeout(id);
      closeTimers.delete(root);
    }
  }

  function scheduleClose(root, ms) {
    clearCloseTimer(root);
    if (ms <= 0) {
      setOpen(root, false);
      selecting.delete(root);
      return;
    }
    var id = setTimeout(function () {
      closeTimers.delete(root);
      selecting.delete(root);
      setOpen(root, false);
    }, ms);
    closeTimers.set(root, id);
  }

  function rootOf(el) {
    return (
      (el.closest && el.closest('[data-dz-widget="search_select"]')) ||
      (el.closest && el.closest(".dz-search-select"))
    );
  }

  function resultsOf(root) {
    return (
      root.querySelector(".dz-search-select-results") ||
      root.querySelector(".search-select-results")
    );
  }

  function hasConfirm(root) {
    var results = resultsOf(root);
    if (!results) return false;
    return !!(
      results.querySelector(".dz-select-result-confirm") ||
      results.querySelector(".select-result-confirm")
    );
  }

  function isResultRow(el) {
    return !!(
      el &&
      el.closest &&
      (el.closest(".dz-search-result-row") || el.closest(".search-result-row"))
    );
  }

  // Mark selecting on pointerdown so blur-grace will not close before swap.
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var row = isResultRow(evt.target);
      if (!row) return;
      var root = rootOf(evt.target);
      if (!root) return;
      selecting.set(root, true);
      clearCloseTimer(root);
      setOpen(root, true);
    },
    true
  );

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) {
      input =
        evt.target.closest && evt.target.closest(".search-select-input");
    }
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    selecting.delete(root);
    clearCloseTimer(root);
    setOpen(root, true);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) {
      input =
        evt.target.closest && evt.target.closest(".search-select-input");
    }
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    // Row interaction in progress — after:swap owns the hold timer.
    if (selecting.get(root)) return;
    // Confirm already showing — keep hold timer; do not replace with blur grace.
    if (hasConfirm(root)) return;
    scheduleClose(root, blurGraceMs(root));
  });

  function onAfterSwap(evt) {
    var target = evt.target;
    if (!target || !target.closest) {
      // some runtimes put the swap root on detail.elt / detail.target
      var d = evt.detail || {};
      target = d.elt || d.target || (d.ctx && d.ctx.target) || null;
    }
    if (!target || !target.closest) return;

    var results =
      (target.classList &&
        (target.classList.contains("dz-search-select-results") ||
          target.classList.contains("search-select-results")) &&
        target) ||
      target.closest(".dz-search-select-results") ||
      target.closest(".search-select-results");
    if (!results) return;

    var root = rootOf(results);
    if (!root) return;
    if (
      !results.querySelector(".dz-select-result-confirm") &&
      !results.querySelector(".select-result-confirm")
    ) {
      selecting.delete(root);
      return;
    }
    selecting.delete(root);
    clearCloseTimer(root);
    setOpen(root, true);
    scheduleClose(root, confirmHoldMs(root));
  }

  document.addEventListener("htmx:after:swap", onAfterSwap);
  document.addEventListener("htmx:afterSwap", onAfterSwap);
  document.addEventListener("htmx:after:settle", onAfterSwap);
  document.addEventListener("htmx:afterSettle", onAfterSwap);
})();
