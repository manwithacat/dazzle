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
 *
 * Hidden FK honesty (cycle 2118): the select exchange writes the id
 * server-side (never invent a selected id here). Typing in the
 * typeahead *clears* a stale FK — same class as money empty→clear
 * minor — and setCustomValidity blocks submit when the field is
 * required but the text is no longer a confirmed selection.
 *
 * Empty-query honesty (cycle 2126): whitespace / empty typeahead must
 * not hx-get a canned hit list. Restore the author's prompt node
 * (WeakMap clone — never write markup from a data attr; CodeQL
 * js/xss-through-dom #223). Same class as search-box empty query
 * (2123) and grid whitespace q= (2125).
 *
 * Leftover-query honesty (cycle 2138): leftover typed text ("zzz")
 * must reach the search exchange as name=q (form="" so leftover is
 * not posted with the hidden FK). The exchange must filter — leftover
 * non-match is empty, not a canned Aurora list. Same class as command
 * leftover query inventing the catalog (2130).
 */
(function () {
  "use strict";

  var DEFAULT_BLUR_GRACE_MS = 200;
  var DEFAULT_CONFIRM_HOLD_MS = 1500;
  var FALLBACK_PROMPT = "Type to search";
  /** @type {WeakMap<Element, Element>} */
  var promptByRoot = new WeakMap();

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
      DEFAULT_BLUR_GRACE_MS,
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
      DEFAULT_CONFIRM_HOLD_MS,
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

  function promptOf(results) {
    if (!results) return null;
    return (
      results.querySelector(".dz-search-select-prompt") ||
      results.querySelector(".search-select-prompt")
    );
  }

  function fallbackPrompt() {
    var d = document.createElement("div");
    d.className = "dz-search-select-prompt search-select-prompt";
    d.setAttribute("role", "option");
    d.setAttribute("aria-disabled", "true");
    d.textContent = FALLBACK_PROMPT;
    return d;
  }

  function cachePrompt(root) {
    if (promptByRoot.has(root)) return;
    var prompt = promptOf(resultsOf(root));
    promptByRoot.set(root, prompt ? prompt.cloneNode(true) : fallbackPrompt());
  }

  function restorePrompt(root) {
    var results = resultsOf(root);
    if (!results) return;
    cachePrompt(root);
    var node = promptByRoot.get(root) || fallbackPrompt();
    results.textContent = "";
    results.appendChild(node.cloneNode(true));
  }

  function onEmptyQuery(evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    var input =
      t.closest(".dz-search-select-input") || t.closest(".search-select-input");
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    cachePrompt(root);
    if (String(input.value || "").trim()) return;
    // Capture + stop so htmx and the gallery mock never exchange an
    // empty q. Restore the prompt — do not leave stale Aurora rows.
    // stopImmediatePropagation would skip the bubble clearStaleFk
    // listener, so clear here.
    clearStaleFk(root, input);
    evt.stopImmediatePropagation();
    restorePrompt(root);
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

  function typeaheadOf(root) {
    return (
      root.querySelector(".dz-search-select-input") ||
      root.querySelector(".search-select-input")
    );
  }

  function hiddenFkOf(root) {
    return root.querySelector('input[type="hidden"]');
  }

  function isRequiredTypeahead(input) {
    return (
      input.hasAttribute("required") ||
      input.getAttribute("aria-required") === "true"
    );
  }

  function clearStaleFk(root, input) {
    var hidden = hiddenFkOf(root);
    if (hidden) hidden.value = "";
    if (!input) return;
    if (isRequiredTypeahead(input) && input.value.trim()) {
      input.setCustomValidity("Select a value from the list");
    } else {
      input.setCustomValidity("");
    }
  }

  function clearFkValidity(root) {
    var input = typeaheadOf(root);
    if (input) input.setCustomValidity("");
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
    true,
  );

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) {
      input = evt.target.closest && evt.target.closest(".search-select-input");
    }
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    selecting.delete(root);
    clearCloseTimer(root);
    setOpen(root, true);
    cachePrompt(root);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) {
      input = evt.target.closest && evt.target.closest(".search-select-input");
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
    clearFkValidity(root);
    scheduleClose(root, confirmHoldMs(root));
  }

  document.addEventListener("input", onEmptyQuery, true);
  document.addEventListener("keyup", onEmptyQuery, true);

  document.addEventListener("input", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) {
      input = evt.target.closest && evt.target.closest(".search-select-input");
    }
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    clearStaleFk(root, input);
  });

  document.addEventListener("htmx:after:swap", onAfterSwap);
  document.addEventListener("htmx:afterSwap", onAfterSwap);
  document.addEventListener("htmx:after:settle", onAfterSwap);
  document.addEventListener("htmx:afterSettle", onAfterSwap);
})();
