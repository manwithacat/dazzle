/*
 * dz-grid-cols — column visibility, a DAZZLE EXTENSION on the HM grid
 * primitive's seams (convergence C2.1; replaces the dzTable Alpine
 * implementation, deleted in C3).
 *
 * Same idiom as the primitive: delegated document-level listeners, state in
 * the DOM + localStorage, no framework. The menu itself is a native
 * `<details>` disclosure (the HM `.dz-menu` idiom — no open/close JS).
 *
 * Contract:
 *   - root:    the `[data-dz-grid]` element; its `id` keys the persisted
 *              hidden set (`localStorage["dz-cols-<id>"]` — the SAME key the
 *              retired dzTable used, so users keep their saved preferences).
 *   - toggle:  `[data-dz-grid-col-toggle="<key>"]` (a checkbox in the menu);
 *              checked = visible. The controller syncs the boxes from
 *              storage at init and after every change.
 *   - cells:   every `[data-dz-col="<key>"]` th/td inside the root gets
 *              `style.display` applied — including rows hydrated later (the
 *              after-swap re-apply; hydrated cells carry no per-cell
 *              bindings).
 *   - prune:   stale stored keys that match no current column are dropped at
 *              init (#853 — otherwise a renamed column leaves invisible
 *              cells behind forever).
 */
(function () {
  "use strict";

  function storageKey(root) {
    return "dz-cols-" + (root.id || "grid");
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

  // Project the hidden set onto every [data-dz-col] cell + the menu boxes.
  function apply(root) {
    var hidden = readHidden(root);
    var cells = root.querySelectorAll("[data-dz-col]");
    for (var i = 0; i < cells.length; i++) {
      var key = cells[i].getAttribute("data-dz-col");
      cells[i].style.display = hidden.indexOf(key) >= 0 ? "none" : "";
    }
    var boxes = root.querySelectorAll("[data-dz-grid-col-toggle]");
    for (i = 0; i < boxes.length; i++) {
      boxes[i].checked =
        hidden.indexOf(boxes[i].getAttribute("data-dz-grid-col-toggle")) < 0;
    }
  }

  // #853: drop stored keys that match no current column — stale storage from
  // before a column rename would otherwise hide cells forever ("headers
  // render but cells are empty"). Skips the prune when NO columns are present
  // (empty-state / not-yet-hydrated renders must not wipe the preference).
  function prune(root) {
    var present = {};
    var cells = root.querySelectorAll("[data-dz-col]");
    if (!cells.length) return;
    for (var i = 0; i < cells.length; i++) {
      present[cells[i].getAttribute("data-dz-col")] = true;
    }
    var hidden = readHidden(root);
    var cleaned = [];
    for (i = 0; i < hidden.length; i++) {
      if (present[hidden[i]]) cleaned.push(hidden[i]);
    }
    if (cleaned.length !== hidden.length) writeHidden(root, cleaned);
  }

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-dz-grid-col-toggle]")) return;
    var root = t.closest("[data-dz-grid]");
    if (!root) return;
    var key = t.getAttribute("data-dz-grid-col-toggle");
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
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      if (grids[i].querySelector("[data-dz-grid-col-toggle]")) apply(grids[i]);
    }
  }
  document.addEventListener("htmx:after:swap", onSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onSwap); // htmx ≤2

  // Init: prune stale keys, then apply the stored preference.
  var grids = document.querySelectorAll("[data-dz-grid]");
  for (var g = 0; g < grids.length; g++) {
    if (grids[g].querySelector("[data-dz-grid-col-toggle]")) {
      prune(grids[g]);
      apply(grids[g]);
    }
  }
})();
