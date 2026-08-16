/* HYPERPART: search-box */
/*
 * dz-search-box — empty query must not hx-get a silent / fake result list.
 *
 * Contract:
 *   - root: `[data-dz-search-box]` (gallery also accepts `[data-search-box]`)
 *   - input: `input[type=search]`
 *   - results: `.dz-search-box-results` / `.search-box-results`
 *
 *   input/search → if the trimmed query is empty, stop the event so the
 *            box does not hx-get. Restore the coaching empty line.
 *            Non-empty queries still exchange. Whitespace-only is empty.
 *
 * Contract already said "Empty queries aren't sent (min length 1)" but
 * the trigger had no filter — clearing after a hit swapped /mock/search
 * (always Aurora/Beacon) or a product empty region. Same honesty class
 * as date-range inverted emptying the region (cycle 2122).
 *
 * Leftover-query honesty (cycle 2148): non-empty leftover ("zzz") must
 * still exchange — the mock / product filters by name=q. Path-only
 * /mock/search invented Aurora. Same class as search-select leftover
 * (2138) and command leftover (2130).
 *
 * Re-query the DOM on every event (morph-safe). Cache a clone of the
 * author's coaching node on first touch (WeakMap — never store markup in
 * a data attribute and write it back; CodeQL js/xss-through-dom #223).
 * Restore via appendChild of a clone. Fallback is createElement +
 * textContent, never an HTML string.
 */
(function () {
  "use strict";

  var coachingByRoot = new WeakMap();
  var FALLBACK_TEXT = "Type a title or keyword";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-search-box]") || el.closest("[data-search-box]")
    );
  }

  function resultsOf(root) {
    return (
      root.querySelector(".dz-search-box-results") ||
      root.querySelector(".search-box-results")
    );
  }

  function isNoResults(el) {
    if (!el || !el.className) return false;
    return String(el.className).indexOf("no-results") !== -1;
  }

  function fallbackNode() {
    var d = document.createElement("div");
    d.className = "search-box-empty";
    d.textContent = FALLBACK_TEXT;
    return d;
  }

  function cacheCoaching(root) {
    if (coachingByRoot.has(root)) return;
    var results = resultsOf(root);
    var empty =
      results &&
      (results.querySelector(".dz-search-box-empty") ||
        results.querySelector(".search-box-empty"));
    if (empty && !isNoResults(empty)) {
      coachingByRoot.set(root, empty.cloneNode(true));
    } else {
      coachingByRoot.set(root, fallbackNode());
    }
  }

  function restoreCoaching(root) {
    var results = resultsOf(root);
    if (!results) return;
    var node = coachingByRoot.get(root) || fallbackNode();
    results.textContent = "";
    results.appendChild(node.cloneNode(true));
  }

  function onQuery(evt) {
    var t = evt.target;
    if (!t || t.type !== "search") return;
    var root = rootOf(t);
    if (!root) return;
    cacheCoaching(root);
    if (String(t.value || "").trim()) return;
    // Capture + stop so htmx and the gallery mock never exchange an
    // empty q. Restore coaching — do not leave stale hits or invent
    // a result list from /mock/search.
    evt.stopImmediatePropagation();
    restoreCoaching(root);
  }

  document.addEventListener("input", onQuery, true);
  document.addEventListener("search", onQuery, true);
})();
