/* HYPERPART: menu */
/* HYPERPART: popover */
/*
 * dz-details-light-dismiss — Esc + outside pointer for single-root overlays.
 *
 * Contract (stem overlay-light-dismiss):
 *   - targets: details.dz-menu / details.menu, details.dz-popover / details.popover
 *   - Escape: close every open matching details
 *   - pointerdown outside an open details: close that details
 *   - does NOT handle menubar / navigation-menu (their controllers own exclusive
 *     multi-peer policy) or accordion/tree (in-flow structure — no light-dismiss)
 *
 * Native <details> only toggles via summary. Progressive enhancement so keyboard
 * and touch can abandon without re-finding the trigger.
 */
(function () {
  "use strict";

  var ROOT =
    "details.dz-menu, details.menu, details.dz-popover, details.popover";

  function openRoots() {
    return document.querySelectorAll(ROOT);
  }

  function closeOpen(exceptContains) {
    var nodes = openRoots();
    for (var i = 0; i < nodes.length; i++) {
      var d = nodes[i];
      if (!d.open) continue;
      if (exceptContains && d.contains(exceptContains)) continue;
      d.open = false;
    }
  }

  document.addEventListener(
    "keydown",
    function (evt) {
      if (evt.key !== "Escape") return;
      var nodes = openRoots();
      var any = false;
      for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].open) {
          nodes[i].open = false;
          any = true;
        }
      }
      // Allow other listeners (e.g. dialog) to run; we only clear details overlays.
      if (any) {
        /* no stopPropagation — command/dialog may also handle Escape */
      }
    },
    true,
  );

  document.addEventListener(
    "pointerdown",
    function (evt) {
      var t = evt.target;
      if (!t) return;
      closeOpen(t);
    },
    true,
  );
})();
