window.__HM_ICONS__ = {'layout-dashboard':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1" /> <rect width="7" height="5" x="14" y="3" rx="1" /> <rect width="7" height="9" x="14" y="12" rx="1" /> <rect width="7" height="5" x="3" y="16" rx="1" /></svg>','settings':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" /> <circle cx="12" cy="12" r="3" /></svg>','receipt':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17V7" /> <path d="M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8" /> <path d="M4 3a1 1 0 0 1 1-1 1.3 1.3 0 0 1 .7.2l.933.6a1.3 1.3 0 0 0 1.4 0l.934-.6a1.3 1.3 0 0 1 1.4 0l.933.6a1.3 1.3 0 0 0 1.4 0l.933-.6a1.3 1.3 0 0 1 1.4 0l.934.6a1.3 1.3 0 0 0 1.4 0l.933-.6A1.3 1.3 0 0 1 19 2a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1 1.3 1.3 0 0 1-.7-.2l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.934.6a1.3 1.3 0 0 1-1.4 0l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-1.4 0l-.934-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-.7.2 1 1 0 0 1-1-1z" /></svg>','users':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /> <path d="M16 3.128a4 4 0 0 1 0 7.744" /> <path d="M22 21v-2a4 4 0 0 0-3-3.87" /> <circle cx="9" cy="7" r="4" /></svg>','triangle-alert':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" /> <path d="M12 9v4" /> <path d="M12 17h.01" /></svg>',};
/* Minimal htmx4 mock — enough for the static gallery demos.
   Supports: hx-get (canned responses), hx-confirm -> htmx:confirm event,
   hx-boost no-op. NOT a real htmx; the point is that the SAME markup that
   runs against a Dazzle server also demos statically here. */
(function () {
  "use strict";
  var RESPONSES = {
    "/mock/command": '<div class="command__group">Workspaces</div>' +
      '<a class="command__item" href="#" role="option">{i:layout-dashboard}<span>Operations Dashboard</span></a>' +
      '<a class="command__item" href="#" role="option">{i:settings}<span>Platform Admin</span></a>' +
      '<div class="command__group">Records</div>' +
      '<a class="command__item" href="#" role="option">{i:receipt}<span>Invoices</span></a>' +
      '<a class="command__item" href="#" role="option">{i:users}<span>Customers</span></a>' +
      '<a class="command__item" href="#" role="option">{i:triangle-alert}<span>Alerts</span></a>',
    "/mock/master-detail/inv-001": '<div class="card card-body"><div class="card-label">INV-001 · Acme</div><div class="card-value">£1,250.00</div><div class="card-delta">Paid · 2 days ago</div></div>',
    "/mock/master-detail/inv-002": '<div class="card card-body"><div class="card-label">INV-002 · Globex</div><div class="card-value">£3,400.00</div><div class="card-delta">Pending · due Friday</div></div>',
    "/mock/master-detail/inv-003": '<div class="card card-body"><div class="card-label">INV-003 · Initech</div><div class="card-value">£820.00</div><div class="card-delta">Overdue · 6 days</div></div>',
    "/mock/pagination/2": '<div class="hm-pag-row">INV-004 · Umbrella</div><div class="hm-pag-row">INV-005 · Stark</div><div class="hm-pag-row">INV-006 · Wonka</div>',
    "/mock/pagination/3": '<div class="hm-pag-row">INV-007 · Tyrell</div><div class="hm-pag-row">INV-008 · Cyberdyne</div><div class="hm-pag-row">INV-009 · Soylent</div>',
    "/mock/pagination/9": '<div class="hm-pag-row">INV-025 · Hooli</div><div class="hm-pag-row">INV-026 · Pied Piper</div><div class="hm-pag-row">INV-027 · Aviato</div>',
    "/mock/typeahead": '<div class="search-result-row" hx-get="/mock/typeahead/select" hx-target="#hm-ss-results" hx-swap="innerHTML"><div class="search-result-name">Aurora Energy Ltd</div><div class="search-result-secondary">Company no. 09182736</div></div><div class="search-result-row" hx-get="/mock/typeahead/select" hx-target="#hm-ss-results" hx-swap="innerHTML"><div class="search-result-name">Aurora Foods plc</div></div>',
    "/mock/typeahead/select": '<div class="select-result-confirm">Selected: Aurora Energy Ltd</div>',
    "/mock/search": '<div class="search-box-result-count">2 results</div><ul class="search-box-result-list" role="list"><li class="search-box-result"><a href="#" class="search-box-result-link"><span class="search-box-result-title">Aurora <mark>Substation</mark></span><ul class="search-box-result-snippets"><li class="search-box-result-snippet"><span class="search-box-result-snippet-field">Region:</span><span class="search-box-result-snippet-text">North grid, <mark>substation</mark> cluster A</span></li></ul></a></li><li class="search-box-result"><a href="#" class="search-box-result-link"><span class="search-box-result-title">Beacon <mark>Substation</mark></span></a></li></ul>',
    "/mock/drawer/detail": '<h3>Aurora Substation</h3><p>Region: North · Load: 82%</p><p>Commissioned 2019; last inspection 14 June. Two open work orders.</p>',
    "/mock/shell/dashboard": '<div class="stack" data-gap="md"><h1>Dashboard</h1><div class="auto-grid" style="--grid-min: 10rem"><div class="card card-body"><div class="card-label">Outstanding</div><div class="card-value">£12,450</div></div><div class="card card-body"><div class="card-label">Paid</div><div class="card-value">£48,900</div></div></div></div>',
    "/mock/shell/invoices": '<div class="stack" data-gap="md"><h1>Invoices</h1><p class="hm-demo-muted">The routed workspace swapped — the shell, sidebar state, and scroll position persist; only the main slot changed.</p></div>',
    "/mock/tabs/activity": '<p class="hm-demo-muted">3 events today — INV-004 paid, INV-005 sent, a comment added.</p>',
    "/mock/tabs/settings": '<p class="hm-demo-muted">Notifications, access, and billing preferences live here.</p>'
  };

  // The grid tbody hydrates, filters, and re-sorts its rows over the wire — the
  // SERVER owns the order and the WHERE. Held as data (not markup) so the mock
  // can filter + ORDER BY the query params the controller puts on the request,
  // mirroring a real list endpoint. Each row renders a stable `id`
  // (`grid-row-<rowid>`, the idiomorph morph key) + `data-grid-row-id`
  // (the bulk payload anchor); the two agree. Values span DISTINCT sort orders
  // per column (first vs last name vs plan vs date all reorder differently) so
  // the demo legibly shows WHICH column you sorted. `status` is a filter-only
  // field (not a visible column). The unsorted (insertion) order below is
  // deliberately scrambled so "no sort" is visibly distinct from every column
  // sort. NB on dates: a real server sorts a typed date column (SQL is
  // type-aware); the mock sorts the ISO-8601 strings, whose LEXICAL order
  // equals chronological order — a faithful stand-in, not string luck.
  var GRID_ROWS = [
    { id: "cust_1", first: "Mia", last: "Chen", plan: "Team", signed: "2025-06-20", status: "Active" },
    { id: "cust_2", first: "Ravi", last: "Patel", plan: "Enterprise", signed: "2023-08-09", status: "Active" },
    { id: "cust_3", first: "Amir", last: "Okafor", plan: "Pro", signed: "2026-01-15", status: "Active" },
    { id: "cust_4", first: "Sofia", last: "Alvarez", plan: "Free", signed: "2026-07-01", status: "Trialing" },
    { id: "cust_5", first: "Noah", last: "Bright", plan: "Pro", signed: "2022-03-14", status: "Churned" },
    { id: "cust_6", first: "Jane", last: "Zimmerman", plan: "Free", signed: "2024-11-02", status: "Trialing" }
  ];
  // Query params handled specially, NOT as exact-match filters: sort/paging
  // control + the free-text search `q`.
  var GRID_CONTROL = { sort: 1, dir: 1, page: 1, page_size: 1, q: 1 };
  function parseQuery(url) {
    var out = {}, qs = (url.split("?")[1] || "");
    qs.split("&").forEach(function (p) {
      if (!p) return;
      var kv = p.split("=");
      out[kv[0]] = decodeURIComponent(kv[1] || "");
    });
    return out;
  }
  // Escape interpolated field values — the canned data is safe, but this mock
  // sits next to the documented server contract, so it must model the correct
  // idiom (never build row HTML from unescaped data).
  function htmlEnc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  var GRID_PAGE_SIZE = 4; // the server's default page size for this demo

  // The full result set for a query — search + filters + sort, WITHOUT paging.
  // The row slice and the pagination total both derive from this, so they can
  // never disagree (the bug class #847-#851 chased for charts).
  function matchedRows(q) {
    var rows = GRID_ROWS.slice();
    // Free-text search: case-insensitive substring across the visible text
    // fields (the server's ILIKE/full-text). Composes with the exact filters.
    if (q.q) {
      var needle = q.q.toLowerCase();
      rows = rows.filter(function (r) {
        return (r.first + " " + r.last + " " + r.plan).toLowerCase().indexOf(needle) >= 0;
      });
    }
    // Filters: every non-control param narrows by an exact field match (the
    // server's WHERE). An empty value ("Any …") is never sent, so never narrows.
    Object.keys(q).forEach(function (k) {
      if (GRID_CONTROL[k] || q[k] === "") return;
      rows = rows.filter(function (r) { return String(r[k]) === q[k]; });
    });
    if (q.sort) {
      rows.sort(function (a, b) {
        var x = a[q.sort], y = b[q.sort];
        var c = x < y ? -1 : (x > y ? 1 : 0);
        return q.dir === "desc" ? -c : c;
      });
    }
    return rows;
  }
  function gridPaging(q, total) {
    var size = parseInt(q.page_size, 10) || GRID_PAGE_SIZE;
    var pages = Math.max(1, Math.ceil(total / size));
    var page = Math.min(Math.max(1, parseInt(q.page, 10) || 1), pages);
    return { size: size, page: page, pages: pages };
  }
  function renderGridRows(url) {
    var q = parseQuery(url);
    var rows = matchedRows(q);
    var pg = gridPaging(q, rows.length);
    var start = (pg.page - 1) * pg.size;
    // Zero rows → empty tbody, so the `:has(tbody tr td)` empty-state shows.
    // Editable cells emit the inline-edit seam: ONE display span per cell
    // carrying kind/value/label (+ options for selects). The grid-edit
    // extension builds the editor on dblclick and commits a single-field PUT
    // to the root's data-grid-edit-url; cells stay server-rendered.
    function editSpan(col, kind, value, label, options) {
      return '<span class="tr-cell-display" data-grid-edit="' + col + '" ' +
        'data-edit-kind="' + kind + '" data-edit-value="' + htmlEnc(value) + '" ' +
        'data-edit-label="' + label + '"' +
        (options ? ' data-edit-options="' + htmlEnc(JSON.stringify(options)) + '"' : "") +
        ">" + htmlEnc(value) + "</span>";
    }
    var PLAN_OPTIONS = [["Free", "Free"], ["Pro", "Pro"], ["Team", "Team"],
      ["Enterprise", "Enterprise"]];
    return rows.slice(start, start + pg.size).map(function (r) {
      var id = htmlEnc(r.id), name = htmlEnc(r.first + " " + r.last);
      // data-col on every data cell = the column-visibility target;
      // data-row-id on the tr = the extensions' row anchor (Dazzle parity).
      return '<tr class="tr-row" id="grid-row-' + id + '" data-row-id="' + id + '">' +
        '<td class="tr-checkbox-cell"><input type="checkbox" class="tr-checkbox" ' +
        'data-grid-select data-grid-row-id="' + id + '" aria-label="Select ' + name + '"></td>' +
        '<td class="tr-cell" data-col="first">' +
        editSpan("first", "text", r.first, "First name") + '</td>' +
        '<td class="tr-cell" data-col="last">' +
        editSpan("last", "text", r.last, "Last name") + '</td>' +
        '<td class="tr-cell" data-col="plan">' +
        editSpan("plan", "select", r.plan, "Plan", PLAN_OPTIONS) + '</td>' +
        '<td class="tr-cell" data-col="signed">' +
        editSpan("signed", "date", r.signed, "Signed up") + '</td></tr>';
    }).join("");
  }
  // The server renders the pagination footer too (state-in-DOM: the page
  // controls carry their target; the current page + total live in the markup).
  // The client only intercepts the clicks and re-requests.
  function renderGridFooter(url) {
    var q = parseQuery(url);
    var total = matchedRows(q).length;
    var pg = gridPaging(q, total);
    var start = total ? (pg.page - 1) * pg.size + 1 : 0;
    var end = Math.min(pg.page * pg.size, total);
    var summary = total ? start + "-" + end + " of " + total : "0 of 0";
    // The summary is the Dazzle-faithful PAIR: a bulk-count mirror shown while
    // a selection exists, the row window otherwise (CSS-toggled off the root's
    // data-bulk-count — see table.css .bulk-summary-*).
    var html = '<span class="pagination-summary">' +
      '<span class="bulk-summary-selected">' +
      '<span data-bulk-count-target>0</span> of ' + total + ' selected</span>' +
      '<span class="bulk-summary-rows">' + summary + "</span></span>";
    html += '<div class="pagination-pages">';
    html += '<button type="button" class="pagination-page" data-grid-page-prev ' +
      (pg.page <= 1 ? "disabled " : "") + 'aria-label="Previous page">‹</button>';
    for (var i = 1; i <= pg.pages; i++) {
      html += '<button type="button" class="pagination-page' +
        (i === pg.page ? " is-current" : "") + '" data-grid-goto="' + i + '"' +
        (i === pg.page ? ' aria-current="page"' : "") + ">" + i + "</button>";
    }
    html += '<button type="button" class="pagination-page" data-grid-page-next ' +
      (pg.page >= pg.pages ? "disabled " : "") + 'aria-label="Next page">›</button>';
    return html + "</div>";
  }
  function updateGridFooter(root, url) {
    var nav = root && root.querySelector("[data-grid-pagination]");
    if (!nav) return;
    // The server stamps the matched TOTAL on the footer nav
    // (data-grid-total) — the all-matching affordance reads it ("Select
    // all N matching") and the controller uses it for the selection count.
    // In a real htmx app the OOB `<nav hx-swap-oob>` carries the attribute.
    nav.setAttribute("data-grid-total", String(matchedRows(parseQuery(url)).length));
    nav.innerHTML = renderGridFooter(url);
  }

  // icon placeholders resolved from a tiny inline map (built by the site gen)
  function icon(name) { return window.__HM_ICONS__ ? (window.__HM_ICONS__[name] || "") : ""; }
  function expand(h) { return h.replace(/\{i:([a-z0-9-]+)\}/g, function (_, n) {
    return '<span class="icon icon--size-sm">' + icon(n) + '</span>'; }); }

  function fire(el, name, detail) {
    var evt = new CustomEvent(name, { bubbles: true, cancelable: true, detail: detail });
    el.dispatchEvent(evt);
    return evt;
  }

  function doGet(el) {
    var url = el.getAttribute("hx-get");
    var body;
    if (url.split("?")[0] === "/mock/grid/rows") {
      // the grid rows are computed from the sort/dir query (server owns ORDER BY)
      body = renderGridRows(url);
    } else {
      body = expand(RESPONSES[url] || '<div class="command__empty">No results.</div>');
    }
    var sel = el.getAttribute("hx-target");
    var target = null;
    if (sel && sel.indexOf("next ") === 0) {
      var cls = sel.slice(5).trim();
      // htmx `next <sel>` = the first element matching sel that appears
      // AFTER el in document order (not just the immediate sibling). This
      // matches real htmx and frees the markup to wrap the input.
      var all = document.querySelectorAll(cls);
      for (var i = 0; i < all.length; i++) {
        if (el.compareDocumentPosition(all[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
          target = all[i];
          break;
        }
      }
    } else if (sel) {
      // plain selector (e.g. an id `#region-body`, as pagination + most real
      // htmx targets use) — resolve like htmx's default querySelector.
      target = document.querySelector(sel);
    } else {
      // no hx-target → the element swaps its own content (htmx default), as
      // the lazy tab panels do.
      target = el;
    }
    // htmx applies `.htmx-request` to the request-initiating element for the
    // duration of the in-flight request — the loading overlay + other CSS states
    // key off it. Mirror that protocol here (add before the swap, remove after).
    // The mock is SYNCHRONOUS, so there is no repaint between add/remove: the
    // overlay never visually renders during gallery hydration (real htmx is
    // async, so it does). The CSS rule itself is exercised by
    // test_grid_loading_overlay_is_wired_to_htmx_request, which injects the class.
    // NB event NAMES are the htmx-4 colon-namespaced family (htmx:after:swap,
    // NOT htmx-2's htmx:afterSwap) — the vendored htmx-4 fires ONLY these. A
    // mock firing the legacy names masks dead listeners fleet-wide (the
    // v0.93.66 confirm-shape lesson, second verse).
    el.classList.add("htmx-request");
    fire(el, "htmx:before:request", { elt: el });
    if (target) {
      target.innerHTML = body;
      // The server re-renders the pagination footer alongside the rows (in a
      // real htmx app: an OOB `<nav>` or a wrapping region swap; here the mock
      // updates it directly). Rows + footer come from the SAME query, so they
      // agree on total / current page.
      if (url.split("?")[0] === "/mock/grid/rows") {
        updateGridFooter(target.closest("[data-grid]"), url);
      }
      fire(target, "htmx:after:swap", { elt: target });
      // Real htmx fires after:settle once, after ALL swaps (OOB included)
      // settle — it's the only event where the OOB footer is guaranteed
      // final, so focus restoration listens there, not on after:swap.
      fire(target, "htmx:after:settle", { elt: target });
    }
    el.classList.remove("htmx-request");
    fire(el, "htmx:after:request", { elt: el });
  }

  // Bulk action POST (e.g. Delete). Mirrors the server contract §15: fire
  // htmx:config:request (the REAL htmx-4 shape: config nested under
  // detail.ctx, the body a FormData) so the grid controller injects the
  // selection payload (action + selected_ids + all_matching/excluded + a
  // query echo), then apply it and swap the refreshed rows for the grid's
  // CURRENT query. A real server re-validates permissions + re-scopes to the
  // query and never trusts the client ids; the mock just deletes the named
  // rows from its data.
  // The bulk-payload keys, as distinct from the echoed query params.
  var BULK_KEYS = { action: 1, selected_ids: 1, all_matching_selected: 1, excluded_ids: 1 };
  function applyBulkDelete(params) {
    var doomed;
    if (params.all_matching_selected === "true") {
      // All-matching: re-run the ECHOED query server-side and apply the action
      // to the whole matched set minus the exclusions — the visible ids are
      // informational only (§15: never trust client ids; re-scope the query).
      var q = {};
      Object.keys(params).forEach(function (k) {
        if (!BULK_KEYS[k]) q[k] = params[k];
      });
      var excluded = params.excluded_ids || [];
      doomed = matchedRows(q).map(function (r) { return r.id; })
        .filter(function (id) { return excluded.indexOf(id) < 0; });
    } else {
      doomed = params.selected_ids || [];
    }
    GRID_ROWS = GRID_ROWS.filter(function (r) { return doomed.indexOf(r.id) < 0; });
  }
  function doPost(el) {
    var url = el.getAttribute("hx-post") || "";
    // Real htmx-4 config:request: the config lives under detail.ctx and the
    // request body is form data the listener APPENDS to (there is no
    // detail.parameters object — that was htmx ≤2).
    var fd = new FormData();
    var ctx = { sourceElement: el, request: { method: "post", action: url, body: fd } };
    fire(el, "htmx:config:request", { ctx: ctx });
    // Decode the form body back into the mock server's params (the known
    // array keys via getAll — form encoding repeats them).
    var params = { selected_ids: fd.getAll("selected_ids"), excluded_ids: fd.getAll("excluded_ids") };
    fd.forEach(function (v, k) { if (!(k in params)) params[k] = v; });
    window.__lastBulk = params; // expose the payload for the gallery tests
    if (url.split("?")[0] === "/mock/grid/bulk") applyBulkDelete(params);
    // Two-request pattern: the POST applies the action and returns nothing to
    // swap (a real server answers JSON/204). The button's
    // data-grid-bulk-refresh makes the controller re-fetch rows + footer
    // for the current query after the request settles — the same GET path
    // every other state change uses.
    el.classList.add("htmx-request");
    fire(el, "htmx:before:request", { elt: el });
    el.classList.remove("htmx-request");
    fire(el, "htmx:after:request", { elt: el });
  }

  // Inline-edit commits (grid-edit.js) use a raw fetch — a PUT to the
  // entity's STANDARD update route with a single-field JSON body — not an
  // htmx exchange, so the mock intercepts window.fetch for /mock/grid/<id>.
  // A real server runs its full update gate (RBAC, scope, validation) here.
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (url, opts) {
    var m = typeof url === "string" && url.match(/^\/mock\/grid\/([^/?]+)$/);
    if (m && opts && String(opts.method).toUpperCase() === "PUT") {
      var patch = {};
      try { patch = JSON.parse(opts.body || "{}"); } catch (e) { patch = {}; }
      var hit = null;
      GRID_ROWS.forEach(function (r) { if (r.id === decodeURIComponent(m[1])) hit = r; });
      if (!hit) return Promise.resolve(new Response("{}", { status: 404 }));
      Object.keys(patch).forEach(function (k) {
        if (k in hit) hit[k] = String(patch[k]);
      });
      return Promise.resolve(new Response("{}", {
        status: 200, headers: { "Content-Type": "application/json" }
      }));
    }
    return realFetch ? realFetch(url, opts) : Promise.reject(new Error("no fetch"));
  };

  // grid:refresh — a custom event the grid controller fires on the tbody
  // after a sort/filter change (real htmx catches it via the tbody's hx-trigger;
  // here the mock does). The controller has already rewritten the tbody's hx-get
  // query, so doGet re-reads it and returns the re-ordered rows.
  document.addEventListener("grid:refresh", function (e) {
    var el = e.target;
    if (el && el.matches && el.matches("[hx-get]")) doGet(el);
  });

  // hx-get on focus/input — INPUTS only (e.g. the command palette's
  // `focus once`). Non-input `[hx-get]` affordances (links/buttons) fire on
  // click below, matching real htmx's default trigger for those elements.
  document.addEventListener("focus", function (e) {
    if (e.target.matches && e.target.matches("input[hx-get]")) doGet(e.target);
  }, true);
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("[hx-get]")) doGet(e.target);
  });
  // hx-get on click (non-input affordances, e.g. master-detail list links).
  // Respect hx-trigger: an element with an EXPLICIT non-click trigger
  // (load / intersect / input) must NOT re-fire on a click inside it — else
  // selecting a checkbox inside a `load`-hydrated tbody re-fetches and wipes
  // the selection. Real htmx fires these on their declared trigger only; a
  // click-triggered affordance (master-detail/pagination) has no hx-trigger,
  // so its default IS click.
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-get]");
    if (!el || el.matches("input")) return;
    var trig = el.getAttribute("hx-trigger") || "";
    if (trig && trig.indexOf("click") < 0) return;
    e.preventDefault();
    doGet(el);
  });

  // hx-confirm -> htmx:confirm (drives confirm.js).
  // Fires the REAL htmx-4 event shape: the config lives under `detail.ctx`
  // (sourceElement + confirm), and the request is issued/dropped via the two
  // functions on `detail`. (Earlier this mock fired the htmx-2 shape
  // {elt, question} — which no real htmx-4 consumer sees, so it silently
  // masked the htmx-4 detail-shape break in confirm.js.)
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-confirm]");
    if (!el) return;
    e.preventDefault();
    var issued = false;
    fire(el, "htmx:confirm", {
      ctx: { sourceElement: el, confirm: el.getAttribute("hx-confirm") },
      issueRequest: function () {
        issued = true;
        // A confirmed hx-post issues the real (mock) request — e.g. a bulk
        // action. Other confirmed affordances (the confirm Hyperpart's demo
        // hx-delete, which has no endpoint) just flash a toast.
        if (el.getAttribute("hx-post")) { doPost(el); return; }
        var note = document.createElement("div");
        note.className = "hm-toast";
        note.textContent = "Deleted (demo).";
        document.body.appendChild(note);
        setTimeout(function () { note.remove(); }, 1800);
      },
      dropRequest: function () { issued = false; }
    });
  });

  // intersect-once: a lazy panel (hx-trigger contains "intersect") loads the
  // first time it becomes visible — the tab controller reveals a hidden panel,
  // which then intersects. Mirrors real htmx's `intersect once` trigger.
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { io.unobserve(e.target); doGet(e.target); }
      });
    });
    var observeLazy = function () {
      var els = document.querySelectorAll("[hx-get][hx-trigger]");
      for (var i = 0; i < els.length; i++) {
        if ((els[i].getAttribute("hx-trigger") || "").indexOf("intersect") >= 0) io.observe(els[i]);
      }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", observeLazy);
    else observeLazy();
  }

  // hx-trigger="load": fire once when the element is ready (the grid tbody
  // hydrates its rows this way). Deferred via setTimeout(0): this mock IIFE is
  // concatenated BEFORE the controllers in the built bundle, so a synchronous
  // call here would fire the swap's htmx:after:swap before grid's delegated
  // listener is attached. A macrotask runs after every controller IIFE has
  // executed, so the initial after:swap re-sync lands (matters once rows can
  // arrive pre-selected, e.g. URL-restored selection).
  var fireLoads = function () {
    var els = document.querySelectorAll("[hx-get][hx-trigger]");
    for (var i = 0; i < els.length; i++) {
      if ((els[i].getAttribute("hx-trigger") || "").indexOf("load") >= 0) doGet(els[i]);
    }
  };
  setTimeout(fireLoads, 0);

  window.htmx = { version: "mock-4" };
})();

