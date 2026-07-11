/* HYPERPART: search-select */
/*
 * dz-search-select — open/close for the typeahead combobox.
 *
 * Contract:
 *   - root: `[data-dz-widget="search_select"]` (class `dz-search-select`)
 *   - open:  runtime `data-dz-open` on the root (CSS hides results off it);
 *            not part of the static DOM_CONTRACT seed
 *
 * The root — not the input — carries open state because the select
 * exchange OOB-replaces the input (`hx-swap-oob`), which would orphan
 * input-anchored state. `aria-expanded` on the combobox input stays in
 * sync whenever the input still exists.
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

  function rootOf(el) {
    return (
      (el.closest && el.closest('[data-dz-widget="search_select"]')) ||
      (el.closest && el.closest(".dz-search-select"))
    );
  }

  document.addEventListener("focusin", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = rootOf(input);
    if (root) setOpen(root, true);
  });

  document.addEventListener("focusout", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-search-select-input");
    if (!input) return;
    var root = rootOf(input);
    if (!root) return;
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      setOpen(root, false);
    }, 200);
  });
})();
