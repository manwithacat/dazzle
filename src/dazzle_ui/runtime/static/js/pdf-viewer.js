/**
 * pdf-viewer.js — bridge handler for the PDF detail-view component
 * (#942 cycle 1b).
 *
 * Mounts on `data-dz-widget="pdf-viewer"`. Listens for keyboard
 * shortcuts:
 *   - Esc → navigate to data-dz-back-url
 *   - j or ArrowLeft → navigate to data-dz-prev-url (if set)
 *   - k or ArrowRight → navigate to data-dz-next-url (if set)
 *
 * Keys are ignored when an editable element has focus (input,
 * textarea, contenteditable) so the shortcuts don't hijack form
 * input. Listener is attached to `document` and removed on unmount
 * — same lifecycle the bridge uses for every other widget.
 *
 * Note: the wrapper element carries `data-dz-widget` only — NOT
 * `x-data`. The widget contract from #940 forbids co-locating both
 * on the same node, and the bridge assumes it owns the lifecycle of
 * any element it mounts.
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) {
    console.warn(
      "[dz-pdf-viewer] Bridge not found — skipping PDF viewer registration",
    );
    return;
  }

  function isEditableTarget(target) {
    if (!target) return false;
    var tag = target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (target.isContentEditable) return true;
    return false;
  }

  bridge.registerWidget("pdf-viewer", {
    mount: function (el) {
      function navigate(url) {
        if (url) {
          window.location.href = url;
        }
      }

      function handler(e) {
        if (isEditableTarget(e.target)) return;
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        if (e.key === "Escape") {
          e.preventDefault();
          navigate(el.getAttribute("data-dz-back-url"));
          return;
        }
        if (e.key === "j" || e.key === "ArrowLeft") {
          var prev = el.getAttribute("data-dz-prev-url");
          if (prev) {
            e.preventDefault();
            navigate(prev);
          }
          return;
        }
        if (e.key === "k" || e.key === "ArrowRight") {
          var next = el.getAttribute("data-dz-next-url");
          if (next) {
            e.preventDefault();
            navigate(next);
          }
          return;
        }
      }

      document.addEventListener("keydown", handler);
      return { handler: handler };
    },

    unmount: function (_el, instance) {
      if (instance && instance.handler) {
        document.removeEventListener("keydown", instance.handler);
      }
    },
  });
})();