/* ── controllers/confirm.js ── */
/* HYPERPART: confirm */
/*
 * confirm — designed hx-confirm surface (HaTchi-MaXchi tranche 1).
 *
 * Part of the `confirm` Hyperpart — manifest in site/registry.py; the
 * designed dialog's styles are in components/alert.css (marked
 * `HYPERPART: confirm`). `python tools/hyperpart.py confirm` lists them.
 *
 * Intercepts htmx's `htmx:confirm` event and replaces window.confirm with
 * a designed <dialog class="alert-dialog"> (icon + title + message +
 * destructive-styled confirm). Every existing `hx-confirm="…"` attribute
 * in the fleet upgrades automatically — no emitter changes.
 *
 * Lifecycle-as-material (taste principle 9): the dialog is created lazily,
 * reused, and the htmx request is only issued via evt.detail.issueRequest()
 * on explicit confirm — cancel closes with no request.
 *
 * Opt-out: set `data-native-confirm` on the element to keep
 * window.confirm (e.g. for tests that stub it).
 */
(function () {
  "use strict";

  var dialog = null;

  var LOCK_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
    'stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "alert-dialog";
    dialog.innerHTML =
      '<span class="alert-dialog__icon" aria-hidden="true">' +
      LOCK_ICON +
      "</span>" +
      '<h2 class="alert-dialog__title">Are you sure?</h2>' +
      '<p class="alert-dialog__message"></p>' +
      '<div class="alert-dialog__actions">' +
      '<button type="button" class="button" data-variant="outline" data-confirm-cancel>Cancel</button>' +
      '<button type="button" class="button" data-variant="destructive" data-confirm-accept>Confirm</button>' +
      "</div>";
    document.body.appendChild(dialog);
    return dialog;
  }

  document.addEventListener("htmx:confirm", function (evt) {
    var d = evt.detail || {};
    // htmx-4 moved the confirm payload under `detail.ctx` (sourceElement +
    // confirm) and split the continuation into issueRequest()/dropRequest();
    // htmx<=2 exposed `detail.elt` + `detail.question` + issueRequest(). Read
    // both shapes so the designed dialog works on whichever htmx a consumer
    // ships (Dazzle vendors htmx-4). `ctx` falls back to `detail` itself so a
    // future flattening doesn't re-break this.
    var ctx = d.ctx || d;
    var elt = d.elt || ctx.sourceElement;
    if (
      !elt ||
      (elt.hasAttribute && elt.hasAttribute("data-native-confirm"))
    )
      return;
    var question = d.question || ctx.confirm;
    if (!question) return; // no hx-confirm on this element

    evt.preventDefault(); // suppress window.confirm; we own the flow now

    var dlg = ensureDialog();
    dlg.querySelector(".alert-dialog__message").textContent = question;

    var accept = dlg.querySelector("[data-confirm-accept]");
    var cancel = dlg.querySelector("[data-confirm-cancel]");

    function cleanup() {
      accept.removeEventListener("click", onAccept);
      cancel.removeEventListener("click", onCancel);
      dlg.removeEventListener("close", onClose);
      if (dlg.open) dlg.close();
    }
    function onAccept() {
      cleanup();
      // true = skip re-running the confirm hook for this request
      if (d.issueRequest) d.issueRequest(true);
    }
    function onCancel() {
      cleanup();
      // htmx-4: explicitly drop the held request; htmx<=2: preventDefault
      // already suppressed it, so dropRequest is absent and this is a no-op.
      if (d.dropRequest) d.dropRequest();
    }
    function onClose() {
      // Esc / backdrop close — treat as cancel
      cleanup();
      if (d.dropRequest) d.dropRequest();
    }

    accept.addEventListener("click", onAccept);
    cancel.addEventListener("click", onCancel);
    dlg.addEventListener("close", onClose);

    dlg.showModal();
    accept.focus();
  });
})();

