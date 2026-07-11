/* HYPERPART: master-detail */
/*
 * dz-master-detail — selection state for the master-detail composite.
 *
 * Contract:
 *   - root: `[data-dz-master-detail]` (class `dz-master-detail`)
 *   - list body: `[data-dz-master-detail-list-body]` (optional marker; Dazzle dual_pane)
 *   - detail body: `[data-dz-master-detail-detail-body]` (hx-get target pane marker)
 *   - item: `.dz-master-detail__item` — click sets aria-current within root
 *
 * The detail pane is loaded by htmx (item hx-get swaps a card into
 * .dz-master-detail__detail / [data-dz-master-detail-detail-body]); this
 * controller owns only selection state.
 *
 * INSTANCE-ISOLATED — delegated on `document`, every query scoped to the
 * clicked item's OWN `[data-dz-master-detail]` root so N instances stay
 * independent.
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var item = evt.target.closest(".dz-master-detail__item");
    if (!item) return;
    var root =
      item.closest("[data-dz-master-detail]") ||
      item.closest(".dz-master-detail");
    if (!root) return;
    // clear the previous selection WITHIN THIS root only, then mark this one
    var current = root.querySelectorAll(
      ".dz-master-detail__item[aria-current]",
    );
    for (var i = 0; i < current.length; i++) {
      current[i].removeAttribute("aria-current");
    }
    item.setAttribute("aria-current", "true");
  });
})();
