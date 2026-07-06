/** @ts-check */
/**
 * dz-toast.js — the toast bridge: auto-dismiss for server OOB toasts, plus
 * the CLIENT-initiated path.
 *
 * Auto-dismiss replaces the htmx-2 `remove-me` extension (dropped in the
 * htmx 4 migration). The server's `with_toast` OOB-prepends into the
 * shell's `#dz-toast` stack with `data-dz-remove-after="5s"`; this bridge
 * schedules the removal. Scans on every `htmx:after:swap` and once at load;
 * each element is scheduled at most once (`__dzRemoveScheduled` guard).
 *
 * Client path (C3 orphan sweep): `window.dz.toast()` fires a `toast` event
 * on the stack, and the optimistic-rollback path fires `showToast` on
 * `document.body` — both previously landed on the never-mounted `dzToast`
 * Alpine component, i.e. nowhere. This bridge renders them into `#dz-toast`
 * with server-parity markup, so one dismiss path + one CSS contract covers
 * both origins. Zero dependencies.
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

  /** Render a client-initiated toast with server-parity markup. */
  function clientToast(message, level) {
    var stack = document.getElementById("dz-toast");
    if (!stack || !message) return;
    var toast = document.createElement("div");
    toast.className = "dz-toast";
    toast.setAttribute("data-dz-toast-level", level || "info");
    toast.setAttribute("data-dz-remove-after", "5s");
    var span = document.createElement("span");
    span.textContent = String(message);
    toast.appendChild(span);
    stack.insertBefore(toast, stack.firstChild);
    schedule(stack);
  }

  // window.dz.toast(msg, type) dispatches `toast` ON the stack element,
  // WITHOUT bubbles — capture phase is the only way a document-level
  // listener sees it (capture visits ancestors on the way DOWN to the
  // target, no bubbling required).
  document.addEventListener(
    "toast",
    function (e) {
      var t = e && e.target;
      if (!t || !t.id || t.id !== "dz-toast") return;
      var d = e.detail || {};
      clientToast(d.message, d.type);
    },
    true,
  );
  // The optimistic-rollback path dispatches `showToast` on document.body
  // WITHOUT bubbles (htmx's HX-Trigger events do bubble) — capture phase
  // covers both, same reasoning as the `toast` listener above.
  document.addEventListener(
    "showToast",
    function (e) {
      var d = (e && e.detail) || {};
      clientToast(d.message, d.type);
    },
    true,
  );

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