/* ── controllers/command.js ── */
/* HYPERPART: command */
/*
 * command — command-palette controller (HaTchi-MaXchi tranche 2B).
 *
 * Part of the `command` Hyperpart — see its manifest in site/registry.py
 * (partial + exchange contract) and its styles in components/hm-core.css
 * (also marked `HYPERPART: command`). `python tools/hyperpart.py command`
 * lists every part.
 *
 * The palette itself is server-rendered markup (dialog.command with an
 * hx-get input); this controller only owns the purely-client bits:
 *   - ⌘K / Ctrl-K opens the first .command dialog on the page
 *   - Esc closes explicitly (the palette's input is type="search", whose
 *     native behaviour swallows the first Esc to clear its value — so
 *     relying on <dialog>'s built-in cancel needs TWO presses mid-query)
 *   - ArrowUp/ArrowDown move the active option: the active .command__item
 *     gets [aria-selected] AND its id is named by the searchbox input's
 *     aria-activedescendant, so screen readers follow it (the input is a
 *     type=search searchbox with aria-controls → the listbox)
 *   - Enter activates the selected item (click — works for <a> and
 *     <button hx-*> items alike)
 * Results arrive via htmx swaps; selection resets on each swap.
 */
(function () {
  "use strict";

  function palette() {
    return document.querySelector("dialog.command");
  }

  function items(dlg) {
    return Array.prototype.slice.call(
      dlg.querySelectorAll(".command__item"),
    );
  }

  function queryInput(dlg) {
    return dlg.querySelector(".command__input");
  }

  function select(dlg, index) {
    var list = items(dlg);
    var activeId = "";
    list.forEach(function (el, i) {
      // Stable option id per result set — required for the combobox
      // aria-activedescendant pointer (screen readers follow the active
      // option only when the input names it; visual aria-selected alone
      // is silent to AT).
      if (!el.id) el.id = "command-opt-" + i;
      if (i === index) {
        el.setAttribute("aria-selected", "true");
        el.scrollIntoView({ block: "nearest" });
        activeId = el.id;
      } else {
        el.removeAttribute("aria-selected");
      }
    });
    var inp = queryInput(dlg);
    if (inp) {
      if (activeId) inp.setAttribute("aria-activedescendant", activeId);
      else inp.removeAttribute("aria-activedescendant");
    }
    return index;
  }

  function selectedIndex(dlg) {
    var list = items(dlg);
    for (var i = 0; i < list.length; i++) {
      if (list[i].getAttribute("aria-selected") === "true") return i;
    }
    return -1;
  }

  document.addEventListener("keydown", function (evt) {
    var dlg = palette();
    if (!dlg) return;

    if ((evt.metaKey || evt.ctrlKey) && (evt.key === "k" || evt.key === "K")) {
      evt.preventDefault();
      if (dlg.open) {
        dlg.close();
      } else {
        dlg.showModal();
        var input = dlg.querySelector(".command__input");
        if (input) input.focus();
      }
      return;
    }

    if (!dlg.open) return;

    if (evt.key === "Escape") {
      evt.preventDefault();
      dlg.close();
    } else if (evt.key === "ArrowDown" || evt.key === "ArrowUp") {
      evt.preventDefault();
      var count = items(dlg).length;
      if (!count) return;
      var cur = selectedIndex(dlg);
      var next = evt.key === "ArrowDown" ? cur + 1 : cur - 1;
      if (next < 0) next = count - 1;
      if (next >= count) next = 0;
      select(dlg, next);
    } else if (evt.key === "Enter") {
      var idx = selectedIndex(dlg);
      if (idx >= 0) {
        evt.preventDefault();
        items(dlg)[idx].click();
      }
    }
  });

  // Reset selection whenever htmx swaps new results in. Bound under BOTH
  // names: htmx-4 fires `htmx:after:swap`, htmx ≤2 fired `htmx:afterSwap` —
  // binding only the legacy name left this dead under the vendored htmx-4.
  function onResultsSwap(evt) {
    var dlg = palette();
    if (dlg && dlg.open && dlg.contains(evt.target)) {
      if (items(dlg).length) {
        select(dlg, 0);
      } else {
        // empty result set — drop the stale activedescendant pointer
        var inp = queryInput(dlg);
        if (inp) inp.removeAttribute("aria-activedescendant");
      }
    }
  }
  document.addEventListener("htmx:after:swap", onResultsSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onResultsSwap); // htmx ≤2

  // Pointer dismiss — the ONLY way to close on a touch device with no Esc
  // key. Two paths: the explicit close button (a native <button>, so its
  // tap fires reliably everywhere incl. iOS Safari) and a backdrop tap.
  // For the backdrop we check `target === dlg`: a modal <dialog>'s box is
  // its content, so a click on the surrounding backdrop targets the dialog
  // ELEMENT, while a click anywhere else (e.g. the opener button) targets
  // that element — so this never fires on the same click that opened the
  // palette. (A naive "outside the dialog rect" test would: the opener is
  // outside, so it'd close on open.) Native `closedby="any"` covers this
  // where supported; this is the cross-browser floor.
  document.addEventListener("click", function (evt) {
    var dlg = palette();
    if (!dlg || !dlg.open) return;
    if (
      evt.target === dlg ||
      (evt.target.closest && evt.target.closest("[data-hm-close-command]"))
    ) {
      dlg.close();
    }
  });
})();

/* ── controllers/master-detail.js ── */
/* HYPERPART: master-detail */
/*
 * master-detail — selection state for the master-detail composite.
 *
 * The detail pane is loaded by htmx (the list item's hx-get swaps a card
 * fragment into .master-detail__detail); this controller owns only the
 * selection marker (aria-current) on the list.
 *
 * INSTANCE-ISOLATED — the reference pattern for composable controllers:
 * one delegated listener on `document`, but every DOM query is scoped to the
 * clicked item's OWN `.master-detail` root. So N master-details on one
 * page each manage their own selection independently (unlike a global
 * `document.querySelector`, which would drive only the first).
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var item = evt.target.closest(".master-detail__item");
    if (!item) return;
    var root = item.closest(".master-detail");
    if (!root) return;
    // clear the previous selection WITHIN THIS root only, then mark this one
    var current = root.querySelectorAll(
      ".master-detail__item[aria-current]",
    );
    for (var i = 0; i < current.length; i++) {
      current[i].removeAttribute("aria-current");
    }
    item.setAttribute("aria-current", "true");
  });
})();

/* ── controllers/dialog.js ── */
/* HYPERPART: dialog */
/*
 * dialog — open a native <dialog> from a delegated trigger.
 *
 * The ONLY behaviour that isn't native: a [data-dialog-open="id"]
 * click calls showModal() on the <dialog id="id"> it names. Close, focus
 * trapping, the inert background and the backdrop tap are all the
 * platform's own (the dialog's <form method="dialog"> buttons + Esc +
 * closedby="any").
 *
 * INSTANCE-ISOLATED — one delegated listener, but the trigger addresses
 * its OWN dialog by id (getElementById), so N dialogs coexist without a
 * shared global handle (contrast command.js's page-level singleton).
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var trigger = evt.target.closest("[data-dialog-open]");
    if (!trigger) return;
    var id = trigger.getAttribute("data-dialog-open");
    if (!id) return;
    var dlg = document.getElementById(id);
    // Guard: only drive a real <dialog> (showModal is dialog-only). A
    // missing id or wrong element type is a no-op, not a throw.
    if (dlg && typeof dlg.showModal === "function") {
      evt.preventDefault();
      dlg.showModal();
    }
  });
})();

/* ── controllers/slider.js ── */
/* HYPERPART: slider */
/*
 * slider — live value readout for a native <input type="range">.
 *
 * Delegated from document; on `input` it writes the range's current value into
 * the `[data-range-value]` readout within the SAME group, so N sliders on a
 * page stay independent (every query scoped to the input's own group — never a
 * global document.querySelector).
 *
 * Skips inputs already managed by a widget bridge (`[data-widget]`) so it
 * never double-handles a host that wires its own range controller. It is the
 * canonical HM value controller: a host adopts it simply by dropping that
 * wrapper attribute.
 */
