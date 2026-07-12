/* HYPERPART: navigation-menu */
/*
 * dz-navigation-menu — exclusive-open + outside dismiss for native <details> panels.
 *
 * Contract:
 *   - root:  `[data-dz-navigation-menu]` (presentation: `.dz-navigation-menu`)
 *   - item:  `details.dz-navigation-menu__branch` (or bare `details` under root)
 *   - open:  one panel open at a time inside a root
 *   - dismiss: pointerdown outside root closes open panels; Escape same
 *
 * Native <details> allow multi-open and ignore outside clicks; product nav must not.
 * Progressive enhancement of the gallery partial.
 *
 * Dual-lock: contracts/navigation_menu.py (`data-dz-navigation-menu`).
 */
(function () {
  "use strict";

  var ROOT =
    "[data-dz-navigation-menu], .dz-navigation-menu, .navigation-menu, [data-navigation-menu]";
  var ITEM =
    "details.dz-navigation-menu__branch, details.navigation-menu__branch";

  function navRoot(el) {
    if (!el || !el.closest) return null;
    return el.closest(ROOT);
  }

  function isNavDetails(el) {
    if (!el || el.tagName !== "DETAILS") return false;
    if (!navRoot(el)) return false;
    // prefer classed branches; fall back to any details under a nav root
    if (el.matches && el.matches(ITEM)) return true;
    return !!navRoot(el);
  }

  function itemsIn(root) {
    var classed = root.querySelectorAll(ITEM);
    if (classed.length) return classed;
    return root.querySelectorAll("details");
  }

  function closeAllIn(root) {
    if (!root) return;
    var siblings = itemsIn(root);
    for (var i = 0; i < siblings.length; i++) {
      if (siblings[i].open) siblings[i].open = false;
    }
  }

  document.addEventListener(
    "toggle",
    function (evt) {
      var item = evt.target;
      if (!isNavDetails(item) || !item.open) return;
      var root = navRoot(item);
      if (!root) return;
      var siblings = itemsIn(root);
      for (var i = 0; i < siblings.length; i++) {
        if (siblings[i] !== item && siblings[i].open) {
          siblings[i].open = false;
        }
      }
    },
    true,
  );

  document.addEventListener(
    "pointerdown",
    function (evt) {
      var t = evt.target;
      var roots = document.querySelectorAll(ROOT);
      for (var i = 0; i < roots.length; i++) {
        var root = roots[i];
        var open = itemsIn(root);
        var any = false;
        for (var j = 0; j < open.length; j++) {
          if (open[j].open) {
            any = true;
            break;
          }
        }
        if (!any) continue;
        if (root.contains(t)) continue;
        closeAllIn(root);
      }
    },
    true,
  );

  document.addEventListener(
    "keydown",
    function (evt) {
      if (evt.key !== "Escape") return;
      var roots = document.querySelectorAll(ROOT);
      for (var i = 0; i < roots.length; i++) {
        closeAllIn(roots[i]);
      }
    },
    true,
  );
})();
