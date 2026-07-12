/* HYPERPART: navigation-menu */
/*
 * dz-navigation-menu — exclusive-open across native <details> panels.
 *
 * Contract:
 *   - root:  `[data-dz-navigation-menu]` (presentation: `.dz-navigation-menu`)
 *   - item:  `details` descendants of the root (one panel per item)
 *   - open:  one panel open at a time inside a root
 *
 * Native <details> allow multiple open panels; product nav must not.
 * On `toggle` (capture), when a panel opens, close sibling details in the
 * same root. Progressive enhancement of the gallery partial.
 */
(function () {
  "use strict";

  function navRoot(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-navigation-menu]") ||
      el.closest(".dz-navigation-menu") ||
      el.closest(".navigation-menu") ||
      el.closest("[data-navigation-menu]")
    );
  }

  function isNavDetails(el) {
    if (!el || el.tagName !== "DETAILS") return false;
    return !!navRoot(el);
  }

  document.addEventListener(
    "toggle",
    function (evt) {
      var item = evt.target;
      if (!isNavDetails(item) || !item.open) return;
      var root = navRoot(item);
      if (!root) return;
      var siblings = root.querySelectorAll("details");
      for (var i = 0; i < siblings.length; i++) {
        if (siblings[i] !== item && siblings[i].open) {
          siblings[i].open = false;
        }
      }
    },
    true,
  );
})();
