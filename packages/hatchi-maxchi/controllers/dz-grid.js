/* HYPERPART: grid */
/*
 * dz-grid — the data-table controller. Slices: selection + sort + filter +
 * search + bulk actions.
 *
 * Delegated + state-in-DOM, the HM idiom (same shape as dz-tabs.js): one pair
 * of document-level listeners, everything scoped to the clicked control's own
 * `[data-dz-grid]` root via `closest()`, so N grids on a page stay independent.
 * There is NO framework and NO reactive scope — the primary selection state is
 * each checkbox's own `.checked`, which idiomorph preserves in place across a
 * tbody swap (the exact thing Alpine's reactive scope did NOT survive). The
 * *derived* state — the root's `data-dz-bulk-count`, the summary text, and the
 * select-all tri-state — is a projection of those checkboxes, so it is
 * recomputed on every `change`/`click` AND re-synced after any `htmx:afterSwap`
 * (a swap changes the row set, so the projection must be rebuilt from the
 * surviving boxes). Row identity across a re-sort/paginate: idiomorph preserves a
 * checkbox by DOM position UNLESS its row carries a stable `id`, which idiomorph
 * then uses as the morph key — so a live selection follows its ROW, not a
 * position. The server emits that `id` (`dz-grid-row-<rowid>`);
 * `data-dz-grid-row-id` stays the bulk-action payload anchor, and the id encodes
 * it so the two agree. (The HM gallery mock emits it today; Dazzle's row emitter
 * adopts it when the runtime converges onto this primitive.)
 *
 * Contract:
 *   - root:        `[data-dz-grid]` (also the `.dz-table` the bulk CSS gates on)
 *   - row box:     `[data-dz-grid-select]` (a checkbox; may carry
 *                  `data-dz-grid-row-id` for later bulk payloads)
 *   - select-all:  `[data-dz-grid-select-all]` (header checkbox; reflects
 *                  checked / indeterminate / unchecked)
 *   - count sink:  `data-dz-bulk-count` written on the root (the CSS reveals
 *                  `.dz-bulk-actions` when it isn't "0") + `[data-dz-bulk-count-target]`
 *                  mirrors the number for a "N selected" summary
 *   - clear:       `[data-dz-grid-clear]` deselects everything
 *   - body:        `[data-dz-grid-body]` (the tbody htmx swaps; `data-dz-grid-src`
 *                  holds its immutable base endpoint, `hx-get` its current query)
 *   - sort:        `[data-dz-grid-sort="<key>"]` (a header button) cycles the
 *                  clicked column through `data-dz-grid-sort-cycle`
 *                  (default "asc desc none"); state lives on the th's `aria-sort`
 *   - filter:      `[data-dz-grid-filter="<key>"]` (a form control) narrows on
 *                  change; empty value = no filter. Composes with sort — the
 *                  request query is rebuilt from ALL current DOM state.
 *   - search:      `[data-dz-grid-search]` (an input) adds `q=` on input,
 *                  debounced (`data-dz-grid-debounce`, default 250ms). Composes
 *                  with sort + filter into the same query. NB `q`, `sort`, `dir`,
 *                  `page`, `page_size` (query keys) and `action`, `selected_ids`,
 *                  `all_matching_selected`, `excluded_ids` (bulk-payload keys) are
 *                  reserved — don't use them as a `data-dz-grid-filter` value.
 *   - bulk:        `[data-dz-grid-bulk-action="<action>"]` (a button, usually
 *                  with `hx-post` + `hx-confirm`) — on `htmx:configRequest` the
 *                  controller injects the selection payload (action, selected
 *                  ids, all-matching/excluded shape, current-query echo) so the
 *                  server re-scopes + re-validates, never trusting client ids.
 */