(function () {
  "use strict";

  // The readout for a range input, or null if this input isn't ours to touch
  // (not a slider, or already owned by a widget bridge). One guard, used by
  // both the delegated listener and the one-time mount sync.
  function readoutFor(input) {
    if (!input || !input.matches) return null;
    if (!input.matches('input[type="range"][data-slider]')) return null;
    if (input.closest("[data-widget]")) return null;
    var group = input.closest(".form-slider-group") || input.parentElement;
    return group ? group.querySelector("[data-range-value]") : null;
  }

  document.addEventListener("input", function (evt) {
    var out = readoutFor(evt.target);
    if (out) out.textContent = evt.target.value;
  });

  // One-time sync so a hard-coded `value=` matches its readout before the first
  // input (copy-paste robustness). Respects the same guard, so it never touches
  // a widget-bridge-managed range.
  function sync() {
    var inputs = document.querySelectorAll(
      'input[type="range"][data-slider]',
    );
    for (var i = 0; i < inputs.length; i++) {
      var out = readoutFor(inputs[i]);
      if (out) out.textContent = inputs[i].value;
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();

/* ── controllers/tabs.js ── */
/* HYPERPART: tabs */
/*
 * tabs — activate a tab + reveal its panel.
 *
 * Delegated from document; a click on a `.tabs__tab` marks it
 * `aria-current="true"` and hides its siblings' panels, all scoped to the
 * clicked tab's OWN `.tabs` root (every query via `closest`), so N tab
 * groups on one page stay independent. Revealing a `hidden` panel is what
 * triggers its `hx-trigger="intersect once"` lazy load (a display:none panel
 * has no intersection; showing it makes htmx fetch it once).
 *
 * Replaces the per-tab inline `onclick` handler the legacy tabbed list used —
 * one delegated listener, no inline script (CSP-friendlier), instance-safe.
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var tab = evt.target.closest(".tabs__tab");
    if (!tab) return;
    var root = tab.closest(".tabs");
    if (!root) return;

    // Ownership filter: querySelectorAll is descendant-scoped, so a
    // NESTED .tabs group (e.g. a related-tables strip inside a
    // tabbed_list region panel) would have its tabs/panels collected by
    // the OUTER root's click. Only touch elements whose closest .tabs
    // is this root.
    var tabs = root.querySelectorAll(".tabs__tab");
    for (var i = 0; i < tabs.length; i++)
      if (tabs[i].closest(".tabs") === root)
        tabs[i].removeAttribute("aria-current");
    tab.setAttribute("aria-current", "true");

    var panels = root.querySelectorAll(".tabs__panel");
    for (var j = 0; j < panels.length; j++)
      if (panels[j].closest(".tabs") === root) panels[j].hidden = true;

    var targetId = tab.getAttribute("data-tab-target");
    var panel = targetId
      ? root.querySelector(
          "#" + (window.CSS && CSS.escape ? CSS.escape(targetId) : targetId),
        )
      : null;
    if (panel) panel.hidden = false; // reveal → triggers the panel's intersect-once load
  });
})();

/* ── controllers/grid.js ── */
/* HYPERPART: grid */
/*
 * grid — the data-table controller. Slices: selection + sort + filter +
 * search + bulk actions + pagination.
 *
 * Delegated + state-in-DOM, the HM idiom (same shape as tabs.js): one pair
 * of document-level listeners, everything scoped to the clicked control's own
 * `[data-grid]` root via `closest()`, so N grids on a page stay independent.
 * There is NO framework and NO reactive scope — the primary selection state is
 * each checkbox's own `.checked`, which idiomorph preserves in place across a
 * tbody swap (the exact thing Alpine's reactive scope did NOT survive). The
 * *derived* state — the root's `data-bulk-count`, the summary text, and the
 * select-all tri-state — is a projection of those checkboxes, so it is
 * recomputed on every `change`/`click` AND re-synced after any swap (htmx-4
 * `htmx:after:swap`; the legacy `htmx:afterSwap` is bound too)
 * (a swap changes the row set, so the projection must be rebuilt from the
 * surviving boxes). Row identity across a re-sort/paginate: idiomorph preserves a
 * checkbox by DOM position UNLESS its row carries a stable `id`, which idiomorph
 * then uses as the morph key — so a live selection follows its ROW, not a
 * position. The server emits that `id` (`grid-row-<rowid>`);
 * `data-grid-row-id` stays the bulk-action payload anchor, and the id encodes
 * it so the two agree. (The HM gallery mock emits it today; Dazzle's row emitter
 * adopts it when the runtime converges onto this primitive.)
 *
 * Contract:
 *   - root:        `[data-grid]` (also the `.table` the bulk CSS gates on)
 *   - row box:     `[data-grid-select]` (a checkbox; may carry
 *                  `data-grid-row-id` for later bulk payloads)
 *   - select-all:  `[data-grid-select-all]` (header checkbox; reflects
 *                  checked / indeterminate / unchecked)
 *   - count sink:  `data-bulk-count` written on the root (the CSS reveals
 *                  `.bulk-actions` when it isn't "0") + `[data-bulk-count-target]`
 *                  mirrors the number for a "N selected" summary
 *   - clear:       `[data-grid-clear]` deselects everything
 *   - body:        `[data-grid-body]` (the tbody htmx swaps; `data-grid-src`
 *                  holds its immutable base endpoint, `hx-get` its current query)
 *   - sort:        `[data-grid-sort="<key>"]` (a header button) cycles the
 *                  clicked column through `data-grid-sort-cycle`
 *                  (default "asc desc none"); state lives on the th's `aria-sort`
 *   - filter:      `[data-grid-filter="<key>"]` (a form control) narrows on
 *                  change; empty value = no filter. Composes with sort — the
 *                  request query is rebuilt from ALL current DOM state.
 *   - search:      `[data-grid-search]` (an input) adds `q=` on input,
 *                  debounced (`data-grid-debounce`, default 250ms). Composes
 *                  with sort + filter into the same query. NB `q`, `sort`, `dir`,
 *                  `page`, `page_size` (query keys) and `action`, `selected_ids`,
 *                  `all_matching_selected`, `excluded_ids` (bulk-payload keys) are
 *                  reserved — don't use them as a `data-grid-filter` value.
 *   - bulk:        `[data-grid-bulk-action="<action>"]` (a button, usually
 *                  with `hx-post` + `hx-confirm`) — on the config-request
 *                  event (htmx-4 `htmx:config:request` / legacy
 *                  `htmx:configRequest`) the
 *                  controller injects the selection payload (action, selected
 *                  ids, all-matching/excluded shape, current-query echo) so the
 *                  server re-scopes + re-validates, never trusting client ids.
 *   - bulk refresh: `data-grid-bulk-refresh` on a bulk button opts into the
 *                  two-request pattern — the POST's response swaps nothing
 *                  (JSON/204); after it settles the controller re-fetches
 *                  rows + footer for the current query. Omit it when the
 *                  server returns the refreshed rows directly (hx-target).
 *   - all-matching: `[data-grid-select-all-matching]` (a button, in the bulk
 *                  bar) escalates the selection to the WHOLE matched query —
 *                  `data-grid-all-matching="true"` on the root, exclusions
 *                  (rows the user unchecks) in `data-grid-excluded` (a JSON
 *                  array of row-ids). The matched TOTAL comes from the
 *                  server-rendered footer's `data-grid-total` and is
 *                  mirrored into any `[data-grid-matching-total]`. A filter /
 *                  search change that CHANGES the matched set drops the mode
 *                  (compared against the `data-grid-scope` snapshot taken at
 *                  entry, so a net-unchanged keystroke keeps it); a sort or
 *                  page change keeps it (same set, reordered/windowed).
 *   - page:        current page is `data-grid-page` on the root (default 1).
 *                  `[data-grid-goto="<n>"]` / `[data-grid-page-prev]` /
 *                  `[data-grid-page-next]` (server-rendered footer buttons)
 *                  set it + refresh (`page=` in the query); the server disables
 *                  prev/next at the edges. Sort / filter / search reset it to 1.
 *   - announcer:   `[data-grid-announce]` (a visually-hidden aria-live
 *                  region, static in the markup) — after every swap the
 *                  controller mirrors the footer's result-window summary into
 *                  it ("Showing 1-4 of 6"), because the footer itself is
 *                  repainted wholesale, which screen readers can't track.
 *                  Page-control focus is restored onto the repainted
 *                  equivalent (or the current-page button when that control
 *                  is now disabled) so keyboard focus never falls to <body>.
 *   - page size:   `[data-grid-page-size]` (a select) re-windows the same
 *                  matched set — `page_size=` joins the query, the change
 *                  resets to page 1, and an all-matching selection SURVIVES
 *                  (windowing, not a scope change). NB the initial `load`
 *                  fires the tbody's static `hx-get` (refresh() isn't
 *                  involved), so a server pre-selecting a NON-default size
 *                  must also bake `page_size=` into that initial URL — else
 *                  the first interaction visibly re-windows.
 *   - url:         `data-grid-url` on the root (opt-in) mirrors the grid's
 *                  query into the address bar — the SAME human-readable
 *                  params the server sees. Discrete actions (sort / filter /
 *                  page / size) push history entries (Back walks grid
 *                  states); the debounced search replaces. Restore order per
 *                  the spec: URL params > EXISTING DOM > defaults — the
 *                  server-rendered state is snapshotted at init and an
 *                  ABSENT URL param restores to it (a `ux: sort:` default
 *                  the entry URL omits must survive a deep link that only
 *                  sets, say, a filter). Deep links apply at controller init
 *                  (before htmx fetches); a param-less entry URL leaves the
 *                  DOM untouched. History entries carry `{htmx: true}` so a
 *                  Back from a FOREIGN page (e.g. an hx-push-url row-drill
 *                  detail) triggers real htmx-4's server restore; the
 *                  after-settle re-sync then applies the URL's grid state to
 *                  the freshly rendered (default-state) DOM. On htmx-less
 *                  hosts (the static gallery) popstate restores client-side.
 *                  The grid only touches its OWN keys — foreign URL params
 *                  survive. One url-synced grid per page (keys not
 *                  namespaced yet).
 */
(function () {
  "use strict";

  function gridOf(el) {
    return el.closest ? el.closest("[data-grid]") : null;
  }

  function rowBoxes(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll("[data-grid-select]"),
    );
  }

  // ── All-matching selection: state on the root, not the rows ────────────
  // `data-grid-all-matching="true"` marks the WHOLE matched query selected
  // (every page); `data-grid-excluded` (a JSON array of row-ids) records
  // the exceptions the user unchecked. Both live on the root because the
  // selection spans pages the DOM doesn't hold. The matched TOTAL is read from
  // the server-rendered footer's `data-grid-total` — the server is
  // authoritative about how many rows match.
  function allMatching(root) {
    return root.getAttribute("data-grid-all-matching") === "true";
  }

  function readExcluded(root) {
    try {
      var ids = JSON.parse(root.getAttribute("data-grid-excluded") || "[]");
      return Array.isArray(ids) ? ids : [];
    } catch (e) {
      return [];
    }
  }

  function writeExcluded(root, ids) {
    if (ids.length) {
      root.setAttribute("data-grid-excluded", JSON.stringify(ids));
    } else {
      root.removeAttribute("data-grid-excluded");
    }
  }

  function clearAllMatching(root) {
    root.removeAttribute("data-grid-all-matching");
    root.removeAttribute("data-grid-excluded");
    root.removeAttribute("data-grid-scope");
  }

  // The matched-set-DEFINING part of the query: search + filters. Sort and
  // page reorder/window the SAME set, so they're not part of the scope.
  function scopeKey(root) {
    var parts = [];
    var search = root.querySelector("[data-grid-search]");
    if (search && search.value) parts.push("q=" + search.value);
    var filters = root.querySelectorAll("[data-grid-filter]");
    for (var i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-grid-filter");
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
    if (scopeKey(root) !== (root.getAttribute("data-grid-scope") || "")) {
      clearAllMatching(root);
    }
  }

  function matchedTotal(root) {
    var nav = root.querySelector("[data-grid-pagination]");
    if (!nav) return null;
    var t = parseInt(nav.getAttribute("data-grid-total"), 10);
    return isNaN(t) ? null : t;
  }

  // Mirror the server-rendered result-window summary ("1-4 of 6") into the
  // visually-hidden `[data-grid-announce]` live region — the footer itself
  // is repainted wholesale, which screen readers can't track. Only on CHANGE:
  // repeating an identical announcement is SR noise.
  function announce(root) {
    var out = root.querySelector("[data-grid-announce]");
    if (!out) return;
    // Prefer the row-window span when the summary is the selected/rows PAIR
    // (the count half is already covered by the bulk bar's own live region).
    var summary =
      root.querySelector("[data-grid-pagination] .bulk-summary-rows") ||
      root.querySelector("[data-grid-pagination] .pagination-summary");
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
    // `.table:not([data-bulk-count="0"]) .bulk-actions { display:flex }`.
    root.setAttribute("data-bulk-count", String(count));
    // ALL count mirrors update — the bulk bar's "Delete N items" AND the
    // footer's "N of M selected" (querySelector-first left the footer stuck
    // at 0 — C1.1 review catch).
    var targets = root.querySelectorAll("[data-bulk-count-target]");
    for (var t = 0; t < targets.length; t++) {
      targets[t].textContent = String(count);
    }
    // Mirror the matched total into the escalation affordance's label
    // ("Select all N matching") whenever the footer knows it.
    var mirror = root.querySelector("[data-grid-matching-total]");
    if (mirror && total !== null) mirror.textContent = String(total);
    var all = root.querySelector("[data-grid-select-all]");
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
  // `data-grid-sort-cycle` (default "asc desc none"), clears every OTHER
  // sortable header (one ORDER BY at a time), rebuilds the tbody's request query
  // from that state, and fires `grid:refresh` so the server returns the
  // re-ordered rows (real htmx via the tbody's `hx-trigger`; the gallery mock via
  // a listener). The controller NEVER re-renders rows — it only asks.
  var DIR_OF = { ascending: "asc", descending: "desc", none: "none" };
  var ARIA_OF = { asc: "ascending", desc: "descending", none: "none" };

  function sortButtons(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll("[data-grid-sort]"),
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
        return { key: btns[i].getAttribute("data-grid-sort"), dir: dir };
      }
    }
    return null;
  }

  // Build the tbody's request query from ALL current DOM state — the search
  // box, the active sort, every filter select, the page-size select, and the
  // root's page — so they all COMPOSE into one server query.
  function buildQuery(root) {
    var q = [];
    var search = root.querySelector("[data-grid-search]");
    if (search && search.value) {
      q.push("q=" + encodeURIComponent(search.value));
    }
    var s = readSort(root);
    if (s) {
      q.push("sort=" + encodeURIComponent(s.key));
      q.push("dir=" + s.dir);
    }
    var filters = root.querySelectorAll("[data-grid-filter]");
    for (var i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-grid-filter");
      var v = filters[i].value;
      if (k && v) q.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    }
    // Page size: a windowing control ([data-grid-page-size] select). Sent
    // whenever the control exists — the server's own default applies when the
    // grid doesn't offer the choice.
    var size = root.querySelector("[data-grid-page-size]");
    if (size && size.value) {
      q.push("page_size=" + encodeURIComponent(size.value));
    }
    // Current page lives on the root; page 1 is the default (omitted for a clean
    // query). Search / sort / filter reset it to 1 via resetPage() BEFORE calling
    // refresh; a page-control click sets it, then refreshes.
    var page = root.getAttribute("data-grid-page");
    if (page && page !== "1") q.push("page=" + encodeURIComponent(page));
    return q.join("&");
  }

  // Write the current DOM state onto the tbody's `hx-get` (no fetch) — the
  // shared half of refresh() and the URL-restore path (where the `load`
  // trigger or the popstate caller does the fetching).
  function setQuery(root) {
    var body = root.querySelector("[data-grid-body]");
    if (!body) return null;
    var base = (
      body.getAttribute("data-grid-src") ||
      body.getAttribute("hx-get") ||
      ""
    ).split("?")[0];
    var qs = buildQuery(root);
    body.setAttribute("hx-get", base + (qs ? "?" + qs : ""));
    return body;
  }

  // ── URL-synced state (opt-in: `data-grid-url` on the root) ──────────
  // The grid's query lands in the address bar as the SAME human-readable
  // params the server sees (spec §7) — q / sort / dir / page / page_size plus
  // this grid's filter keys. The grid only ever touches its OWN keys, so
  // foreign params on the page URL survive. Discrete actions (sort / filter /
  // page / size) PUSH a history entry — Back walks grid states; the debounced
  // search REPLACES (a keystroke burst is not N history entries). The
  // all-matching selection is ephemeral UI state and is deliberately NOT in
  // the URL.
  function ownedKeys(root) {
    var keys = { q: 1, sort: 1, dir: 1, page: 1, page_size: 1 };
    var filters = root.querySelectorAll("[data-grid-filter]");
    for (var i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-grid-filter");
      if (k) keys[k] = 1;
    }
    return keys;
  }

  function syncUrl(root, mode) {
    if (!root.hasAttribute("data-grid-url")) return;
    var owned = ownedKeys(root);
    var sp = new URLSearchParams(location.search);
    Object.keys(owned).forEach(function (k) {
      sp.delete(k);
    });
    // The tbody's hx-get query is the single source of truth for what the
    // grid is showing — mirror exactly that into the URL.
    var body = root.querySelector("[data-grid-body]");
    var qs = ((body && body.getAttribute("hx-get")) || "").split("?")[1] || "";
    new URLSearchParams(qs).forEach(function (v, k) {
      sp.set(k, v);
    });
    var urlq = sp.toString();
    var url = location.pathname + (urlq ? "?" + urlq : "") + location.hash;
    // The state object carries `{htmx: true}` — htmx-4 only restores history
    // entries it recognises (its popstate handler checks `e.state.htmx`), so
    // an unmarked grid entry would strand the user when they Back onto it
    // from a foreign page (e.g. a row-drill detail): nothing would restore
    // the list. Marked, htmx re-GETs the full page; the after-settle re-sync
    // below then applies the URL's grid state to the freshly rendered DOM.
    if (mode === "push") history.pushState({ htmx: true }, "", url);
    else history.replaceState({ htmx: true }, "", url);
  }

  // Apply the URL's params onto the grid's controls + the tbody query (NO
  // fetch — at init the `load` trigger fetches; on popstate the caller
  // dispatches the refresh). Runs at controller parse time, BEFORE htmx
  // initialises, so the hydration fetch already carries the restored query —
  // no default-then-correct double fetch. (A server rendering this page can
  // also bake the params in directly; this restore is then a no-op.)
  // Snapshot a url-synced grid's SERVER-RENDERED state at controller parse —
  // the "existing DOM" tier of the spec's restore order (URL params > existing
  // DOM > defaults). An ABSENT URL param must restore to this, not to empty:
  // a server-rendered default (e.g. a `ux: sort:` header marked ascending, or
  // a pre-selected filter) is state the entry URL legitimately omits.
  function captureInitial(root) {
    var state = {
      search: "",
      sorts: {},
      filters: {},
      size: "",
      page: root.getAttribute("data-grid-page") || "1",
    };
    var search = root.querySelector("[data-grid-search]");
    if (search) state.search = search.value;
    var btns = sortButtons(root);
    for (var i = 0; i < btns.length; i++) {
      var th = btns[i].closest("th");
      if (th) {
        state.sorts[btns[i].getAttribute("data-grid-sort")] =
          th.getAttribute("aria-sort") || "none";
      }
    }
    var filters = root.querySelectorAll("[data-grid-filter]");
    for (i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-grid-filter");
      if (k) state.filters[k] = filters[i].value;
    }
    var size = root.querySelector("[data-grid-page-size]");
    if (size) state.size = size.value;
    root._dzInitial = state;
  }

  // True when the URL carries ANY of this grid's owned keys — the gate for
  // touching the server-rendered state at init (a param-less entry URL must
  // leave the DOM and the tbody's default query completely alone).
  function urlHasGridState(root, sp) {
    var owned = ownedKeys(root);
    var keys = Object.keys(owned);
    for (var i = 0; i < keys.length; i++) {
      if (sp.has(keys[i])) return true;
    }
    return false;
  }

  function restoreFromUrl(root) {
    if (!root.hasAttribute("data-grid-url")) return;
    var sp = new URLSearchParams(location.search);
    var init = root._dzInitial || {
      search: "",
      sorts: {},
      filters: {},
      size: "",
      page: "1",
    };
    var search = root.querySelector("[data-grid-search]");
    if (search) search.value = sp.has("q") ? sp.get("q") : init.search;
    var sort = sp.get("sort");
    var dir = sp.get("dir");
    if (dir !== "asc" && dir !== "desc") dir = null;
    var urlSort = Boolean(sort && dir);
    var btns = sortButtons(root);
    for (var i = 0; i < btns.length; i++) {
      var th = btns[i].closest("th");
      if (!th) continue;
      var key = btns[i].getAttribute("data-grid-sort");
      if (urlSort) {
        th.setAttribute("aria-sort", key === sort ? ARIA_OF[dir] : "none");
      } else {
        // No sort in the URL → the initial (server-rendered) state stands.
        th.setAttribute("aria-sort", init.sorts[key] || "none");
      }
    }
    var filters = root.querySelectorAll("[data-grid-filter]");
    for (i = 0; i < filters.length; i++) {
      var k = filters[i].getAttribute("data-grid-filter");
      if (!k) continue;
      filters[i].value = sp.has(k) ? sp.get(k) : init.filters[k] || "";
    }
    var size = root.querySelector("[data-grid-page-size]");
    if (size)
      size.value = sp.has("page_size") ? sp.get("page_size") : init.size;
    root.setAttribute(
      "data-grid-page",
      sp.has("page") ? sp.get("page") : init.page,
    );
    setQuery(root);
  }

  // Rebuild the query from the DOM, sync the URL (per `urlMode`: "push" for
  // discrete actions, "replace" for continuous ones, falsy for none — e.g.
  // the popstate path, which must never rewrite the URL it is restoring), and
  // ask the server (via `grid:refresh`) for the matching, ordered rows.
  function refresh(root, urlMode) {
    var body = setQuery(root);
    if (!body) return;
    if (urlMode) syncUrl(root, urlMode);
    body.dispatchEvent(new CustomEvent("grid:refresh", { bubbles: true }));
  }

  function resetPage(root) {
    root.setAttribute("data-grid-page", "1");
  }

  function applySort(root, btn) {
    var th = btn.closest("th");
    var cur = (th && th.getAttribute("aria-sort")) || "none";
    var cycle = (btn.getAttribute("data-grid-sort-cycle") || "asc desc none")
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
    refresh(root, "push"); // reads the sort we just wrote + any active filters
  }

  // Search: debounced so a burst of keystrokes makes ONE request. The timer
  // lives on the input itself (delegated, no per-grid state map). Default 250ms,
  // overridable with `data-grid-debounce`.
  document.addEventListener("input", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-grid-search]")) return;
    var root = gridOf(t);
    if (!root) return;
    var ms = parseInt(t.getAttribute("data-grid-debounce"), 10);
    if (isNaN(ms)) ms = 250;
    if (t._dzSearchTimer) clearTimeout(t._dzSearchTimer);
    t._dzSearchTimer = setTimeout(function () {
      t._dzSearchTimer = null;
      // A search that CHANGES the matched set drops all-matching — a
      // selection over the old query must not silently apply to the new one.
      // (Scope-compared, so a net-unchanged keystroke keeps the mode.)
      dropModeIfScopeChanged(root);
      resetPage(root); // a new search starts at page 1
      refresh(root, "replace"); // continuous input REPLACES (no history spam)
    }, ms);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-grid-select]")) {
      var r = gridOf(t);
      if (!r) return;
      if (allMatching(r)) {
        // In all-matching mode a row toggle edits the EXCLUSION list on the
        // root — the row's own checkbox can't carry the state, because the
        // selection spans pages whose boxes aren't in the DOM.
        var id = t.getAttribute("data-grid-row-id");
        if (id) {
          var ex = readExcluded(r);
          var at = ex.indexOf(id);
          if (!t.checked && at < 0) ex.push(id);
          if (t.checked && at >= 0) ex.splice(at, 1);
          writeExcluded(r, ex);
        }
      }
      sync(r);
    } else if (t.matches("[data-grid-select-all]")) {
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
    } else if (t.matches("[data-grid-filter]")) {
      // A filter select changed → rebuild the query (composing with any active
      // sort) and reload the rows from the server, back at page 1. The matched
      // set changed, so an all-matching selection drops (same rule as search).
      var fr = gridOf(t);
      if (fr) {
        dropModeIfScopeChanged(fr);
        resetPage(fr);
        refresh(fr, "push");
      }
    } else if (t.matches("[data-grid-page-size]")) {
      // Page size re-WINDOWS the same matched set (like a page click, NOT a
      // scope change): back to page 1, but an all-matching selection survives.
      var zr = gridOf(t);
      if (zr) {
        resetPage(zr);
        refresh(zr, "push");
      }
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    // Pagination: a page-number (`data-grid-goto`) or prev/next control. The
    // server disables prev/next at the edges, so a disabled button won't fire;
    // the max(1, …) is a floor for safety. Page is state on the root.
    var goBtn = t.closest(
      "[data-grid-goto], [data-grid-page-prev], [data-grid-page-next]",
    );
    if (goBtn) {
      var proot = gridOf(goBtn);
      if (proot) {
        evt.preventDefault();
        var cur = parseInt(proot.getAttribute("data-grid-page"), 10) || 1;
        var to;
        if (goBtn.hasAttribute("data-grid-page-prev"))
          to = Math.max(1, cur - 1);
        else if (goBtn.hasAttribute("data-grid-page-next")) to = cur + 1;
        else to = parseInt(goBtn.getAttribute("data-grid-goto"), 10) || 1;
        proot.setAttribute("data-grid-page", String(to));
        // The swap repaints the footer wholesale, destroying the focused
        // control — note the INTENT (not the node) so afterSwap can restore
        // focus onto the repainted equivalent. Ephemeral UI state, so a JS
        // property (not an attribute) is fine: it never has to survive a morph.
        proot._dzRefocus = goBtn.hasAttribute("data-grid-page-prev")
          ? "prev"
          : goBtn.hasAttribute("data-grid-page-next")
            ? "next"
            : "goto:" + to;
        refresh(proot, "push");
      }
      return;
    }
    var sortBtn = t.closest("[data-grid-sort]");
    if (sortBtn) {
      var sroot = gridOf(sortBtn);
      if (sroot) {
        evt.preventDefault();
        applySort(sroot, sortBtn);
      }
      return;
    }
    var amBtn = t.closest("[data-grid-select-all-matching]");
    if (amBtn) {
      var aroot = gridOf(amBtn);
      if (aroot) {
        // Escalate to the whole matched query: mark the root, snapshot the
        // scope the user confirmed (search + filters — so a later change can
        // be told apart from a net no-op), drop any stale exclusions, and
        // check the visible boxes so the DOM agrees.
        aroot.setAttribute("data-grid-all-matching", "true");
        aroot.setAttribute("data-grid-scope", scopeKey(aroot));
        writeExcluded(aroot, []);
        var aboxes = rowBoxes(aroot);
        for (var j = 0; j < aboxes.length; j++) aboxes[j].checked = true;
        sync(aroot);
      }
      return;
    }
    var clear = t.closest("[data-grid-clear]");
    if (!clear) return;
    var root = gridOf(clear);
    if (!root) return;
    clearAllMatching(root); // Clear means everything — mode included
    var boxes = rowBoxes(root);
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
    sync(root);
  });

  // ── Bulk actions: add the selection to the request ─────────────────────
  // A `[data-grid-bulk-action]` button posts (after its confirm). On the
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
    var btn = el && el.closest && el.closest("[data-grid-bulk-action]");
    if (!btn) return;
    var root = gridOf(btn);
    if (!root) return;
    // Assemble the payload: the query echo FIRST — the filter/sort/search the
    // rows came from — then the bulk keys LAST so they always win (a filter
    // named `action` etc. can't clobber the operation name).
    var payload = {};
    var body = root.querySelector("[data-grid-body]");
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
        var id = boxes[i].getAttribute("data-grid-row-id");
        if (id) ids.push(id);
      }
    }
    payload.action = btn.getAttribute("data-grid-bulk-action");
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
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      // In all-matching mode freshly-rendered rows arrive SELECTED (minus the
      // exclusions): the mode spans pages, the DOM doesn't, so each swap
      // re-projects the root's state onto the new boxes.
      if (allMatching(grids[i])) {
        var ex = readExcluded(grids[i]);
        var boxes = rowBoxes(grids[i]);
        for (var j = 0; j < boxes.length; j++) {
          boxes[j].checked =
            ex.indexOf(boxes[j].getAttribute("data-grid-row-id")) < 0;
        }
      }
      sync(grids[i]);
      // Re-sync the root's page from the server-rendered footer's current-page
      // marker: the server may have CLAMPED the page (e.g. a bulk delete that
      // removed the last page), so the client's requested page can be stale.
      // The footer is authoritative about which page actually rendered.
      var nav = grids[i].querySelector("[data-grid-pagination]");
      var curBtn =
        nav && nav.querySelector("[data-grid-goto][aria-current='page']");
      if (curBtn) {
        var pnum = parseInt(curBtn.getAttribute("data-grid-goto"), 10);
        if (
          pnum &&
          String(pnum) !== grids[i].getAttribute("data-grid-page")
        ) {
          // The SERVER moved the page out from under the client (e.g. a bulk
          // delete emptied the last page). Follow it everywhere the page is
          // mirrored: the root, the tbody query, and — for a url-synced grid —
          // the address bar. REPLACE, not push: a clamp is a correction, not a
          // navigation the user should Back into.
          grids[i].setAttribute("data-grid-page", String(pnum));
          setQuery(grids[i]);
          syncUrl(grids[i], "replace");
        }
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
  // Does the DOM-derived query satisfy every grid-owned param IN THE URL?
  // Deliberately asymmetric: DOM-only extras (e.g. a page-size select's
  // default that no interaction has mirrored into the URL yet) are NOT a
  // divergence — only a URL param the DOM contradicts is.
  function domMatchesUrlState(root) {
    var owned = ownedKeys(root);
    var dom = {};
    new URLSearchParams(buildQuery(root)).forEach(function (v, k) {
      dom[k] = v;
    });
    var ok = true;
    new URLSearchParams(location.search).forEach(function (v, k) {
      if (owned[k] && (dom[k] || "") !== v) ok = false;
    });
    return ok;
  }

  function onAfterSettle() {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      // History-restore re-sync (url-synced grids): after htmx restores a
      // history entry it re-GETs the page, which renders the SERVER DEFAULT
      // state — while the URL still describes the grid state the user was
      // on. When the two diverge, re-apply the URL to the fresh DOM and
      // refetch. Normal swaps never diverge (the grid writes both sides), so
      // this no-ops everywhere else; the did-the-query-change dispatch guard
      // below is what makes it loop-proof (unsatisfiable params degrade).
      if (
        grids[i].hasAttribute("data-grid-url") &&
        urlHasGridState(grids[i], new URLSearchParams(location.search)) &&
        !domMatchesUrlState(grids[i])
      ) {
        // A history-restored body is a FRESH server render — its root never
        // went through the init loop, so snapshot it now: this DOM *is* the
        // server-default state that absent URL params must restore to.
        if (!grids[i]._dzInitial) captureInitial(grids[i]);
        // Re-dispatch ONLY when the restore actually changed the query (the
        // popstate path's proven guard): a URL param the DOM cannot express
        // (a renamed sort column in a stale bookmark, an out-of-range
        // page_size) leaves hx-get unchanged — dispatching anyway would
        // re-fetch forever (GET storm; stack overflow under a synchronous
        // mock). Unsatisfiable params degrade, they don't loop.
        var rbody = grids[i].querySelector("[data-grid-body]");
        var rBefore = rbody && rbody.getAttribute("hx-get");
        restoreFromUrl(grids[i]);
        if (rbody && rbody.getAttribute("hx-get") !== rBefore) {
          rbody.dispatchEvent(
            new CustomEvent("grid:refresh", { bubbles: true }),
          );
        }
      }
      var want = grids[i]._dzRefocus;
      if (!want) continue;
      grids[i]._dzRefocus = null;
      var nav = grids[i].querySelector("[data-grid-pagination]");
      if (!nav) continue;
      var el = null;
      if (want === "prev") {
        el = nav.querySelector("[data-grid-page-prev]:not([disabled])");
      } else if (want === "next") {
        el = nav.querySelector("[data-grid-page-next]:not([disabled])");
      } else {
        el = nav.querySelector(
          "[data-grid-goto='" + want.slice(5) + "']:not([disabled])",
        );
      }
      if (!el) {
        el = nav.querySelector("[data-grid-goto][aria-current='page']");
      }
      if (el) el.focus();
    }
  }
  document.addEventListener("htmx:after:settle", onAfterSettle); // htmx 4
  document.addEventListener("htmx:afterSettle", onAfterSettle); // htmx ≤2

  // ── Bulk two-request pattern ────────────────────────────────────────────
  // A bulk button carrying `data-grid-bulk-refresh` posts an action whose
  // response swaps NOTHING (a real server answers JSON/204) — after the
  // request settles the controller re-fetches rows + footer for the current
  // query, the same GET path every other state change uses. Servers that
  // return the refreshed rows directly (hx-target on the button) simply omit
  // the attribute. No urlMode: a bulk action doesn't change the query (a
  // server page-clamp is corrected by the after-swap re-sync).
  function onAfterRequest(evt) {
    var d = evt.detail || {};
    var el = d.elt || (d.ctx && d.ctx.sourceElement) || evt.target;
    var btn =
      el &&
      el.closest &&
      el.closest("[data-grid-bulk-action][data-grid-bulk-refresh]");
    if (!btn) return;
    var root = gridOf(btn);
    if (root) refresh(root);
  }
  document.addEventListener("htmx:after:request", onAfterRequest); // htmx 4
  document.addEventListener("htmx:afterRequest", onAfterRequest); // htmx ≤2

  // ── URL-state wiring ────────────────────────────────────────────────────
  // Init: apply the URL's params to every opted-in grid NOW, synchronously at
  // controller parse — before htmx initialises — so the hydration fetch
  // already carries the deep-linked query (no double fetch). Back/forward:
  // restore the state the URL describes, then fetch it; the popstate path
  // never calls syncUrl (it must not rewrite the history it is walking).
  var urlGrids = document.querySelectorAll("[data-grid][data-grid-url]");
  var initSp = new URLSearchParams(location.search);
  for (var g = 0; g < urlGrids.length; g++) {
    // Snapshot the server-rendered state FIRST — it's the restore target for
    // absent URL params (spec order: URL > existing DOM > defaults). Then
    // only touch the DOM when the URL actually carries grid state: a
    // param-less entry URL must leave the server-rendered defaults (and the
    // tbody's baked default query) completely alone.
    captureInitial(urlGrids[g]);
    if (urlHasGridState(urlGrids[g], initSp)) restoreFromUrl(urlGrids[g]);
  }

  window.addEventListener("popstate", function (evt) {
    // When REAL htmx is present and recognises the entry (state.htmx), it
    // owns the restore — a full-page GET replaces the body and the
    // after-settle re-sync applies the URL's grid state. The client-side
    // path below serves htmx-less hosts (the static gallery).
    // "Real htmx" = it exposes the ajax API the restore pipeline uses; the
    // static gallery's mock stub (`{version: "mock-4"}`) must NOT trip this.
    if (
      evt.state &&
      evt.state.htmx &&
      window.htmx &&
      typeof window.htmx.ajax === "function"
    ) {
      return;
    }
    var grids = document.querySelectorAll("[data-grid][data-grid-url]");
    for (var i = 0; i < grids.length; i++) {
      if (!grids[i]._dzInitial) captureInitial(grids[i]);
      var body = grids[i].querySelector("[data-grid-body]");
      // Back across a HASH-only history entry (e.g. in-page anchors) fires
      // popstate with the grid's params unchanged — skip the refetch when the
      // restore didn't change the query (no loading flash for a no-op).
      var before = body && body.getAttribute("hx-get");
      restoreFromUrl(grids[i]);
      if (body && body.getAttribute("hx-get") !== before) {
        body.dispatchEvent(
          new CustomEvent("grid:refresh", { bubbles: true }),
        );
      }
    }
  });
})();

