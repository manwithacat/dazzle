/*
 * HYPERPART: grid (extension)
 *
 * dz-grid-resize — column resize, an OPTIONAL grid extension on the grid
 * primitive's seams (promoted from the Dazzle layer, 0.1.26 — Dazzle now
 * consumes it from here).
 *
 * Same idiom as the primitive: delegated document-level pointerdown; the
 * per-drag window listeners attach at drag start and detach at drag end
 * (the #795 teardown discipline — nothing leaks between drags). Widths live
 * on the table's `<col data-dz-col>` elements + localStorage.
 *
 * Contract:
 *   - handle:  `[data-dz-grid-resize="<key>"]` at the header's right edge —
 *              a focusable window-splitter `role="separator"`: drag it, or
 *              Left/Right steps the width by STEP px and Home resets it.
 *              `aria-valuenow` follows the rendered width.
 *   - step:    `[data-dz-grid-width="<key>"][data-dz-step="-1|1"]` buttons
 *              (the Columns menu's Narrower / Wider) — the single-pointer
 *              alternative to the drag (#1842, WCAG 2.5.7). The result is
 *              announced in `[data-dz-grid-width-status]` when present.
 *   - target:  `col[data-dz-col="<key>"]` in the table's colgroup — resizing
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
  var STEP = 24; // px per keyboard / button step (three 8px snaps)

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
    return root.querySelector('col[data-dz-col="' + key + '"]');
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
    // A focusable separator must carry aria-valuenow from the start.
    var handles = root.querySelectorAll("[data-dz-grid-resize]");
    for (var i = 0; i < handles.length; i++) {
      syncValue(root, handles[i].getAttribute("data-dz-grid-resize"));
    }
  }

  // Drop stored widths whose column no longer exists (the #853 analogue) —
  // skipped when no cols are present (not-yet-rendered table).
  function prune(root) {
    var cols = root.querySelectorAll("col[data-dz-col]");
    if (!cols.length) return;
    var present = {};
    for (var i = 0; i < cols.length; i++) {
      present[cols[i].getAttribute("data-dz-col")] = true;
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

  function handleOf(root, key) {
    return root.querySelector('[data-dz-grid-resize="' + key + '"]');
  }

  // The column's ACTUAL rendered width. col.offsetWidth reports it in
  // Chromium + WebKit; the th-rect fallback covers engines where col boxes
  // don't report, and 160 is unreachable in practice.
  function widthOf(root, key) {
    var col = colOf(root, key);
    if (!col) return 0;
    var handle = handleOf(root, key);
    var th = handle && handle.closest("th");
    return (
      col.offsetWidth ||
      parseInt(col.style.width, 10) ||
      (th ? Math.round(th.getBoundingClientRect().width) : 160)
    );
  }

  // The separator's value range is set here, not in the markup: the Nu
  // validator HM CI pins predates ARIA 1.2's focusable-separator values.
  function syncValue(root, key) {
    var handle = handleOf(root, key);
    if (!handle) return;
    handle.setAttribute("aria-valuemin", "80");
    handle.setAttribute("aria-valuemax", "800");
    handle.setAttribute("aria-valuenow", String(widthOf(root, key)));
  }

  function setWidth(root, key, px) {
    var col = colOf(root, key);
    if (!col) return;
    var width = snapClamp(px);
    col.style.width = width + "px";
    var widths = readWidths(root);
    widths[key] = width;
    writeWidths(root, widths);
    syncValue(root, key);
  }

  function resetWidth(root, key) {
    var col = colOf(root, key);
    if (!col) return;
    col.style.width = "";
    var widths = readWidths(root);
    delete widths[key];
    writeWidths(root, widths);
    syncValue(root, key);
  }

  // "<Label> column width 184 pixels" — the label is the button's group name.
  function announce(root, btn, key) {
    var status = root.querySelector("[data-dz-grid-width-status]");
    if (!status) return;
    var group = btn.closest("[role=group]");
    var label = (group && group.getAttribute("aria-label")) || key;
    status.textContent = label + " " + widthOf(root, key) + " pixels";
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
    setWidth(drag.root, drag.key, drag.startWidth + (evt.clientX - drag.startX));
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
    if (!colOf(root, key)) return;
    drag = {
      root: root,
      key: key,
      startX: evt.clientX,
      startWidth: widthOf(root, key),
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

  // Keyboard: the handle is a window-splitter separator.
  document.addEventListener("keydown", function (evt) {
    var handle =
      evt.target && evt.target.matches && evt.target.matches("[data-dz-grid-resize]")
        ? evt.target
        : null;
    if (!handle) return;
    var root = handle.closest("[data-dz-grid]");
    if (!root) return;
    var key = handle.getAttribute("data-dz-grid-resize");
    if (evt.key === "ArrowLeft" || evt.key === "ArrowRight") {
      setWidth(root, key, widthOf(root, key) + (evt.key === "ArrowRight" ? STEP : -STEP));
    } else if (evt.key === "Home") {
      resetWidth(root, key);
    } else {
      return;
    }
    // Never a sort keypress or a page scroll.
    evt.preventDefault();
    evt.stopPropagation();
  });

  document.addEventListener("focusin", function (evt) {
    var handle =
      evt.target && evt.target.matches && evt.target.matches("[data-dz-grid-resize]")
        ? evt.target
        : null;
    var root = handle && handle.closest("[data-dz-grid]");
    if (root) syncValue(root, handle.getAttribute("data-dz-grid-resize"));
  });

  // Single pointer (#1842): the Columns menu's Narrower / Wider buttons.
  document.addEventListener("click", function (evt) {
    var btn =
      evt.target && evt.target.closest && evt.target.closest("[data-dz-grid-width]");
    if (!btn) return;
    var root = btn.closest("[data-dz-grid]");
    if (!root) return;
    var key = btn.getAttribute("data-dz-grid-width");
    if (!colOf(root, key)) return;
    var dir = Number(btn.getAttribute("data-dz-step")) < 0 ? -1 : 1;
    setWidth(root, key, widthOf(root, key) + dir * STEP);
    announce(root, btn, key);
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
