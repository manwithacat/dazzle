/** @ts-check */
/**
 * dz-toast.js — auto-dismiss bridge for OOB toasts.
 *
 * Replaces the htmx-2 `remove-me` extension (dropped in the htmx 4 migration).
 * The server emits toasts into `#dz-toast-container` via OOB swap with a
 * `data-dz-remove-after="5s"` attribute; this bridge schedules their removal.
 *
 * Scans on every `htmx:after:swap` (toasts arrive via OOB swap) and once at
 * load. Each element is scheduled at most once (`__dzRemoveScheduled` guard).
 * Zero dependencies. ~0.3 KB minified.
 */

(function () {
  "use strict";

  /** Parse an htmx-style timing string ("5s", "300ms", or bare seconds) to ms. */
  function parseDelayMs(value) {
    if (!value) return 5000;
    var m = String(value)
      .trim()
      .match(/^(\d+(?:\.\d+)?)\s*(ms|s)?$/);
    if (!m) return 5000;
    var n = parseFloat(m[1]);
    if (m[2] === "ms") return n;
    return n * 1000; // "s" or bare number → seconds
  }

  function schedule(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-dz-remove-after]").forEach(function (el) {
      if (el.__dzRemoveScheduled) return;
      el.__dzRemoveScheduled = true;
      setTimeout(
        function () {
          el.remove();
        },
        parseDelayMs(el.getAttribute("data-dz-remove-after")),
      );
    });
    // OOB toasts may land outside the swapped target — sweep the document too.
    if (scope !== document) {
      document
        .querySelectorAll("[data-dz-remove-after]")
        .forEach(function (el) {
          if (el.__dzRemoveScheduled) return;
          el.__dzRemoveScheduled = true;
          setTimeout(
            function () {
              el.remove();
            },
            parseDelayMs(el.getAttribute("data-dz-remove-after")),
          );
        });
    }
  }

  document.addEventListener("htmx:after:swap", function (e) {
    schedule(e && e.target);
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      schedule(document);
    });
  } else {
    schedule(document);
  }
})();