/* ── controllers/grid-cols.js ── */
/*
 * HYPERPART: grid (extension)
 *
 * grid-cols — column visibility, an OPTIONAL grid extension on the grid
 * primitive's seams (promoted from the Dazzle layer, 0.1.26 — Dazzle now
 * consumes it from here).
 *
 * Same idiom as the primitive: delegated document-level listeners, state in
 * the DOM + localStorage, no framework. The menu itself is a native
 * `<details>` disclosure (the HM `.menu` idiom — no open/close JS).
 *
 * Contract:
 *   - root:    the `[data-grid]` element; its `id` keys the persisted
 *              hidden set (`localStorage["cols-<id>"]` — the SAME key the
 *              retired dzTable used, so users keep their saved preferences).
 *   - toggle:  `[data-grid-col-toggle="<key>"]` (a checkbox in the menu);
 *              checked = visible. The controller syncs the boxes from
 *              storage at init and after every change.
 *   - cells:   every `[data-col="<key>"]` th/td inside the root gets
 *              `style.display` applied — including rows hydrated later (the
 *              after-swap re-apply; hydrated cells carry no per-cell
 *              bindings).
 *   - prune:   stale stored keys that match no current column are dropped at
 *              init (#853 — otherwise a renamed column leaves invisible
 *              cells behind forever).
 *   - reset:   `[data-grid-cols-reset]` (a menu button) shows every
 *              column and clears the stored preference — the #853 escape
 *              hatch for a user who hid everything.
 */
