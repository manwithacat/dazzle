/* HYPERPART: grid */
/*
 * dz-grid — the data-table controller. Slices: selection + sort + filter +
 * search + bulk actions + pagination.
 *
 * Delegated + state-in-DOM, the HM idiom (same shape as dz-tabs.js): one pair
 * of document-level listeners, everything scoped to the clicked control's own
 * `[data-dz-grid]` root via `closest()`, so N grids on a page stay independent.
 * There is NO framework and NO reactive scope — the primary selection state is
 * each checkbox's own `.checked`, which idiomorph preserves in place across a
 * tbody swap (the exact thing Alpine's reactive scope did NOT survive). The
 * *derived* state — the root's `data-dz-bulk-count`, the summary text, and the
 * select-all tri-state — is a projection of those checkboxes, so it is
 * recomputed on every `change`/`click` AND re-synced after any swap (htmx-4
 * `htmx:after:swap`; the legacy `htmx:afterSwap` is bound too)
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
 *                  with `hx-post` + `hx-confirm`) — on the config-request
 *                  event (htmx-4 `htmx:config:request` / legacy
 *                  `htmx:configRequest`) the
 *                  controller injects the selection payload (action, selected
 *                  ids, all-matching/excluded shape, current-query echo) so the
 *                  server re-scopes + re-validates, never trusting client ids.
 *   - all-matching: `[data-dz-grid-select-all-matching]` (a button, in the bulk
 *                  bar) escalates the selection to the WHOLE matched query —
 *                  `data-dz-grid-all-matching="true"` on the root, exclusions
 *                  (rows the user unchecks) in `data-dz-grid-excluded` (a JSON
 *                  array of row-ids). The matched TOTAL comes from the
 *                  server-rendered footer's `data-dz-grid-total` and is
 *                  mirrored into any `[data-dz-grid-matching-total]`. A filter /
 *                  search change that CHANGES the matched set drops the mode
 *                  (compared against the `data-dz-grid-scope` snapshot taken at
 *                  entry, so a net-unchanged keystroke keeps it); a sort or
 *                  page change keeps it (same set, reordered/windowed).
 *   - page:        current page is `data-dz-grid-page` on the root (default 1).
 *                  `[data-dz-grid-goto="<n>"]` / `[data-dz-grid-page-prev]` /
 *                  `[data-dz-grid-page-next]` (server-rendered footer buttons)
 *                  set it + refresh (`page=` in the query); the server disables
 *                  prev/next at the edges. Sort / filter / search reset it to 1.
 *   - announcer:   `[data-dz-grid-announce]` (a visually-hidden aria-live
 *                  region, static in the markup) — after every swap the
 *                  controller mirrors the footer's result-window summary into
 *                  it ("Showing 1-4 of 6"), because the footer itself is
 *                  repainted wholesale, which screen readers can't track.
 *                  Page-control focus is restored onto the repainted
 *                  equivalent (or the current-page button when that control
 *                  is now disabled) so keyboard focus never falls to <body>.
 *   - page size:   `[data-dz-grid-page-size]` (a select) re-windows the same
 *                  matched set — `page_size=` joins the query, the change
 *                  resets to page 1, and an all-matching selection SURVIVES
 *                  (windowing, not a scope change). NB the initial `load`
 *                  fires the tbody's static `hx-get` (refresh() isn't
 *                  involved), so a server pre-selecting a NON-default size
 *                  must also bake `page_size=` into that initial URL — else
 *                  the first interaction visibly re-windows.
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

  // ── All-matching selection: state on the root, not the rows ────────────
  // `data-dz-grid-all-matching="true"` marks the WHOLE matched query selected
  // (every page); `data-dz-grid-excluded` (a JSON array of row-ids) records
  // the exceptions the user unchecked. Both live on the root because the
  // selection spans pages the DOM doesn't hold. The matched TOTAL is read from
  // the server-rendered footer's `data-dz-grid-total` — the server is
  // authoritative about how many rows match.
  function allMatching(root) {
    return root.getAttribute("data-dz-grid-all-matching") === "true";
  }

  function readExcluded(root) {
    try {
      var ids = JSON.parse(root.getAttribute("data-dz-grid-excluded") || "[]");
      return Array.isArray(ids) ? ids : [];
    } catch (e) {
      return [];
    }
  }

  function writeExcluded(root, ids) {
    if (ids.length) {
      root.setAttribute("data-dz-grid-excluded", JSON.stringify(ids));
    } else {
      root.removeAttribute("data-dz-grid-excluded");
    }
  }

  function clearAllMatching(root) {
    root.removeAttribute("data-dz-grid-all-matching");
    root.removeAttribute("data-dz-grid-excluded");
    root.removeAttribute("data-dz-grid-scope");
  }

  // The matched-set-DEFINING part of the query: search + filters. Sort and
  // page reorder/window the SAME set, so they're not part of the scope.
  function scopeKey(root) {
    var parts = [];
    var search = root.querySelector("[data-dz-grid-search]");
    if (search && search.value) parts.push("q=" + search.value);
    var filters = root.querySelectorAll("[data-dz-grid-filter]");
    for (var i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-dz-grid-filter");
      if (k && filters[i].value) parts.push(k + "=" + filters[i].value);
    }
    return parts.join("&");
  }

  // Drop all-matching ONLY if the matched set actually changed since the mode
  // was entered (its scope snapshot lives on the root). A search keystroke
  // that's deleted again — net-unchanged query — must NOT silently destroy a
  // cross-page selection right before a destructive bulk action.
  function dropModeIfScopeChanged(root) {
    if (!allMatching(root)) return;
    if (scopeKey(root) !== (root.getAttribute("data-dz-grid-scope") || "")) {
      clearAllMatching(root);
    }
  }

  function matchedTotal(root) {
    var nav = root.querySelector("[data-dz-grid-pagination]");
    if (!nav) return null;
    var t = parseInt(nav.getAttribute("data-dz-grid-total"), 10);
    return isNaN(t) ? null : t;
  }

  // Mirror the server-rendered result-window summary ("1-4 of 6") into the
  // visually-hidden `[data-dz-grid-announce]` live region — the footer itself
  // is repainted wholesale, which screen readers can't track. Only on CHANGE:
  // repeating an identical announcement is SR noise.
  function announce(root) {
    var out = root.querySelector("[data-dz-grid-announce]");
    if (!out) return;
    var summary = root.querySelector(
      "[data-dz-grid-pagination] .dz-pagination-summary",
    );
    if (!summary) return;
    var msg = "Showing " + summary.textContent.trim();
    if (out.textContent !== msg) out.textContent = msg;
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
    // In all-matching mode the selection is the whole matched query minus the
    // exclusions, so the count comes from the server's total — NOT the visible
    // boxes. If the footer (and its total) hasn't rendered yet, degrade to the
    // visible count rather than invent one.
    var am = allMatching(root);
    var excluded = am ? readExcluded(root) : [];
    var total = matchedTotal(root);
    var count = checked;
    if (am && total !== null) count = Math.max(0, total - excluded.length);
    // The count is the single source of truth the CSS reads (#978 pattern):
    // `.dz-table:not([data-dz-bulk-count="0"]) .dz-bulk-actions { display:flex }`.
    root.setAttribute("data-dz-bulk-count", String(count));
    var target = root.querySelector("[data-dz-bulk-count-target]");
    if (target) target.textContent = String(count);
    // Mirror the matched total into the escalation affordance's label
    // ("Select all N matching") whenever the footer knows it.
    var mirror = root.querySelector("[data-dz-grid-matching-total]");
    if (mirror && total !== null) mirror.textContent = String(total);
    var all = root.querySelector("[data-dz-grid-select-all]");
    if (all) {
      if (am) {
        // The header box reflects the QUERY-wide selection: fully checked
        // until an exclusion exists, then indeterminate.
        all.checked = excluded.length === 0;
        all.indeterminate = excluded.length > 0;
      } else {
        all.checked = checked > 0 && checked === boxes.length;
        all.indeterminate = checked > 0 && checked < boxes.length;
      }
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
    // Page size: a windowing control ([data-dz-grid-page-size] select). Sent
    // whenever the control exists — the server's own default applies when the
    // grid doesn't offer the choice.
    var size = root.querySelector("[data-dz-grid-page-size]");
    if (size && size.value) {
      q.push("page_size=" + encodeURIComponent(size.value));
    }
    // Current page lives on the root; page 1 is the default (omitted for a clean
    // query). Search / sort / filter reset it to 1 via resetPage() BEFORE calling
    // refresh; a page-control click sets it, then refreshes.
    var page = root.getAttribute("data-dz-grid-page");
    if (page && page !== "1") q.push("page=" + encodeURIComponent(page));
    body.setAttribute("hx-get", base + (q.length ? "?" + q.join("&") : ""));
    body.dispatchEvent(new CustomEvent("dz-grid:refresh", { bubbles: true }));
  }

  function resetPage(root) {
    root.setAttribute("data-dz-grid-page", "1");
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
    resetPage(root); // a new sort starts at page 1
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
      // A search that CHANGES the matched set drops all-matching — a
      // selection over the old query must not silently apply to the new one.
      // (Scope-compared, so a net-unchanged keystroke keeps the mode.)
      dropModeIfScopeChanged(root);
      resetPage(root); // a new search starts at page 1
      refresh(root);
    }, ms);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-dz-grid-select]")) {
      var r = gridOf(t);
      if (!r) return;
      if (allMatching(r)) {
        // In all-matching mode a row toggle edits the EXCLUSION list on the
        // root — the row's own checkbox can't carry the state, because the
        // selection spans pages whose boxes aren't in the DOM.
        var id = t.getAttribute("data-dz-grid-row-id");
        if (id) {
          var ex = readExcluded(r);
          var at = ex.indexOf(id);
          if (!t.checked && at < 0) ex.push(id);
          if (t.checked && at >= 0) ex.splice(at, 1);
          writeExcluded(r, ex);
        }
      }
      sync(r);
    } else if (t.matches("[data-dz-grid-select-all]")) {
      var root = gridOf(t);
      if (!root) return;
      if (allMatching(root)) {
        // Checking restores the FULL all-matching selection (exclusions
        // gone); unchecking exits the mode — everything deselects.
        if (t.checked) writeExcluded(root, []);
        else clearAllMatching(root);
      }
      var boxes = rowBoxes(root);
      for (var i = 0; i < boxes.length; i++) boxes[i].checked = t.checked;
      sync(root);
    } else if (t.matches("[data-dz-grid-filter]")) {
      // A filter select changed → rebuild the query (composing with any active
      // sort) and reload the rows from the server, back at page 1. The matched
      // set changed, so an all-matching selection drops (same rule as search).
      var fr = gridOf(t);
      if (fr) {
        dropModeIfScopeChanged(fr);
        resetPage(fr);
        refresh(fr);
      }
    } else if (t.matches("[data-dz-grid-page-size]")) {
      // Page size re-WINDOWS the same matched set (like a page click, NOT a
      // scope change): back to page 1, but an all-matching selection survives.
      var zr = gridOf(t);
      if (zr) {
        resetPage(zr);
        refresh(zr);
      }
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    // Pagination: a page-number (`data-dz-grid-goto`) or prev/next control. The
    // server disables prev/next at the edges, so a disabled button won't fire;
    // the max(1, …) is a floor for safety. Page is state on the root.
    var goBtn = t.closest(
      "[data-dz-grid-goto], [data-dz-grid-page-prev], [data-dz-grid-page-next]",
    );
    if (goBtn) {
      var proot = gridOf(goBtn);
      if (proot) {
        evt.preventDefault();
        var cur = parseInt(proot.getAttribute("data-dz-grid-page"), 10) || 1;
        var to;
        if (goBtn.hasAttribute("data-dz-grid-page-prev"))
          to = Math.max(1, cur - 1);
        else if (goBtn.hasAttribute("data-dz-grid-page-next")) to = cur + 1;
        else to = parseInt(goBtn.getAttribute("data-dz-grid-goto"), 10) || 1;
        proot.setAttribute("data-dz-grid-page", String(to));
        // The swap repaints the footer wholesale, destroying the focused
        // control — note the INTENT (not the node) so afterSwap can restore
        // focus onto the repainted equivalent. Ephemeral UI state, so a JS
        // property (not an attribute) is fine: it never has to survive a morph.
        proot._dzRefocus = goBtn.hasAttribute("data-dz-grid-page-prev")
          ? "prev"
          : goBtn.hasAttribute("data-dz-grid-page-next")
            ? "next"
            : "goto:" + to;
        refresh(proot);
      }
      return;
    }
    var sortBtn = t.closest("[data-dz-grid-sort]");
    if (sortBtn) {
      var sroot = gridOf(sortBtn);
      if (sroot) {
        evt.preventDefault();
        applySort(sroot, sortBtn);
      }
      return;
    }
    var amBtn = t.closest("[data-dz-grid-select-all-matching]");
    if (amBtn) {
      var aroot = gridOf(amBtn);
      if (aroot) {
        // Escalate to the whole matched query: mark the root, snapshot the
        // scope the user confirmed (search + filters — so a later change can
        // be told apart from a net no-op), drop any stale exclusions, and
        // check the visible boxes so the DOM agrees.
        aroot.setAttribute("data-dz-grid-all-matching", "true");
        aroot.setAttribute("data-dz-grid-scope", scopeKey(aroot));
        writeExcluded(aroot, []);
        var aboxes = rowBoxes(aroot);
        for (var j = 0; j < aboxes.length; j++) aboxes[j].checked = true;
        sync(aroot);
      }
      return;
    }
    var clear = t.closest("[data-dz-grid-clear]");
    if (!clear) return;
    var root = gridOf(clear);
    if (!root) return;
    clearAllMatching(root); // Clear means everything — mode included
    var boxes = rowBoxes(root);
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
    sync(root);
  });

  // ── Bulk actions: add the selection to the request ─────────────────────
  // A `[data-dz-grid-bulk-action]` button posts (after its confirm). On the
  // config-request event we inject the selection payload so the SERVER
  // re-scopes the action to exactly what the user was viewing — never trusting
  // the client ids alone (§15). Payload: the action, the selected row ids, the
  // all-matching / excluded shape, and an echo of the current query
  // (search / sort / filters).
  //
  // htmx-4 vs htmx-2 COMPAT (the v0.93.66 confirm lesson): htmx-4 renamed the
  // event `htmx:configRequest` → `htmx:config:request` AND moved the config
  // under `detail.ctx` with a FormData `ctx.request.body` (there is no
  // `detail.parameters`). We bind BOTH names and deliver via whichever shape
  // the event carries. Real htmx fires exactly ONE of the two names per
  // request — the handler is not double-fire safe (the mode-clear below runs
  // once) and doesn't need to be.
  function onConfigRequest(evt) {
    var d = evt.detail || {};
    var ctx = d.ctx || d; // htmx-4 nests the config under detail.ctx
    var el = d.elt || ctx.sourceElement || evt.target;
    var btn = el && el.closest && el.closest("[data-dz-grid-bulk-action]");
    if (!btn) return;
    var root = gridOf(btn);
    if (!root) return;
    // Assemble the payload: the query echo FIRST — the filter/sort/search the
    // rows came from — then the bulk keys LAST so they always win (a filter
    // named `action` etc. can't clobber the operation name).
    var payload = {};
    var body = root.querySelector("[data-dz-grid-body]");
    var qs = ((body && body.getAttribute("hx-get")) || "").split("?")[1] || "";
    qs.split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("=");
      var k = decodeURIComponent(i < 0 ? kv : kv.slice(0, i));
      payload[k] = i < 0 ? "" : decodeURIComponent(kv.slice(i + 1));
    });
    var boxes = rowBoxes(root);
    var ids = [];
    for (var i = 0; i < boxes.length; i++) {
      if (boxes[i].checked) {
        var id = boxes[i].getAttribute("data-dz-grid-row-id");
        if (id) ids.push(id);
      }
    }
    payload.action = btn.getAttribute("data-dz-grid-bulk-action");
    payload.selected_ids = ids;
    payload.all_matching_selected = allMatching(root) ? "true" : "false";
    payload.excluded_ids = readExcluded(root);
    // The action consumes the selection (spec: "clears unless configured
    // otherwise"): exit all-matching NOW, at payload-capture time, so the
    // refreshed rows that follow the action arrive unselected instead of
    // being re-checked by the after-swap hydration. Trade-off (deliberate):
    // if the server rejects the action, the all-matching selection is gone.
    if (allMatching(root)) clearAllMatching(root);
    if (d.parameters) {
      // htmx ≤2: a plain parameters object.
      Object.keys(payload).forEach(function (k) {
        d.parameters[k] = payload[k];
      });
    } else if (ctx.request) {
      // htmx-4: append to the request's form body. Delete-then-append keeps
      // the keys-win semantics; arrays repeat the key (form encoding).
      if (!ctx.request.body || typeof ctx.request.body.append !== "function") {
        ctx.request.body = new FormData();
      }
      var fd = ctx.request.body;
      Object.keys(payload).forEach(function (k) {
        fd.delete(k);
        var v = payload[k];
        if (Array.isArray(v)) {
          for (var j = 0; j < v.length; j++) fd.append(k, v[j]);
        } else {
          fd.append(k, v);
        }
      });
    }
  }
  document.addEventListener("htmx:config:request", onConfigRequest); // htmx 4
  document.addEventListener("htmx:configRequest", onConfigRequest); // htmx ≤2

  // A tbody swap changes the row set: idiomorph preserves each checkbox's
  // `.checked` in place, but the derived count / bar / select-all must be
  // rebuilt from the surviving boxes — else the root could say "2 selected"
  // after those 2 rows were swapped out. Re-sync every grid on the page (cheap;
  // no-op where nothing changed). Harmless if htmx never fires this event.
  // Bound under BOTH names: htmx-4 fires `htmx:after:swap`, htmx ≤2 fired
  // `htmx:afterSwap`.
  function onAfterSwap() {
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      // In all-matching mode freshly-rendered rows arrive SELECTED (minus the
      // exclusions): the mode spans pages, the DOM doesn't, so each swap
      // re-projects the root's state onto the new boxes.
      if (allMatching(grids[i])) {
        var ex = readExcluded(grids[i]);
        var boxes = rowBoxes(grids[i]);
        for (var j = 0; j < boxes.length; j++) {
          boxes[j].checked =
            ex.indexOf(boxes[j].getAttribute("data-dz-grid-row-id")) < 0;
        }
      }
      sync(grids[i]);
      // Re-sync the root's page from the server-rendered footer's current-page
      // marker: the server may have CLAMPED the page (e.g. a bulk delete that
      // removed the last page), so the client's requested page can be stale.
      // The footer is authoritative about which page actually rendered.
      var nav = grids[i].querySelector("[data-dz-grid-pagination]");
      var curBtn =
        nav && nav.querySelector("[data-dz-grid-goto][aria-current='page']");
      if (curBtn) {
        var pnum = parseInt(curBtn.getAttribute("data-dz-grid-goto"), 10);
        if (pnum) grids[i].setAttribute("data-dz-grid-page", String(pnum));
      }
      // Announce the (possibly new) result window to screen readers. Safe on
      // after-swap even under the OOB footer contract: while the nav is still
      // stale the text hasn't changed (no announcement); the OOB nav's own
      // after-swap then announces the real change.
      announce(grids[i]);
    }
  }
  document.addEventListener("htmx:after:swap", onAfterSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onAfterSwap); // htmx ≤2

  // Focus restoration runs on after-SETTLE, not after-swap: with the OOB
  // footer contract the tbody's after-swap fires while the nav is still STALE
  // — focusing one of its buttons would be undone a beat later when the OOB
  // swap evicts it (focus → <body>, the exact failure this exists to prevent).
  // after-settle fires once, after ALL swaps (OOB included) settle, so the nav
  // queried here is final. The gallery mock fires it after its footer repaint
  // for the same reason. Restore the same-intent control if still usable, else
  // the current-page button (e.g. prev clicked onto page 1, where prev is
  // disabled). Consuming the marker twice is a no-op (it's nulled on first
  // read), so the dual binding is safe even if both names ever fired.
  function onAfterSettle() {
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      var want = grids[i]._dzRefocus;
      if (!want) continue;
      grids[i]._dzRefocus = null;
      var nav = grids[i].querySelector("[data-dz-grid-pagination]");
      if (!nav) continue;
      var el = null;
      if (want === "prev") {
        el = nav.querySelector("[data-dz-grid-page-prev]:not([disabled])");
      } else if (want === "next") {
        el = nav.querySelector("[data-dz-grid-page-next]:not([disabled])");
      } else {
        el = nav.querySelector(
          "[data-dz-grid-goto='" + want.slice(5) + "']:not([disabled])",
        );
      }
      if (!el) {
        el = nav.querySelector("[data-dz-grid-goto][aria-current='page']");
      }
      if (el) el.focus();
    }
  }
  document.addEventListener("htmx:after:settle", onAfterSettle); // htmx 4
  document.addEventListener("htmx:afterSettle", onAfterSettle); // htmx ≤2
})();
