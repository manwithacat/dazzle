/**
 * pdf-viewer.js — bridge handler for the PDF detail-view component
 * (#942 cycle 1b; multi-panel support added in #943 cycle 5a).
 *
 * Mounts on `data-dz-widget="pdf-viewer"`. Listens for keyboard
 * shortcuts:
 *   - Esc → navigate to data-dz-back-url (or close the open panel
 *     first, if any — dialog-convention: one Esc closes, second
 *     Esc navigates back)
 *   - j or ArrowLeft → navigate to data-dz-prev-url (if set)
 *   - k or ArrowRight → navigate to data-dz-next-url (if set)
 *   - Each panel's `data-dz-panel-key` → toggle its panel
 *
 * Multi-panel exclusivity: opening one panel auto-closes the others.
 * Pressing the key of an already-open panel closes it (native
 * checkbox toggle behaviour).
 *
 * Keys are ignored when an editable element has focus (input,
 * textarea, contenteditable) so the shortcuts don't hijack form
 * input. Listener is attached to `document` and removed on unmount.
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
  // #942 cycle 2b / #943 cycle 5a — panel focus management.
  //
  // When a panel opens, move focus to its close button. Mark every
  // chrome band (header, footer, embed) AND every other panel as
  // `inert` so Tab stays inside the active panel. When the panel
  // closes, undo `inert` and restore focus to whichever element
  // had it before the panel opened.
  //
  // CSS-only show/hide via the adjacent-sibling combinator
  // (cycle 5a) is preserved — this layer only adds focus + inert
  // side effects, triggered by the toggle's native `change` event.
  // ---------------------------------------------------------------

  function setBackgroundInert(viewerEl, openPanelEl, inert) {
    var bands = viewerEl.querySelectorAll(
      ".dz-pdf-viewer-header, .dz-pdf-viewer-footer, .dz-pdf-viewer-embed",
    );
    for (var i = 0; i < bands.length; i++) {
      bands[i].inert = inert;
    }
    // #943 cycle 5a: also mark every OTHER panel as inert when one
    // opens. Without this, Tab from the open panel's close button
    // could land on a closed-but-still-in-DOM sibling panel's
    // contents (display:none isn't used here — visibility is
    // transform-based — so Tab order still includes them).
    var asides = viewerEl.querySelectorAll(".dz-pdf-viewer-panel");
    for (var j = 0; j < asides.length; j++) {
      if (asides[j] !== openPanelEl) {
        asides[j].inert = inert;
      } else {
        asides[j].inert = false;
      }
    }
  }

  function focusFirstInPanel(panelEl) {
    var closeBtn = panelEl.querySelector("[data-dz-panel-close]");
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

      // All panel toggles in render order. Cycle 2a's single-panel
      // case is just a length-1 list. Cycle 5a's multi-panel case
      // iterates the same way.
      var toggles = el.querySelectorAll(".dz-pdf-viewer-panel-toggle");

      // Captured at open time, restored at close time. Keyed by
      // toggle so successive open/close cycles each remember the
      // element that triggered them.
      var prevFocusByToggle = {};

      function panelForToggle(toggle) {
        // Adjacent-sibling combinator in CSS; mirror in JS by
        // reading the next element sibling.
        return toggle.nextElementSibling;
      }

      function closeOtherPanels(activeToggle) {
        for (var i = 0; i < toggles.length; i++) {
          var t = toggles[i];
          if (t !== activeToggle && t.checked) {
            t.checked = false;
            t.dispatchEvent(new Event("change"));
          }
        }
      }

      function makeOnToggleChange(toggle) {
        var name = toggle.getAttribute("data-dz-panel-name") || toggle.id;
        return function onToggleChange() {
          var panelEl = panelForToggle(toggle);
          if (toggle.checked) {
            // Exclusivity: close any other open panels.
            closeOtherPanels(toggle);
            prevFocusByToggle[name] = document.activeElement;
            setBackgroundInert(el, panelEl, true);
            if (panelEl) focusFirstInPanel(panelEl);
          } else {
            setBackgroundInert(el, null, false);
            var pf = prevFocusByToggle[name];
            if (pf && typeof pf.focus === "function") {
              pf.focus();
            }
            prevFocusByToggle[name] = null;
          }
        };
      }

      var toggleListeners = [];
      for (var i = 0; i < toggles.length; i++) {
        var listener = makeOnToggleChange(toggles[i]);
        toggles[i].addEventListener("change", listener);
        toggleListeners.push({ toggle: toggles[i], listener: listener });
      }

      // Close-button click handler — bridge clicks back to the
      // toggle for each panel. Each close button's parent <aside>
      // carries `data-dz-panel`, which matches the toggle's
      // `data-dz-panel-name`.
      function findToggleForCloseBtn(btn) {
        var aside = btn.closest(".dz-pdf-viewer-panel");
        if (!aside) return null;
        var name = aside.getAttribute("data-dz-panel");
        return el.querySelector(
          '.dz-pdf-viewer-panel-toggle[data-dz-panel-name="' + name + '"]',
        );
      }

      var closeBtns = el.querySelectorAll("[data-dz-panel-close]");
      var closeListeners = [];
      function makeOnCloseClick(btn) {
        return function onCloseClick() {
          var toggle = findToggleForCloseBtn(btn);
          if (toggle) {
            toggle.checked = false;
            toggle.dispatchEvent(new Event("change"));
          }
        };
      }
      for (var k = 0; k < closeBtns.length; k++) {
        var ccl = makeOnCloseClick(closeBtns[k]);
        closeBtns[k].addEventListener("click", ccl);
        closeListeners.push({ btn: closeBtns[k], listener: ccl });
      }

      function findOpenToggle() {
        for (var i = 0; i < toggles.length; i++) {
          if (toggles[i].checked) return toggles[i];
        }
        return null;
      }

      function findToggleByKey(key) {
        for (var i = 0; i < toggles.length; i++) {
          var k = toggles[i].getAttribute("data-dz-panel-key");
          // #943 cycle 5a: keys are case-insensitive (`p` matches
          // `P`) — same convention as the cycle 2a single-panel
          // handler that accepted both.
          if (k && (k === key || k.toLowerCase() === key.toLowerCase())) {
            return toggles[i];
          }
        }
        return null;
      }

      function handler(e) {
        if (isEditableTarget(e.target)) return;
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        if (e.key === "Escape") {
          // #942 cycle 2a / #943 cycle 5a: if any panel is open,
          // Esc closes it rather than navigating back. One Esc =
          // close; a second Esc (with all panels closed) = back.
          // Matches the dialog/modal convention users expect.
          var openToggle = findOpenToggle();
          if (openToggle) {
            e.preventDefault();
            openToggle.click();
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
        // Per-panel key dispatch. The cycle 2a single-panel case
        // registers `p` via `data-dz-panel-key="p"` on its toggle,
        // so this branch covers both shapes.
        if (e.key && e.key.length === 1) {
          var panelToggle = findToggleByKey(e.key);
          if (panelToggle) {
            e.preventDefault();
            panelToggle.click();
            return;
          }
        }
      }

      document.addEventListener("keydown", handler);
      return {
        handler: handler,
        toggleListeners: toggleListeners,
        closeListeners: closeListeners,
      };
    },

    unmount: function (_el, instance) {
      if (!instance) return;
      if (instance.handler) {
        document.removeEventListener("keydown", instance.handler);
      }
      if (instance.toggleListeners) {
        for (var i = 0; i < instance.toggleListeners.length; i++) {
          var tl = instance.toggleListeners[i];
          tl.toggle.removeEventListener("change", tl.listener);
        }
      }
      if (instance.closeListeners) {
        for (var j = 0; j < instance.closeListeners.length; j++) {
          var cl = instance.closeListeners[j];
          cl.btn.removeEventListener("click", cl.listener);
        }
      }
    },
  });
})();
