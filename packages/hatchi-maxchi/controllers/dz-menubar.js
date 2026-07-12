/* HYPERPART: menubar */
/*
 * dz-menubar — exclusive-open + outside dismiss for native <details> items.
 *
 * Contract:
 *   - root:  `[data-dz-menubar]` (presentation: `.dz-menubar` / `.menubar`)
 *   - item:  `details.dz-menubar__item` or `details.menubar__item`
 *   - open:  one item open at a time inside a root
 *   - dismiss: pointerdown outside root closes all open items; Escape same
 *
 * Native <details> allow multiple open panels and ignore outside clicks;
 * app menubars must not. Progressive enhancement of the gallery partial.
 *
 * Dual-lock: contracts/menubar.py (`data-dz-menubar`).
 */
(function () {
  "use strict";

  var ITEM = "details.dz-menubar__item, details.menubar__item";
  var ROOT =
    "[data-dz-menubar], .dz-menubar, .menubar, [data-menubar]";

  function menubarRoot(el) {
    if (!el || !el.closest) return null;
    return el.closest(ROOT);
  }

  function isItem(el) {
    return el && el.matches && el.matches(ITEM);
  }

  function closeAllIn(root) {
    if (!root) return;
    var siblings = root.querySelectorAll(ITEM);
    for (var i = 0; i < siblings.length; i++) {
      if (siblings[i].open) siblings[i].open = false;
    }
  }

  document.addEventListener(
    "toggle",
    function (evt) {
      var item = evt.target;
      if (!isItem(item) || !item.open) return;
      var root = menubarRoot(item);
      if (!root) return;
      var siblings = root.querySelectorAll(ITEM);
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
        if (!root.querySelector(ITEM + "[open]")) continue;
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
