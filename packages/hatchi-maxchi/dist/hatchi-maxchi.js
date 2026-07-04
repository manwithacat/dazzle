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

  // Reset selection whenever htmx swaps new results in.
  document.addEventListener("htmx:afterSwap", function (evt) {
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
  });

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

    var tabs = root.querySelectorAll(".tabs__tab");
    for (var i = 0; i < tabs.length; i++)
      tabs[i].removeAttribute("aria-current");
    tab.setAttribute("aria-current", "true");

    var panels = root.querySelectorAll(".tabs__panel");
    for (var j = 0; j < panels.length; j++) panels[j].hidden = true;

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
 * grid — the data-table controller. Slices: selection + sort + filter + search.
 *
 * Delegated + state-in-DOM, the HM idiom (same shape as tabs.js): one pair
 * of document-level listeners, everything scoped to the clicked control's own
 * `[data-grid]` root via `closest()`, so N grids on a page stay independent.
 * There is NO framework and NO reactive scope — the primary selection state is
 * each checkbox's own `.checked`, which idiomorph preserves in place across a
 * tbody swap (the exact thing Alpine's reactive scope did NOT survive). The
 * *derived* state — the root's `data-bulk-count`, the summary text, and the
 * select-all tri-state — is a projection of those checkboxes, so it is
 * recomputed on every `change`/`click` AND re-synced after any `htmx:afterSwap`
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
 *                  `page`, `page_size` are reserved query keys — don't use them
 *                  as a `data-grid-filter` value.
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
    // `.table:not([data-bulk-count="0"]) .bulk-actions { display:flex }`.
    root.setAttribute("data-bulk-count", String(checked));
    var target = root.querySelector("[data-bulk-count-target]");
    if (target) target.textContent = String(checked);
    var all = root.querySelector("[data-grid-select-all]");
    if (all) {
      all.checked = checked > 0 && checked === boxes.length;
      all.indeterminate = checked > 0 && checked < boxes.length;
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

  // Rebuild the tbody's request query from ALL current DOM state — the search
  // box, the active sort, AND every filter select — so search / sort / filter
  // COMPOSE, then ask the server (via `grid:refresh`) for the matching,
  // ordered rows.
  function refresh(root) {
    var body = root.querySelector("[data-grid-body]");
    if (!body) return;
    var base = (
      body.getAttribute("data-grid-src") ||
      body.getAttribute("hx-get") ||
      ""
    ).split("?")[0];
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
    // Search / sort / filter reset pagination to page 1 (spec) — a no-op until
    // the pagination slice adds page state; the reset lands there.
    body.setAttribute("hx-get", base + (q.length ? "?" + q.join("&") : ""));
    body.dispatchEvent(new CustomEvent("grid:refresh", { bubbles: true }));
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
    refresh(root); // reads the sort we just wrote + any active filters
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
      refresh(root);
    }, ms);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-grid-select]")) {
      var r = gridOf(t);
      if (r) sync(r);
    } else if (t.matches("[data-grid-select-all]")) {
      var root = gridOf(t);
      if (!root) return;
      var boxes = rowBoxes(root);
      for (var i = 0; i < boxes.length; i++) boxes[i].checked = t.checked;
      sync(root);
    } else if (t.matches("[data-grid-filter]")) {
      // A filter select changed → rebuild the query (composing with any active
      // sort) and reload the rows from the server.
      var fr = gridOf(t);
      if (fr) refresh(fr);
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    var sortBtn = t.closest("[data-grid-sort]");
    if (sortBtn) {
      var sroot = gridOf(sortBtn);
      if (sroot) {
        evt.preventDefault();
        applySort(sroot, sortBtn);
      }
      return;
    }
    var clear = t.closest("[data-grid-clear]");
    if (!clear) return;
    var root = gridOf(clear);
    if (!root) return;
    var boxes = rowBoxes(root);
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
    sync(root);
  });

  // A tbody swap changes the row set: idiomorph preserves each checkbox's
  // `.checked` in place, but the derived count / bar / select-all must be
  // rebuilt from the surviving boxes — else the root could say "2 selected"
  // after those 2 rows were swapped out. Re-sync every grid on the page (cheap;
  // no-op where nothing changed). Harmless if htmx never fires this event.
  document.addEventListener("htmx:afterSwap", function () {
    var grids = document.querySelectorAll("[data-grid]");
    for (var i = 0; i < grids.length; i++) sync(grids[i]);
  });
})();