(function () {
  "use strict";

  function gridOf(el) {
    return el.closest ? el.closest("[data-dz-grid]") : null;
  }

  function rowBoxes(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll("[data-dz-grid-select]"),
    );
  }

  function sync(root) {
    var boxes = rowBoxes(root);
    var checked = 0;
    for (var i = 0; i < boxes.length; i++) {
      var on = boxes[i].checked;
      if (on) checked++;
      var tr = boxes[i].closest("tr");
      if (tr) tr.classList.toggle("is-selected", on);
    }
    // The count is the single source of truth the CSS reads (#978 pattern):
    // `.dz-table:not([data-dz-bulk-count="0"]) .dz-bulk-actions { display:flex }`.
    root.setAttribute("data-dz-bulk-count", String(checked));
    var target = root.querySelector("[data-dz-bulk-count-target]");
    if (target) target.textContent = String(checked);
    var all = root.querySelector("[data-dz-grid-select-all]");
    if (all) {
      all.checked = checked > 0 && checked === boxes.length;
      all.indeterminate = checked > 0 && checked < boxes.length;
    }
  }

  // ── Sort: state-in-DOM, server owns the order ──────────────────────────
  // The sorted column + direction live on each header th's `aria-sort`
  // (none|ascending|descending). A click cycles the CLICKED column through
  // `data-dz-grid-sort-cycle` (default "asc desc none"), clears every OTHER
  // sortable header (one ORDER BY at a time), rebuilds the tbody's request query
  // from that state, and fires `dz-grid:refresh` so the server returns the
  // re-ordered rows (real htmx via the tbody's `hx-trigger`; the gallery mock via
  // a listener). The controller NEVER re-renders rows — it only asks.
  var DIR_OF = { ascending: "asc", descending: "desc", none: "none" };
  var ARIA_OF = { asc: "ascending", desc: "descending", none: "none" };

  function sortButtons(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll("[data-dz-grid-sort]"),
    );
  }

  // The active sort read back off the DOM (the one header whose aria-sort is
  // ascending/descending), or null. Single source of truth: the headers.
  function readSort(root) {
    var btns = sortButtons(root);
    for (var i = 0; i < btns.length; i++) {
      var th = btns[i].closest("th");
      var dir = DIR_OF[(th && th.getAttribute("aria-sort")) || "none"];
      if (dir && dir !== "none") {
        return { key: btns[i].getAttribute("data-dz-grid-sort"), dir: dir };
      }
    }
    return null;
  }

  // Rebuild the tbody's request query from ALL current DOM state — the search
  // box, the active sort, AND every filter select — so search / sort / filter
  // COMPOSE, then ask the server (via `dz-grid:refresh`) for the matching,
  // ordered rows.
  function refresh(root) {
    var body = root.querySelector("[data-dz-grid-body]");
    if (!body) return;
    var base = (
      body.getAttribute("data-dz-grid-src") ||
      body.getAttribute("hx-get") ||
      ""
    ).split("?")[0];
    var q = [];
    var search = root.querySelector("[data-dz-grid-search]");
    if (search && search.value) {
      q.push("q=" + encodeURIComponent(search.value));
    }
    var s = readSort(root);
    if (s) {
      q.push("sort=" + encodeURIComponent(s.key));
      q.push("dir=" + s.dir);
    }
    var filters = root.querySelectorAll("[data-dz-grid-filter]");
    for (var i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-dz-grid-filter");
      var v = filters[i].value;
      if (k && v) q.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    }
    // Search / sort / filter reset pagination to page 1 (spec) — a no-op until
    // the pagination slice adds page state; the reset lands there.
    body.setAttribute("hx-get", base + (q.length ? "?" + q.join("&") : ""));
    body.dispatchEvent(new CustomEvent("dz-grid:refresh", { bubbles: true }));
  }

  function applySort(root, btn) {
    var th = btn.closest("th");
    var cur = (th && th.getAttribute("aria-sort")) || "none";
    var cycle = (btn.getAttribute("data-dz-grid-sort-cycle") || "asc desc none")
      .split(/\s+/)
      .filter(Boolean);
    if (!cycle.length) cycle = ["asc", "desc", "none"];
    // A fresh column is at "none" → its next state is cycle[0] (asc by default);
    // the active column advances through the cycle.
    var idx = cycle.indexOf(DIR_OF[cur] || "none");
    var next = cycle[(idx + 1) % cycle.length];
    var btns = sortButtons(root);
    for (var i = 0; i < btns.length; i++) {
      var h = btns[i].closest("th");
      if (h) h.setAttribute("aria-sort", "none");
    }
    if (th) th.setAttribute("aria-sort", ARIA_OF[next] || "none");
    refresh(root); // reads the sort we just wrote + any active filters
  }

  // Search: debounced so a burst of keystrokes makes ONE request. The timer
  // lives on the input itself (delegated, no per-grid state map). Default 250ms,
  // overridable with `data-dz-grid-debounce`.
  document.addEventListener("input", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-dz-grid-search]")) return;
    var root = gridOf(t);
    if (!root) return;
    var ms = parseInt(t.getAttribute("data-dz-grid-debounce"), 10);
    if (isNaN(ms)) ms = 250;
    if (t._dzSearchTimer) clearTimeout(t._dzSearchTimer);
    t._dzSearchTimer = setTimeout(function () {
      t._dzSearchTimer = null;
      refresh(root);
    }, ms);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-dz-grid-select]")) {
      var r = gridOf(t);
      if (r) sync(r);
    } else if (t.matches("[data-dz-grid-select-all]")) {
      var root = gridOf(t);
      if (!root) return;
      var boxes = rowBoxes(root);
      for (var i = 0; i < boxes.length; i++) boxes[i].checked = t.checked;
      sync(root);
    } else if (t.matches("[data-dz-grid-filter]")) {
      // A filter select changed → rebuild the query (composing with any active
      // sort) and reload the rows from the server.
      var fr = gridOf(t);
      if (fr) refresh(fr);
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    var sortBtn = t.closest("[data-dz-grid-sort]");
    if (sortBtn) {
      var sroot = gridOf(sortBtn);
      if (sroot) {
        evt.preventDefault();
        applySort(sroot, sortBtn);
      }
      return;
    }
    var clear = t.closest("[data-dz-grid-clear]");
    if (!clear) return;
    var root = gridOf(clear);
    if (!root) return;
    var boxes = rowBoxes(root);
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
    sync(root);
  });

  // ── Bulk actions: add the selection to the request ─────────────────────
  // A `[data-dz-grid-bulk-action]` button posts (after its confirm). On
  // `htmx:configRequest` we inject the selection payload so the SERVER re-scopes
  // the action to exactly what the user was viewing — never trusting the client
  // ids alone (§15). Payload: the action, the selected row ids, the
  // all-matching / excluded shape (all_matching lands with the paging slice),
  // and an echo of the current query (search / sort / filters).
  document.addEventListener("htmx:configRequest", function (evt) {
    var d = evt.detail || {};
    var el = d.elt || evt.target;
    var btn = el && el.closest && el.closest("[data-dz-grid-bulk-action]");
    if (!btn) return;
    var root = gridOf(btn);
    if (!root) return;
    var p = d.parameters || (d.parameters = {});
    // Echo the current query FIRST — the filter/sort/search the rows came from —
    // so the server applies the action to exactly those rows, re-validating
    // server-side. The bulk-payload keys are written LAST so they always win: a
    // filter named `action` (etc.) can't clobber the operation name.
    var body = root.querySelector("[data-dz-grid-body]");
    var qs = ((body && body.getAttribute("hx-get")) || "").split("?")[1] || "";
    qs.split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("=");
      var k = decodeURIComponent(i < 0 ? kv : kv.slice(0, i));
      p[k] = i < 0 ? "" : decodeURIComponent(kv.slice(i + 1));
    });
    var boxes = rowBoxes(root);
    var ids = [];
    for (var i = 0; i < boxes.length; i++) {
      if (boxes[i].checked) {
        var id = boxes[i].getAttribute("data-dz-grid-row-id");
        if (id) ids.push(id);
      }
    }
    p.action = btn.getAttribute("data-dz-grid-bulk-action");
    p.selected_ids = ids;
    p.all_matching_selected = "false";
    p.excluded_ids = [];
  });

  // A tbody swap changes the row set: idiomorph preserves each checkbox's
  // `.checked` in place, but the derived count / bar / select-all must be
  // rebuilt from the surviving boxes — else the root could say "2 selected"
  // after those 2 rows were swapped out. Re-sync every grid on the page (cheap;
  // no-op where nothing changed). Harmless if htmx never fires this event.
  document.addEventListener("htmx:afterSwap", function () {
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) sync(grids[i]);
  });
})();