(function () {
  "use strict";

  function storageKey(root) {
    return "cols-" + (root.id || "grid");
  }

  function readHidden(root) {
    try {
      var list = JSON.parse(localStorage.getItem(storageKey(root)) || "[]");
      return Array.isArray(list) ? list : [];
    } catch (e) {
      return [];
    }
  }

  function writeHidden(root, list) {
    try {
      localStorage.setItem(storageKey(root), JSON.stringify(list));
    } catch (e) {
      /* storage unavailable (private mode) — visibility still works, just
         doesn't persist */
    }
  }

  // Project the hidden set onto every [data-col] cell + the menu boxes.
  function apply(root) {
    var hidden = readHidden(root);
    var cells = root.querySelectorAll("[data-col]");
    for (var i = 0; i < cells.length; i++) {
      var key = cells[i].getAttribute("data-col");
      cells[i].style.display = hidden.indexOf(key) >= 0 ? "none" : "";
    }
    var boxes = root.querySelectorAll("[data-grid-col-toggle]");
    for (i = 0; i < boxes.length; i++) {
      boxes[i].checked =
        hidden.indexOf(boxes[i].getAttribute("data-grid-col-toggle")) < 0;
    }
  }

  // #853: drop stored keys that match no current column — stale storage from
  // before a column rename would otherwise hide cells forever ("headers
  // render but cells are empty"). Skips the prune when NO columns are present
  // (empty-state / not-yet-hydrated renders must not wipe the preference).
  function prune(root) {
    var present = {};
    var cells = root.querySelectorAll("[data-col]");
    if (!cells.length) return;
    for (var i = 0; i < cells.length; i++) {
      present[cells[i].getAttribute("data-col")] = true;
    }
    var hidden = readHidden(root);
    var cleaned = [];
    for (i = 0; i < hidden.length; i++) {
      if (present[hidden[i]]) cleaned.push(hidden[i]);
    }
    if (cleaned.length !== hidden.length) writeHidden(root, cleaned);
  }

  // Escape hatch (#853 follow-on): a menu affordance that shows every
  // column and clears the stored preference — without it, a user who
  // hides everything is stuck until they find devtools.
  document.addEventListener("click", function (evt) {
    var t =
      evt.target &&
      evt.target.closest &&
      evt.target.closest("[data-grid-cols-reset]");
    if (!t) return;
    var root = t.closest("[data-grid]");
    if (!root) return;
    try {
      localStorage.removeItem(storageKey(root));
    } catch (e) {
      /* storage unavailable — the in-DOM reset below still applies */
    }
    apply(root);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-grid-col-toggle]")) return;
    var root = t.closest("[data-grid]");
    if (!root) return;
    var key = t.getAttribute("data-grid-col-toggle");
    var hidden = readHidden(root);
    var at = hidden.indexOf(key);
    if (t.checked && at >= 0) hidden.splice(at, 1);
    if (!t.checked && at < 0) hidden.push(key);
    writeHidden(root, hidden);
    apply(root);
  });

  // Hydrated / re-fetched rows arrive visible-by-default — re-project the
  // hidden set after every swap. Bound under BOTH names (htmx-4 colon /
  // legacy camelCase), same as the primitive.
  function onSwap() {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      if (grids[i].querySelector("[data-grid-col-toggle]")) apply(grids[i]);
    }
  }
  document.addEventListener("htmx:after:swap", onSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onSwap); // htmx ≤2

  // Init: prune stale keys, then apply the stored preference.
  var grids = document.querySelectorAll("[data-grid]");
  for (var g = 0; g < grids.length; g++) {
    if (grids[g].querySelector("[data-grid-col-toggle]")) {
      prune(grids[g]);
      apply(grids[g]);
    }
  }
})();

/* ── controllers/grid-resize.js ── */
/*
 * HYPERPART: grid (extension)
 *
 * grid-resize — column resize, an OPTIONAL grid extension on the grid
 * primitive's seams (promoted from the Dazzle layer, 0.1.26 — Dazzle now
 * consumes it from here).
 *
 * Same idiom as the primitive: delegated document-level pointerdown; the
 * per-drag window listeners attach at drag start and detach at drag end
 * (the #795 teardown discipline — nothing leaks between drags). Widths live
 * on the table's `<col data-col>` elements + localStorage.
 *
 * Contract:
 *   - handle:  `[data-grid-resize="<key>"]` (a decorative span at the
 *              header's right edge; pointer-only — column width is
 *              presentational, so there is no keyboard path yet).
 *   - target:  `col[data-col="<key>"]` in the table's colgroup — resizing
 *              the col resizes the whole column (header + cells), and cols
 *              survive tbody-only swaps untouched.
 *   - width:   clamped 80..800px, snapped to an 8px grid (live during the
 *              drag), persisted as `localStorage["widths-<root.id>"]`
 *              ({key: px} — the key dzTable reserved for this feature).
 *   - state:   `data-resizing` on the root during a drag (CSS: col-resize
 *              cursor + selection off).
 *   - NB: the table keeps `table-layout: auto`, so a col width acts as a
 *              strong hint — content can still push a column wider than a
 *              too-small width. Honest trade-off; `fixed` would make widths
 *              exact but reflows every other column on the first drag.
 */
(function () {
  "use strict";

  var drag = null; // {root, key, startX, startWidth} — one drag at a time

  function storageKey(root) {
    return "widths-" + (root.id || "grid");
  }

  function readWidths(root) {
    try {
      var w = JSON.parse(localStorage.getItem(storageKey(root)) || "{}");
      return w && typeof w === "object" && !Array.isArray(w) ? w : {};
    } catch (e) {
      return {};
    }
  }

  function writeWidths(root, widths) {
    try {
      localStorage.setItem(storageKey(root), JSON.stringify(widths));
    } catch (e) {
      /* storage unavailable — resize still works, just doesn't persist */
    }
  }

  function colOf(root, key) {
    return root.querySelector('col[data-col="' + key + '"]');
  }

  function snapClamp(px) {
    return Math.round(Math.min(800, Math.max(80, px)) / 8) * 8;
  }

  function apply(root) {
    var widths = readWidths(root);
    for (var key in widths) {
      var col = colOf(root, key);
      if (col) col.style.width = widths[key] + "px";
    }
  }

  // Drop stored widths whose column no longer exists (the #853 analogue) —
  // skipped when no cols are present (not-yet-rendered table).
  function prune(root) {
    var cols = root.querySelectorAll("col[data-col]");
    if (!cols.length) return;
    var present = {};
    for (var i = 0; i < cols.length; i++) {
      present[cols[i].getAttribute("data-col")] = true;
    }
    var widths = readWidths(root);
    var cleaned = {};
    var dropped = false;
    for (var key in widths) {
      if (present[key]) cleaned[key] = widths[key];
      else dropped = true;
    }
    if (dropped) writeWidths(root, cleaned);
  }

  function onMove(evt) {
    if (!drag) return;
    var col = colOf(drag.root, drag.key);
    if (col) {
      col.style.width =
        snapClamp(drag.startWidth + (evt.clientX - drag.startX)) + "px";
    }
  }

  function onUp(evt) {
    if (!drag) return;
    var width = snapClamp(drag.startWidth + (evt.clientX - drag.startX));
    var col = colOf(drag.root, drag.key);
    if (col) col.style.width = width + "px";
    var widths = readWidths(drag.root);
    widths[drag.key] = width;
    writeWidths(drag.root, widths);
    drag.root.removeAttribute("data-resizing");
    document.body.style.cursor = "";
    drag = null;
    // #795: the window listeners live only for the drag.
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
  }

  document.addEventListener("pointerdown", function (evt) {
    var handle =
      evt.target &&
      evt.target.closest &&
      evt.target.closest("[data-grid-resize]");
    if (!handle) return;
    var root = handle.closest("[data-grid]");
    if (!root) return;
    var key = handle.getAttribute("data-grid-resize");
    var col = colOf(root, key);
    if (!col) return;
    // Baseline = the column's ACTUAL rendered width. col.offsetWidth reports
    // it correctly in Chromium + WebKit (verified empirically); the th-rect
    // fallback covers engines where col boxes don't report, and the 160
    // sentinel is unreachable in practice (the handle lives inside a th).
    var th = handle.closest("th");
    drag = {
      root: root,
      key: key,
      startX: evt.clientX,
      startWidth:
        col.offsetWidth ||
        parseInt(col.style.width, 10) ||
        (th ? Math.round(th.getBoundingClientRect().width) : 160),
    };
    root.setAttribute("data-resizing", "");
    document.body.style.cursor = "col-resize";
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    // A drag must not select text or start a sort click.
    evt.preventDefault();
    evt.stopPropagation();
  });

  // Re-apply after swaps: cols survive tbody-only swaps, but a full-page
  // history restore renders a fresh table. Both htmx event-name families.
  function onSwap() {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      if (grids[i].querySelector("[data-grid-resize]")) apply(grids[i]);
    }
  }
  document.addEventListener("htmx:after:swap", onSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onSwap); // htmx ≤2

  // Init: prune stale keys, then apply the stored widths.
  var grids = document.querySelectorAll("[data-grid]");
  for (var g = 0; g < grids.length; g++) {
    if (grids[g].querySelector("[data-grid-resize]")) {
      prune(grids[g]);
      apply(grids[g]);
    }
  }
})();

/* ── controllers/grid-edit.js ── */
/*
 * HYPERPART: grid (extension)
 *
 * grid-edit — inline cell editing, an OPTIONAL grid extension on the grid
 * primitive's seams (promoted from the Dazzle layer, 0.1.26 — Dazzle now
 * consumes it from here).
 *
 * The ratified seam design: the CELL owns its edit affordance; the grid
 * stays out of the way. One display span per editable cell carries the
 * contract; the controller builds the editor input on demand, and the typed
 * BUFFER lives on the grid root (`root._dzEdit`) — out of the morph path —
 * so an in-flight edit survives a tbody swap (poll refresh, re-sort): the
 * before-swap hook captures the input's live value, the after-swap hook
 * re-opens the editor on the (morph-keyed) row and restores the buffer.
 *
 * Contract:
 *   - root:   `[data-grid]` with `data-grid-edit-url` = the entity API
 *             base; commits PUT `{base}/{rowId}` with a single-field JSON
 *             body — the entity's STANDARD gated update route (permit +
 *             scope pre-read + destination-scope + schema validation).
 *   - cell:   `[data-grid-edit="<col>"]` (the display span) with
 *             `data-edit-kind` (text|date|bool|select),
 *             `data-edit-value` (the raw value), `data-edit-label`
 *             (a11y), and for selects `data-edit-options`
 *             (JSON [[value,label],…]).
 *   - open:   dblclick the span (dzTable parity; pointer-first — a keyboard
 *             entry point is tracked follow-up work).
 *   - keys:   Enter commits (text/date), Escape cancels, Tab / Shift-Tab
 *             commits then advances to the next/previous editable cell
 *             (wrapping to the adjacent row); bool/select commit on change.
 *   - state:  `is-saving` / `is-error` classes on the row (the same classes
 *             the Alpine `:class` bind used); a failed commit keeps the
 *             editor open with the server error in its `title`.
 *   - after a successful commit the controller fires `grid:refresh` on
 *             the tbody — the server re-renders rows, so rich display chrome
 *             (badges, dates) stays server-owned.
 */
