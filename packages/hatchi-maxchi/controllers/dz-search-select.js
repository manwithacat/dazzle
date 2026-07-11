/* HYPERPART: search-select */
/*
 * dz-search-select — open/close for the typeahead combobox.
 *
 * Contract:
 *   - root: `[data-dz-widget="search_select"]` (class `dz-search-select`)
 *   - open:  runtime `data-dz-open` on the root (CSS hides results off it);
 *            not part of the static DOM_CONTRACT seed
 *   - data-dz-blur-grace-ms (default 200): after focus leaves the widget,
 *     wait this long before closing so a result-row click (which blurs the
 *     input first) can land its htmx request
 *   - data-dz-confirm-dwell-ms (default 1500): after a select exchange paints
 *     `.dz-select-result-confirm`, keep the panel open this long so the
 *     confirmation is readable; then close. 0 = close as soon as focus leaves
 *     (confirm may never be seen — prefer >0 when the confirm is the UX)
 *
 * The root — not the input — carries open state because the select
 * exchange OOB-replaces the input (`hx-swap-oob`), which would orphan
 * input-anchored state. `aria-expanded` on the combobox input stays in
 * sync whenever the input still exists.
 *
 * Focus entering the input opens; focus leaving the widget closes after
 * blur-grace — unless a confirm fragment is showing, in which case
 * confirm-dwell owns the close.
 */
(function () {
  "use strict";

  var DEFAULT_BLUR_GRACE_MS = 200;
  var DEFAULT_CONFIRM_DWELL_MS = 1500;

  /** @type {WeakMap<Element, number>} */
  var closeTimers = new WeakMap();

  function readMs(root, attr, fallback) {
    var raw = root.getAttribute(attr);
    if (raw === null || raw === "") return fallback;
    var n = parseInt(raw, 10);
    return isNaN(n) || n < 0 ? fallback : n;
  }

  function blurGraceMs(root) {
    return readMs(root, "data-dz-blur-grace-ms", DEFAULT_BLUR_GRACE_MS);
  }

  function confirmDwellMs(root) {
    return readMs(root, "data-dz-confirm-dwell-ms", DEFAULT_CONFIRM_DWELL_MS);
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
      return;
    }
    var id = setTimeout(function () {
      closeTimers.delete(root);
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
    return root.querySelector(".dz-search-select-results");
  }

  function hasConfirm(root) {
    var results = resultsOf(root);
    return !!(results && results.querySelector(".dz-select-result-confirm"));
  }

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    clearCloseTimer(root);
    setOpen(root, true);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    var grace = blurGraceMs(root);
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      // Select exchange just painted a confirm — dwell owns the close.
      if (hasConfirm(root)) return;
      setOpen(root, false);
    }, grace);
  });

  // After a select (or any swap into the listbox), if confirm is present
  // hold the panel open for confirm-dwell so the message is readable.
  function onAfterSwap(evt) {
    var target = evt.target;
    if (!target || !target.closest) return;
    if (!target.classList || !target.classList.contains("dz-search-select-results")) {
      // htmx may fire on the swapped content's parent; also accept when
      // the event target is inside the results panel.
      target = target.closest(".dz-search-select-results");
      if (!target) return;
    }
    var root = rootOf(target);
    if (!root) return;
    if (!target.querySelector(".dz-select-result-confirm")) return;
    clearCloseTimer(root);
    setOpen(root, true);
    scheduleClose(root, confirmDwellMs(root));
  }

  // htmx-4 colon names + legacy camelCase (gallery mock / dual-bind)
  document.addEventListener("htmx:after:swap", onAfterSwap);
  document.addEventListener("htmx:afterSwap", onAfterSwap);
})();
