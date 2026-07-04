/* HYPERPART: grid */
/*
 * dz-grid — the data-table controller. FIRST SLICE: row selection.
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
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    var clear = t && t.closest && t.closest("[data-dz-grid-clear]");
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
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) sync(grids[i]);
  });
})();