(function () {
  "use strict";

  function rootOf(el) {
    return el.closest ? el.closest("[data-grid]") : null;
  }

  function cellSpan(root, rowId, colKey) {
    var row = root.querySelector('[data-row-id="' + rowId + '"]');
    return row && row.querySelector('[data-grid-edit="' + colKey + '"]');
  }

  function buildEditor(edit) {
    var el;
    if (edit.kind === "bool") {
      el = document.createElement("input");
      el.type = "checkbox";
      el.className = "inline-edit-checkbox";
      el.checked = edit.value === "true";
    } else if (edit.kind === "select") {
      el = document.createElement("select");
      el.className = "inline-edit-input inline-edit-select";
      var opts = [];
      try {
        opts = JSON.parse(edit.options || "[]");
      } catch (e) {
        opts = [];
      }
      for (var i = 0; i < opts.length; i++) {
        var o = document.createElement("option");
        o.value = String(opts[i][0]);
        o.textContent = String(opts[i][1]);
        if (String(opts[i][0]) === edit.value) o.selected = true;
        el.appendChild(o);
      }
    } else {
      el = document.createElement("input");
      el.type = edit.kind === "date" ? "date" : "text";
      el.className = "inline-edit-input";
      el.value = edit.value;
    }
    el.setAttribute("data-grid-editor", "");
    el.setAttribute("aria-label", "Edit " + (edit.label || edit.colKey));
    return el;
  }

  // Project the root's edit state into the DOM: hide the display span, put
  // the editor next to it, focus. Returns false when the target cell is gone
  // (e.g. the row was filtered away by the swap that interrupted the edit).
  function openEditor(root) {
    var edit = root._dzEdit;
    if (!edit) return false;
    var span = cellSpan(root, edit.rowId, edit.colKey);
    if (!span) return false;
    var editor = buildEditor(edit);
    span.style.display = "none";
    span.parentNode.insertBefore(editor, span.nextSibling);
    editor.focus();
    if (editor.select && edit.kind === "text") editor.select();
    return true;
  }

  function closeEditor(root) {
    var editor = root.querySelector("[data-grid-editor]");
    if (editor) {
      var span = editor.previousSibling;
      editor.parentNode.removeChild(editor);
      if (span && span.style) span.style.display = "";
    }
    root._dzEdit = null;
  }

  function editorValue(editor, kind) {
    return kind === "bool" ? String(editor.checked) : editor.value;
  }

  function rowOf(root, rowId) {
    return root.querySelector('[data-row-id="' + rowId + '"]');
  }

  // The row's editable columns, in DOM order — Tab-advance derives the ring
  // from the markup itself (no config list to drift).
  function editableKeys(root, rowId) {
    var row = rowOf(root, rowId);
    if (!row) return [];
    var spans = row.querySelectorAll("[data-grid-edit]");
    var keys = [];
    for (var i = 0; i < spans.length; i++) {
      keys.push(spans[i].getAttribute("data-grid-edit"));
    }
    return keys;
  }

  function nextEditable(root, rowId, colKey, direction) {
    var keys = editableKeys(root, rowId);
    var at = keys.indexOf(colKey);
    if (at < 0) return null;
    if (direction === "next" && at < keys.length - 1) {
      return { rowId: rowId, colKey: keys[at + 1] };
    }
    if (direction === "prev" && at > 0) {
      return { rowId: rowId, colKey: keys[at - 1] };
    }
    // Wrap to the adjacent row's first/last editable cell.
    var rows = root.querySelectorAll("[data-row-id]");
    var ids = [];
    for (var i = 0; i < rows.length; i++) {
      ids.push(rows[i].getAttribute("data-row-id"));
    }
    var rowAt = ids.indexOf(rowId);
    if (direction === "next" && rowAt >= 0 && rowAt < ids.length - 1) {
      var nk = editableKeys(root, ids[rowAt + 1]);
      return nk.length ? { rowId: ids[rowAt + 1], colKey: nk[0] } : null;
    }
    if (direction === "prev" && rowAt > 0) {
      var pk = editableKeys(root, ids[rowAt - 1]);
      return pk.length
        ? { rowId: ids[rowAt - 1], colKey: pk[pk.length - 1] }
        : null;
    }
    return null;
  }

  function startEdit(root, span) {
    if (root._dzEdit) closeEditor(root); // one edit at a time
    var row = span.closest("[data-row-id]");
    if (!row) return;
    root._dzEdit = {
      rowId: row.getAttribute("data-row-id"),
      colKey: span.getAttribute("data-grid-edit"),
      kind: span.getAttribute("data-edit-kind") || "text",
      value: span.getAttribute("data-edit-value") || "",
      label: span.getAttribute("data-edit-label") || "",
      options: span.getAttribute("data-edit-options") || "",
    };
    openEditor(root);
  }

  function commit(root, value, andThen) {
    var edit = root._dzEdit;
    if (!edit || edit.saving) return;
    edit.saving = true;
    var row = rowOf(root, edit.rowId);
    if (row) {
      row.classList.add("is-saving");
      row.classList.remove("is-error");
    }
    var base = root.getAttribute("data-grid-edit-url") || "";
    // Commit through the entity's STANDARD update route (PUT, all-optional
    // update schema + exclude_unset = partial update) with a single-field
    // JSON body — full RBAC (permit + scope pre-read + #1312 destination
    // scope), storage verification, and schema validation for free. (The old
    // dzTable posted a bespoke /field/ route that was never mounted.)
    var payload = {};
    payload[edit.colKey] = edit.kind === "bool" ? value === "true" : value;
    // Raw fetch bypasses csrf.js (which wires the token onto htmx requests
    // only), so echo the double-submit cookie here — without it the commit
    // 403s wherever the Sec-Fetch-Site origin gate is absent (Safari <16.4).
    var csrf =
      (document.cookie.match(/(?:^|; )dazzle_csrf=([^;]*)/) || [])[1] || "";
    var headers = { "Content-Type": "application/json" };
    if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf);
    fetch(base + "/" + encodeURIComponent(edit.rowId), {
      method: "PUT",
      headers: headers,
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (row) row.classList.remove("is-saving");
        if (!resp.ok) {
          return resp.text().then(function (text) {
            edit.saving = false;
            if (row) row.classList.add("is-error");
            var editor = root.querySelector("[data-grid-editor]");
            if (editor) editor.title = text || "Error " + resp.status;
            return;
          });
        }
        closeEditor(root);
        // Server-owned rendering: refresh the rows so badge/date chrome is
        // re-rendered rather than patched client-side.
        var body = root.querySelector("[data-grid-body]");
        if (body) {
          body.dispatchEvent(
            new CustomEvent("grid:refresh", { bubbles: true }),
          );
        }
        if (andThen) andThen();
      })
      .catch(function (err) {
        edit.saving = false;
        if (row) {
          row.classList.remove("is-saving");
          row.classList.add("is-error");
        }
        var editor = root.querySelector("[data-grid-editor]");
        if (editor) editor.title = (err && err.message) || "Network error";
      });
  }

  document.addEventListener("dblclick", function (evt) {
    var span =
      evt.target &&
      evt.target.closest &&
      evt.target.closest("[data-grid-edit]");
    if (!span) return;
    var root = rootOf(span);
    if (!root || !root.hasAttribute("data-grid-edit-url")) return;
    startEdit(root, span);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-grid-editor]")) return;
    var root = rootOf(t);
    if (!root || !root._dzEdit) return;
    var kind = root._dzEdit.kind;
    // bool / select / date commit on change (dzTable parity); text commits
    // on Enter/Tab so a blur-out mid-thought doesn't write.
    if (kind === "bool" || kind === "select" || kind === "date") {
      commit(root, editorValue(t, kind));
    }
  });

  document.addEventListener("keydown", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-grid-editor]")) return;
    var root = rootOf(t);
    if (!root || !root._dzEdit) return;
    var edit = root._dzEdit;
    if (evt.key === "Escape") {
      evt.preventDefault();
      closeEditor(root);
    } else if (evt.key === "Enter" && edit.kind !== "select") {
      evt.preventDefault();
      commit(root, editorValue(t, edit.kind));
    } else if (evt.key === "Tab") {
      evt.preventDefault();
      var target = nextEditable(
        root,
        edit.rowId,
        edit.colKey,
        evt.shiftKey ? "prev" : "next",
      );
      commit(root, editorValue(t, edit.kind), function () {
        if (!target) return;
        var span = cellSpan(root, target.rowId, target.colKey);
        if (span) startEdit(root, span);
      });
    }
  });

  // Morph safety: capture the live buffer before a swap replaces the editor,
  // re-project it after. If the row is gone (filtered away), the edit drops.
  function onBeforeSwap() {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      var edit = grids[i]._dzEdit;
      if (!edit) continue;
      var editor = grids[i].querySelector("[data-grid-editor]");
      if (editor) edit.value = editorValue(editor, edit.kind);
    }
  }
  document.addEventListener("htmx:before:swap", onBeforeSwap); // htmx 4
  document.addEventListener("htmx:beforeSwap", onBeforeSwap); // htmx ≤2

  function onAfterSwap() {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) {
      var edit = grids[i]._dzEdit;
      if (!edit || edit.saving) continue;
      // The swap destroyed the editor element; re-open on the morph-keyed
      // row with the captured buffer (or drop if the row vanished).
      var stale = grids[i].querySelector("[data-grid-editor]");
      if (stale) stale.parentNode.removeChild(stale);
      if (!openEditor(grids[i])) grids[i]._dzEdit = null;
    }
  }
  document.addEventListener("htmx:after:swap", onAfterSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onAfterSwap); // htmx ≤2
})();

/* ── controllers/app-shell.js ── */
/* HYPERPART: app-shell */
/*
 * app-shell — the shell's sidebar toggle + persistence controller
 * (promoted verbatim from Dazzle's alpine.js #1294 section; vanilla
 * and event-delegated — it never depended on Alpine).
 *
 * Contract:
 *   - root:    `.app-shell` carries `data-sidebar="open|closed"`
 *              (server-rendered initial state).
 *   - toggle:  `[data-sidebar-toggle]` (the topbar hamburger) flips the
 *              state and mirrors it to aria-expanded.
 *   - persist: the `dz_sidebar` cookie (1y) — a cookie, not localStorage,
 *              so the SERVER renders the correct state on first paint.
 */
// ── #1294 — App-shell sidebar toggle + persistence ──────────────────
// SSR emits `data-sidebar` on `.app-shell` (default "open") so the
// nav is reachable on first paint. This vanilla, event-delegated
// controller (a) reads the `dz_sidebar` cookie on load and applies it as
// a universal persistence fallback for render paths that default to
// "open", and (b) flips the state + writes the cookie when the topbar
// toggle is clicked. No Alpine dependency — survives HTMX swaps.
(function () {
  "use strict";
  var COOKIE = "dz_sidebar";
  var MAX_AGE = 60 * 60 * 24 * 365; // 1 year
  function shell() {
    return document.querySelector(".app-shell");
  }
  function readCookie() {
    var m = document.cookie.match(/(?:^|;\s*)dz_sidebar=(open|closed)\b/);
    return m ? m[1] : null;
  }
  function syncToggle(state) {
    var t = document.querySelector("[data-sidebar-toggle]");
    if (t) t.setAttribute("aria-expanded", state === "open" ? "true" : "false");
  }
  function apply(state) {
    var el = shell();
    if (!el) return;
    el.setAttribute("data-sidebar", state);
    syncToggle(state);
  }
  function init() {
    var el = shell();
    if (!el) return;
    var persisted = readCookie();
    if (persisted && persisted !== el.getAttribute("data-sidebar")) {
      apply(persisted);
    } else {
      syncToggle(el.getAttribute("data-sidebar") || "open");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("click", function (e) {
    var btn =
      e.target && e.target.closest
        ? e.target.closest("[data-sidebar-toggle]")
        : null;
    if (!btn) return;
    var el = shell();
    if (!el) return;
    var next =
      el.getAttribute("data-sidebar") === "open" ? "closed" : "open";
    apply(next);
    document.cookie =
      COOKIE + "=" + next + "; path=/; max-age=" + MAX_AGE + "; SameSite=Lax";
  });
})();

/* ── controllers/confirm-gate.js ── */
/* HYPERPART: confirm-panel */
/*
 * confirm-gate — the irreversible-action consent gate.
 *
 * Delegated from document; every `change` inside a `[data-confirm-gate]`
 * root recounts the checked REQUIRED boxes (`input[data-required="true"]`)
 * against `data-required-count` and arms/disarms the `.confirm-primary`
 * anchor. State lives entirely in the DOM: while disarmed the anchor carries
 * `aria-disabled="true"` and its destination stays parked in
 * `data-confirm-href`; arming promotes the href and drops aria-disabled.
 * A wholesale recount (never a +/- counter) means any real `change`
 * event self-heals the gate — including after an htmx morph (the SSR
 * markup arrives disarmed; the first user change recounts honestly).
 *
 * Zero required boxes = always armed — the server simply emits the anchor
 * with a live href and no aria-disabled, and this controller never fires
 * (no data-required inputs to change). Optional boxes never gate.
 *
 * Replaces the Alpine `dzConfirmGate` island (x-data + :href/:aria-disabled
 * bindings) per the HM Hyperpart idiom: delegated vanilla controller,
 * server-owned markup, no framework runtime.
 */
(function () {
  "use strict";

  document.addEventListener("change", function (evt) {
    var input = evt.target;
    if (!input || !input.matches || !input.matches('input[type="checkbox"]'))
      return;
    var root = input.closest("[data-confirm-gate]");
    if (!root) return;

    var declared = parseInt(
      root.getAttribute("data-required-count") || "0",
      10,
    );
    var required = root.querySelectorAll(
      'input[type="checkbox"][data-required="true"]',
    );
    var needed = declared > 0 ? declared : required.length;

    var ticked = 0;
    for (var i = 0; i < required.length; i++) if (required[i].checked) ticked++;

    var primary = root.querySelector(".confirm-primary");
    if (!primary) return;
    var href = primary.getAttribute("data-confirm-href");

    if (needed === 0 || ticked >= needed) {
      if (href) primary.setAttribute("href", href);
      primary.removeAttribute("aria-disabled");
    } else {
      primary.removeAttribute("href");
      primary.setAttribute("aria-disabled", "true");
    }
  });
})();

/* ── controllers/search-select.js ── */
/* HYPERPART: search-select */
/*
 * search-select — open/close for the typeahead combobox.
 *
 * Delegated from document; state lives in the DOM as `data-open` on
 * the `.search-select` ROOT (the CSS hides the results panel off the
 * attribute). The root — not the input — carries the state because the
 * select exchange OOB-replaces the input element (fragment_routes
 * `hx-swap-oob`), which would orphan any input-anchored state; nothing
 * ever swaps the root. `aria-expanded` on the combobox input is kept in
 * sync as the a11y mirror whenever the input still exists.
 *
 * Focus entering the input opens; focus leaving the widget closes after
 * a 200ms grace — result rows are htmx affordances (a click blurs the
 * input first), so an immediate close would hide the row before its
 * request fires. Re-focusing within the grace keeps it open.
 */
(function () {
  "use strict";

  function setOpen(root, open) {
    if (open) root.setAttribute("data-open", "true");
    else root.removeAttribute("data-open");
    var input = root.querySelector(".search-select-input");
    if (input) input.setAttribute("aria-expanded", open ? "true" : "false");
  }

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".search-select-input");
    if (!input) return;
    var root = input.closest(".search-select");
    if (root) setOpen(root, true);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".search-select-input");
    if (!input) return;
    var root = input.closest(".search-select");
    if (!root) return;
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      setOpen(root, false);
    }, 200);
  });
})();

/* ── controllers/money.js ── */
/* HYPERPART: money */
/*
 * money — major-unit money input with a hidden minor-unit carrier.
 *
 * Delegated from document; state lives in the DOM. The root
 * `[data-money]` carries the scale (`data-scale`, mutable when a
 * currency selector changes it); the visible decimal input is what the
 * user types; the hidden `*_minor` input is what the form posts. The
 * server precomputes the edit-mode display, so there is no init pass.
 *
 *   input  → hidden minor = round(major × 10^scale)
 *   blur   → normalize display to toFixed(scale); empty clears minor
 *   change (currency <select>) → scale = option's data-scale, prefix
 *            symbol = option's data-symbol, re-normalize
 *
 * Replaces the Alpine `dzMoney` island (x-model/x-init bindings).
 */
