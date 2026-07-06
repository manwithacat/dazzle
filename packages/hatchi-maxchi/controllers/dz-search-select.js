/* HYPERPART: search-select */
/*
 * dz-search-select — open/close for the typeahead combobox.
 *
 * Delegated from document; state lives in the DOM as `data-dz-open` on
 * the `.dz-search-select` ROOT (the CSS hides the results panel off the
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
    if (open) root.setAttribute("data-dz-open", "true");
    else root.removeAttribute("data-dz-open");
    var input = root.querySelector(".dz-search-select-input");
    if (input) input.setAttribute("aria-expanded", open ? "true" : "false");
  }

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = input.closest(".dz-search-select");
    if (root) setOpen(root, true);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = input.closest(".dz-search-select");
    if (!root) return;
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      setOpen(root, false);
    }, 200);
  });
})();
