/* HYPERPART: menubar */
/*
 * dz-menubar — exclusive-open across native <details> items.
 *
 * Contract:
 *   - root:  `[data-dz-menubar]` (presentation: `.dz-menubar` / `.menubar`)
 *   - item:  `details.dz-menubar__item` or `details.menubar__item`
 *   - open:  one item open at a time inside a root
 *
 * Native <details> allow multiple open panels; app menubars must not.
 * On `toggle` (capture), when an item opens, close sibling items in the
 * same root. No framework dependency — progressive enhancement of the
 * gallery partial.
 */
(function () {
  "use strict";

  var ITEM = "details.dz-menubar__item, details.menubar__item";

  function menubarRoot(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-menubar]") ||
      el.closest(".dz-menubar") ||
      el.closest(".menubar")
    );
  }

  function isItem(el) {
    return el && el.matches && el.matches(ITEM);
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
})();