(function () {
  "use strict";

  function parts(el) {
    var root = el.closest && el.closest("[data-money]");
    if (!root) return null;
    return {
      root: root,
      scale: parseInt(root.getAttribute("data-scale") || "2", 10),
      display: root.querySelector('input[inputmode="decimal"]'),
      minor: root.querySelector('input[type="hidden"][name$="_minor"]'),
    };
  }

  function toMinor(val, scale) {
    var num = parseFloat(val);
    if (isNaN(num)) return 0;
    return Math.round(num * Math.pow(10, scale));
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p || evt.target !== p.display || !p.minor) return;
    p.minor.value = String(toMinor(p.display.value, p.scale));
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || evt.target !== p.display || !p.minor) return;
      if (!p.display.value.trim()) {
        p.minor.value = "";
        return;
      }
      var minor = toMinor(p.display.value, p.scale);
      p.minor.value = String(minor);
      p.display.value = (minor / Math.pow(10, p.scale)).toFixed(p.scale);
    },
    true, // blur doesn't bubble — capture
  );

  document.addEventListener("change", function (evt) {
    var sel = evt.target;
    if (!sel.matches || !sel.matches("[data-money] select")) return;
    var p = parts(sel);
    if (!p) return;
    var opt = sel.selectedOptions && sel.selectedOptions[0];
    if (opt && opt.dataset.scale !== undefined) {
      p.root.setAttribute("data-scale", opt.dataset.scale);
      p.scale = parseInt(opt.dataset.scale, 10);
    }
    var prefix = p.root.querySelector(".form-money-prefix");
    if (prefix && opt && opt.dataset.symbol)
      prefix.textContent = opt.dataset.symbol;
    if (p.display && p.display.value && p.minor) {
      var minor = toMinor(p.display.value, p.scale);
      p.minor.value = String(minor);
      p.display.value = (minor / Math.pow(10, p.scale)).toFixed(p.scale);
    }
  });
})();

/* ── controllers/wizard.js ── */
/* HYPERPART: wizard */
/*
 * wizard — multi-stage form navigation via the stepper.
 *
 * Delegated from document; state lives in the DOM: the `[data-wizard]`
 * root carries `data-step`, stages are `[data-stage]` blocks toggled
 * via the native `hidden` attribute, and each stepper item carries
 * `data-state="complete|current|pending"` (the completed checkmark is
 * pure CSS off that attribute) plus `is-active` on its circle/label/
 * connector for the visual trail.
 *
 * Navigation contract (ported from the dzWizard island, which was
 * production-dead — nothing mounted x-data after the Jinja teardown):
 * clicking a stepper item goes BACK freely; FORWARD only one step at a
 * time, and only when every required input in the current stage is valid
 * (reportValidity so the browser surfaces what's missing).
 */
(function () {
  "use strict";

  function stageValid(root, step) {
    var stage = root.querySelector('[data-stage="' + step + '"]');
    if (!stage) return true;
    var inputs = stage.querySelectorAll(
      "input[required], select[required], textarea[required]",
    );
    for (var i = 0; i < inputs.length; i++) {
      if (!inputs[i].checkValidity()) {
        inputs[i].reportValidity();
        return false;
      }
    }
    return true;
  }

  function render(root, step) {
    root.setAttribute("data-step", String(step));
    var stages = root.querySelectorAll("[data-stage]");
    for (var i = 0; i < stages.length; i++)
      stages[i].hidden =
        parseInt(stages[i].getAttribute("data-stage"), 10) !== step;
    var items = root.querySelectorAll("[data-step-to]");
    for (var j = 0; j < items.length; j++) {
      var idx = parseInt(items[j].getAttribute("data-step-to"), 10);
      var state = idx < step ? "complete" : idx === step ? "current" : "pending";
      // state + aria-current live on the <li> (the button's host item);
      // the button is the keyboard-operable trigger.
      var host = items[j].closest("li") || items[j];
      host.setAttribute("data-state", state);
      if (idx === step) host.setAttribute("aria-current", "step");
      else host.removeAttribute("aria-current");
      var active = idx <= step;
      var circle = host.querySelector(".form-stepper-circle");
      var label = host.querySelector(".form-stepper-label");
      var conn = host.querySelector(".form-stepper-connector");
      if (circle) circle.classList.toggle("is-active", active);
      if (label) label.classList.toggle("is-active", active);
      // the connector after item idx lights once the NEXT step is reached
      if (conn) conn.classList.toggle("is-active", idx < step);
      var sr = host.querySelector("[data-step-status]");
      if (sr) sr.textContent = state;
    }
  }

  // #1548: an early Submit with an invalid required field in a LATER
  // (hidden) stage must not be a silent no-op. The submit event never
  // fires in that case — the browser's constraint validation runs
  // FIRST and drops the submission because a hidden control is
  // unfocusable (console noise only). The reliable hook is the
  // `invalid` event, which fires per failing control during any
  // validation pass (native submit OR htmx's reportValidity): on the
  // first invalid control inside a HIDDEN wizard stage, jump the
  // wizard there and surface the bubble on the now-visible input.
  // Controls in the visible stage keep the native UI untouched.
  document.addEventListener(
    "invalid",
    function (evt) {
      var input = evt.target;
      if (!input || !input.closest) return;
      var root = input.closest("[data-wizard]");
      if (!root) return;
      var stage = input.closest("[data-stage]");
      if (!stage || !stage.hidden) return; // visible → native bubble is fine
      // One validation pass fires one invalid event PER failing
      // control — only the first may drive the jump, or a later
      // hidden stage would immediately steal the render.
      if (root.__dzWizardJumping) {
        evt.preventDefault();
        return;
      }
      root.__dzWizardJumping = true;
      setTimeout(function () {
        root.__dzWizardJumping = false;
      }, 0);
      evt.preventDefault(); // suppress the unfocusable-control drop
      render(root, parseInt(stage.getAttribute("data-stage"), 10));
      input.focus();
      input.reportValidity();
    },
    true,
  );

  document.addEventListener("click", function (evt) {
    var item = evt.target.closest && evt.target.closest("[data-step-to]");
    if (!item) return;
    var root = item.closest("[data-wizard]");
    if (!root) return;
    var target = parseInt(item.getAttribute("data-step-to"), 10);
    var current = parseInt(root.getAttribute("data-step") || "0", 10);
    if (target === current) return;
    if (target > current) {
      // forward: one step at a time, current stage must validate
      if (target !== current + 1 || !stageValid(root, current)) return;
    }
    render(root, target);
  });
})();

/* ── controllers/color.js ── */
/* HYPERPART: field */
/*
 * color — mirror a colour input's value into its hex readout.
 *
 * Delegated from document: `input` on `.form-color-input` writes the
 * value into the sibling `.form-color-hex` span. The server SSRs the
 * initial readout, so no init pass. Replaces the last Alpine straggler
 * (an inline `x-data { value }` scope on the colour group).
 */
(function () {
  "use strict";

  document.addEventListener("input", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".form-color-input");
    if (!input) return;
    var group = input.closest(".form-color-group");
    var hex = group && group.querySelector(".form-color-hex");
    if (hex) hex.textContent = input.value;
  });
})();

/* ── controllers/pdf.js ── */
/* HYPERPART: pdf */
/*
 * pdf — a progressively enhanced PDF viewing shell (the hx-pdf
 * primitive). The application renders the shell + controls access
 * (the server-side range proxy); PDF.js renders the document; this
 * controller glues them: lazy library load, toolbar wiring, page/zoom
 * state, URL deep-links, loading/error status.
 *
 * Mount: every `[data-pdf]` root at load + htmx settle (including
 * the swap target itself). The PDF.js library is NOT bundled — it
 * lazy-loads as an ES module from `data-pdf-lib` (+ optional
 * `data-pdf-worker`) only when the first viewer scrolls into view.
 *
 * Root attributes (the spec §7 contract, namespaced):
 *   data-pdf-src           bytes URL (the /_dazzle/documents proxy)
 *   data-pdf-lib           PDF.js module URL (required to enhance)
 *   data-pdf-worker        PDF.js worker URL
 *   data-pdf-initial-page  1-based start page
 *   data-pdf-state         "url" syncs ?dzpdf-page/?dzpdf-zoom via
 *                             replaceState; anything else keeps state
 *                             local (default)
 * Toolbar slots (wired when present, all optional):
 *   [data-pdf-prev] [data-pdf-next] [data-pdf-page]
 *   [data-pdf-page-count] [data-pdf-zoom-in] [data-pdf-zoom-out]
 *   [data-pdf-fit-width] [data-pdf-status] [data-pdf-viewer]
 *
 * No JS → the <noscript> download link inside the viewer region is the
 * whole experience (progressive enhancement, spec §2).
 */
(function () {
  "use strict";

  var libPromise = null;
  var live = [];

  function loadLib(root) {
    if (libPromise) return libPromise;
    var url = root.getAttribute("data-pdf-lib");
    if (!url) return Promise.reject(new Error("data-pdf-lib missing"));
    libPromise = import(url).then(function (mod) {
      var lib = mod.default || mod;
      var worker = root.getAttribute("data-pdf-worker");
      if (worker && lib.GlobalWorkerOptions)
        lib.GlobalWorkerOptions.workerSrc = worker;
      return lib;
    });
    return libPromise;
  }

  function q(root, slot) {
    return root.querySelector("[data-pdf-" + slot + "]");
  }

  function urlState() {
    var p = new URLSearchParams(location.search);
    return {
      page: parseInt(p.get("dzpdf-page") || "", 10) || null,
      zoom: p.get("dzpdf-zoom") || null,
    };
  }

  function writeUrlState(page, zoom) {
    var p = new URLSearchParams(location.search);
    p.set("dzpdf-page", String(page));
    p.set("dzpdf-zoom", String(zoom));
    // replaceState, never pushState: Back stays page navigation.
    history.replaceState(
      history.state,
      "",
      location.pathname + "?" + p + location.hash,
    );
  }

  async function boot(root) {
    var status = q(root, "status");
    var viewer = q(root, "viewer");
    var say = function (t) {
      if (status) status.textContent = t;
    };
    if (!viewer) return;
    try {
      say("Loading document…");
      var lib = await loadLib(root);
      var src = root.getAttribute("data-pdf-src");
      var doc = await lib.getDocument(src).promise;

      var syncUrl = root.getAttribute("data-pdf-state") === "url";
      var fromUrl = syncUrl ? urlState() : { page: null, zoom: null };
      var state = {
        page: Math.min(
          doc.numPages,
          Math.max(
            1,
            fromUrl.page ||
              parseInt(root.getAttribute("data-pdf-initial-page") || "1", 10) ||
              1,
          ),
        ),
        // zoom: a number, or "fit" (fit-width, the default)
        zoom: fromUrl.zoom || "fit",
      };

      var pageCount = q(root, "page-count");
      if (pageCount) pageCount.textContent = "of " + doc.numPages;
      var pageInput = q(root, "page");
      var gen = 0;

      async function render() {
        var g = ++gen;
        var page = await doc.getPage(state.page);
        var base = page.getViewport({ scale: 1 });
        var scale =
          state.zoom === "fit"
            ? Math.max(0.1, (viewer.clientWidth - 16) / base.width)
            : parseFloat(state.zoom) || 1;
        state.renderedScale = scale;
        var viewport = page.getViewport({ scale: scale });
        var canvas = document.createElement("canvas");
        var ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = Math.floor(viewport.width) + "px";
        canvas.style.height = Math.floor(viewport.height) + "px";
        var ctx = canvas.getContext("2d");
        ctx.scale(ratio, ratio);
        await page.render({ canvasContext: ctx, viewport: viewport }).promise;
        if (g !== gen) return; // a newer render superseded this one
        viewer.replaceChildren(canvas);
        if (pageInput) pageInput.value = String(state.page);
        if (syncUrl) writeUrlState(state.page, state.zoom);
        say("");
        root.setAttribute("data-pdf-ready", "true");
      }

      function go(page) {
        var target = Math.min(doc.numPages, Math.max(1, page || state.page));
        if (target === state.page) {
          // revert garbage typed into the page input
          if (pageInput) pageInput.value = String(state.page);
          return;
        }
        state.page = target;
        render();
      }

      function rezoom(factor) {
        // step from the scale the last render actually used — this is
        // how "fit" resolves to a number when the user starts zooming
        var current = state.renderedScale || 1;
        state.zoom = String(Math.min(8, Math.max(0.25, current * factor)));
        render();
      }

      root.addEventListener("click", function (e) {
        if (e.target.closest("[data-pdf-prev]")) go(state.page - 1);
        else if (e.target.closest("[data-pdf-next]")) go(state.page + 1);
        else if (e.target.closest("[data-pdf-zoom-in]")) rezoom(1.25);
        else if (e.target.closest("[data-pdf-zoom-out]")) rezoom(0.8);
        else if (e.target.closest("[data-pdf-fit-width]")) {
          state.zoom = "fit";
          render();
        }
      });
      if (pageInput)
        pageInput.addEventListener("change", function () {
          go(parseInt(pageInput.value, 10) || state.page);
        });

      // teardown for the mount sweep: swapping this viewer out must
      // release the PDF.js document (and its worker) — spec §7 cleanup.
      root._dzPdfCleanup = function () {
        gen++; // cancel any in-flight render
        try {
          doc.destroy();
        } catch (e) {
          /* already destroyed */
        }
      };

      await render();
    } catch (err) {
      say("Failed to load document.");
      root.setAttribute("data-pdf-error", "true");
    }
  }

  function mount(root) {
    if (root._dzPdfMounted) return;
    root._dzPdfMounted = true;
    live.push(root);
    if (!("IntersectionObserver" in window)) {
      boot(root);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          io.disconnect();
          boot(root);
          return;
        }
      }
    });
    io.observe(root);
  }

  function mountAll(scope) {
    // release documents whose viewer left the DOM (htmx swaps)
    for (var i = live.length - 1; i >= 0; i--) {
      if (!live[i].isConnected) {
        if (live[i]._dzPdfCleanup) live[i]._dzPdfCleanup();
        live.splice(i, 1);
      }
    }
    var host = scope || document;
    var roots = Array.prototype.slice.call(
      host.querySelectorAll("[data-pdf]"),
    );
    if (host.matches && host.matches("[data-pdf]")) roots.push(host);
    roots.forEach(mount);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountAll(document);
    });
  } else {
    mountAll(document);
  }
  function onSettle(e) {
    mountAll((e.detail && e.detail.target) || document);
  }
  // dual-bound for htmx 4 (colon) and htmx <=2 (camelCase) consumers —
  // the package convention (see grid.js).
  document.addEventListener("htmx:after:settle", onSettle);
  document.addEventListener("htmx:afterSettle", onSettle);
})();
