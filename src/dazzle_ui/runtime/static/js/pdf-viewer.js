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

  // ---------------------------------------------------------------
  // #942 cycle 2b — panel focus management.
  //
  // When the panel opens, move focus to the close button so screen-
  // reader and keyboard users know it appeared. Mark the rest of
  // the chrome as `inert` so Tab stays within the panel — without
  // this, Tab would land on the back link / nav / `<embed>` behind
  // the panel and the user would lose the visual context.
  //
  // When the panel closes, undo `inert` and restore focus to
  // whichever element had it before the panel opened (typically
  // the back link or the body, depending on what the user
  // pressed `p` from).
  //
  // CSS-only show/hide (cycle 2a's :has(:checked)) is preserved —
  // this layer only adds focus + inert side effects, triggered by
  // the toggle's native `change` event. Mouse users clicking the
  // close <label> trigger the same change event; keyboard users
  // get the same treatment via the `p`/Esc handlers.
  // ---------------------------------------------------------------

  function setBackgroundInert(viewerEl, inert) {
    var bands = viewerEl.querySelectorAll(
      ".dz-pdf-viewer-header, .dz-pdf-viewer-footer, .dz-pdf-viewer-embed",
    );
    for (var i = 0; i < bands.length; i++) {
      bands[i].inert = inert;
    }
  }

  function focusFirstInPanel(viewerEl) {
    var closeBtn = viewerEl.querySelector("[data-dz-panel-close]");
    if (closeBtn && typeof closeBtn.focus === "function") {
      closeBtn.focus();
    }
  }

  bridge.registerWidget("pdf-viewer", {
    mount: function (el) {
      function navigate(url) {
        if (url) {
          window.location.href = url;
        }
      }

      // Captured at open time, restored at close time. Reset each
      // time the panel toggles so successive open/close cycles
      // each remember their own caller.
      var prevFocus = null;

      var toggle = document.getElementById("dz-panel-toggle");
      function onToggleChange() {
        if (toggle.checked) {
          prevFocus = document.activeElement;
          setBackgroundInert(el, true);
          focusFirstInPanel(el);
        } else {
          setBackgroundInert(el, false);
          if (prevFocus && typeof prevFocus.focus === "function") {
            prevFocus.focus();
          }
          prevFocus = null;
        }
      }
      if (toggle) {
        toggle.addEventListener("change", onToggleChange);
      }

      // Close-button click handler — the button is `<button type="button">`
      // (not `<label for="dz-panel-toggle">`) so it's tabbable and
      // receives focus on panel open. JS bridges the click back to
      // the toggle: flip `checked` and dispatch `change` so the
      // focus-management listener above runs. Same code path the
      // keyboard `p` shortcut uses.
      var closeBtn = el.querySelector("[data-dz-panel-close]");
      function onCloseClick() {
        if (toggle) {
          toggle.checked = false;
          toggle.dispatchEvent(new Event("change"));
        }
      }
      if (closeBtn) {
        closeBtn.addEventListener("click", onCloseClick);
      }

      function handler(e) {
        if (isEditableTarget(e.target)) return;
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        if (e.key === "Escape") {
          // #942 cycle 2a: if the panel is open, Esc closes the
          // panel rather than navigating back. One Esc = close;
          // a second Esc (with panel now closed) = back. Matches
          // the dialog/modal convention users expect.
          var toggleEsc = document.getElementById("dz-panel-toggle");
          if (toggleEsc && toggleEsc.checked) {
            e.preventDefault();
            toggleEsc.click();
            return;
          }
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
        if (e.key === "p" || e.key === "P") {
          // #942 cycle 2a: toggle the right-side panel via the
          // hidden checkbox — CSS-only show/hide. No-op when no
          // panel is rendered (no checkbox in DOM).
          var togglePanel = document.getElementById("dz-panel-toggle");
          if (togglePanel) {
            e.preventDefault();
            togglePanel.click();
          }
          return;
        }
      }

      document.addEventListener("keydown", handler);
      return {
        handler: handler,
        toggleEl: toggle,
        toggleListener: onToggleChange,
        closeEl: closeBtn,
        closeListener: onCloseClick,
      };
    },

    unmount: function (_el, instance) {
      if (instance && instance.handler) {
        document.removeEventListener("keydown", instance.handler);
      }
      if (instance && instance.toggleEl && instance.toggleListener) {
        instance.toggleEl.removeEventListener(
          "change",
          instance.toggleListener,
        );
      }
      if (instance && instance.closeEl && instance.closeListener) {
        instance.closeEl.removeEventListener("click", instance.closeListener);
      }
    },
  });
})();
