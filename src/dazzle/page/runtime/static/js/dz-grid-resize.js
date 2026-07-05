/*
 * dz-grid-resize — column resize, a DAZZLE EXTENSION on the HM grid
 * primitive's seams (convergence C2.2). Net-new as a REACHABLE feature: the
 * dzTable implementation existed but no production emitter ever rendered a
 * handle or a colgroup, so users never had it.
 *
 * Same idiom as the primitive: delegated document-level pointerdown; the
 * per-drag window listeners attach at drag start and detach at drag end
 * (the #795 teardown discipline — nothing leaks between drags). Widths live
 * on the table's `<col data-col>` elements + localStorage.
 *
 * Contract:
 *   - handle:  `[data-dz-grid-resize="<key>"]` (a decorative span at the
 *              header's right edge; pointer-only — column width is
 *              presentational, so there is no keyboard path yet).
 *   - target:  `col[data-col="<key>"]` in the table's colgroup — resizing
 *              the col resizes the whole column (header + cells), and cols
 *              survive tbody-only swaps untouched.
 *   - width:   clamped 80..800px, snapped to an 8px grid (live during the
 *              drag), persisted as `localStorage["dz-widths-<root.id>"]`
 *              ({key: px} — the key dzTable reserved for this feature).
 *   - state:   `data-dz-resizing` on the root during a drag (CSS: col-resize
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
    return "dz-widths-" + (root.id || "grid");
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
    drag.root.removeAttribute("data-dz-resizing");
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
      evt.target.closest("[data-dz-grid-resize]");
    if (!handle) return;
    var root = handle.closest("[data-dz-grid]");
    if (!root) return;
    var key = handle.getAttribute("data-dz-grid-resize");
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
    root.setAttribute("data-dz-resizing", "");
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
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      if (grids[i].querySelector("[data-dz-grid-resize]")) apply(grids[i]);
    }
  }
  document.addEventListener("htmx:after:swap", onSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onSwap); // htmx ≤2

  // Init: prune stale keys, then apply the stored widths.
  var grids = document.querySelectorAll("[data-dz-grid]");
  for (var g = 0; g < grids.length; g++) {
    if (grids[g].querySelector("[data-dz-grid-resize]")) {
      prune(grids[g]);
      apply(grids[g]);
    }
  }
})();
