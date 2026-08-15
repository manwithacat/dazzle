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
 * Re-query the DOM on every event (morph-safe). Cache the original
 * coaching HTML on first touch so restore is the author's copy, not a
 * hard-coded string.
 */
(function () {
  "use strict";

  var COACHING_ATTR = "data-dz-search-coaching";
  var FALLBACK_COACHING =
    '<div class="search-box-empty">Type a title or keyword</div>';

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

  function cacheCoaching(root) {
    if (root.getAttribute(COACHING_ATTR)) return;
    var results = resultsOf(root);
    var empty =
      results &&
      (results.querySelector(".dz-search-box-empty") ||
        results.querySelector(".search-box-empty"));
    var html =
      empty && !isNoResults(empty) ? empty.outerHTML : FALLBACK_COACHING;
    root.setAttribute(COACHING_ATTR, html);
  }

  function restoreCoaching(root) {
    var results = resultsOf(root);
    if (!results) return;
    results.innerHTML = root.getAttribute(COACHING_ATTR) || FALLBACK_COACHING;
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
