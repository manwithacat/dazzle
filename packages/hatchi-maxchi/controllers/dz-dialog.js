/* HYPERPART: dialog */
/*
 * dz-dialog — open a native <dialog> from a delegated trigger.
 *
 * The ONLY behaviour that isn't native: a [data-dz-dialog-open="id"]
 * click calls showModal() on the <dialog id="id"> it names. Close, focus
 * trapping, the inert background and the backdrop tap are all the
 * platform's own (the dialog's <form method="dialog"> buttons + Esc +
 * closedby="any").
 *
 * INSTANCE-ISOLATED — one delegated listener, but the trigger addresses
 * its OWN dialog by id (getElementById), so N dialogs coexist without a
 * shared global handle (contrast dz-command.js's page-level singleton).
 *
 * open timing: showModal is deferred with setTimeout(0) so the opening
 * click is not also treated as a light-dismiss on closedby="any" (a
 * microtask is still too early in Chromium — open-and-instantly-close).
 *
 * initial focus: showModal focuses the first focusable — often header
 * chrome (✕, Expand, …). WebKit paints that as :focus-visible after a
 * pointer open ("looks active"). UA focus assignment can land *after*
 * showModal returns, so a single settle is a race. We settle immediately
 * and again on rAF / short timeout. Prefer [autofocus], else the scrollable
 * body (tabindex=0), else the dialog shell — never leave focus on header
 * chrome. Closing focus settle with "only when active is .drawer__close"
 * failed as soon as Expand became first focusable.
 *
 * panel width: Expand / Restore is a 2-state toggle (resting width ↔ xl),
 * not a multi-step cycle. Labels always name the next action. Separate
 * from "Open full page" (navigation).
 */
(function () {
  "use strict";

  var REST_WIDTH = "md";
  var EXPANDED_WIDTH = "xl";
  /* Both dual-lock and gallery dialects — apply_prefix collapses data-dz-* ↔ data-* */
  var EXPAND_SEL =
    "[data-dz-drawer-expand], [data-drawer-expand], " +
    "[data-dz-drawer-widen], [data-drawer-widen]";
  var HEADER_SEL =
    ".dz-drawer__header, .drawer__header, .dz-dialog__header, .dialog__header";
  var BODY_SEL =
    ".dz-drawer__body, .drawer__body, .dz-dialog__body, .dialog__body";

  function openAttr(el) {
    return (
      el.getAttribute("data-dz-dialog-open") || el.getAttribute("data-dialog-open")
    );
  }

  function focusQuiet(el) {
    if (!el || typeof el.focus !== "function") return;
    try {
      el.focus({ preventScroll: true, focusVisible: false });
    } catch (e1) {
      try {
        el.focus({ preventScroll: true });
      } catch (e2) {
        /* ignore */
      }
    }
  }

  function isHeaderChrome(el, dlg) {
    if (!el || !dlg || !dlg.contains(el) || el === dlg) return false;
    var header = dlg.querySelector(HEADER_SEL);
    return !!(header && header.contains(el));
  }

  /**
   * After pointer-driven showModal: never leave focus on header chrome.
   * Honour [autofocus]; else scrollable body; else dialog shell.
   * Blur chrome first so sticky :focus-visible cannot linger on Expand/✕.
   */
  function settleInitialFocus(dlg) {
    if (!dlg || !dlg.open) return;

    var auto = dlg.querySelector("[autofocus]");
    if (auto) {
      if (document.activeElement && document.activeElement !== auto) {
        try {
          document.activeElement.blur();
        } catch (e0) {
          /* ignore */
        }
      }
      focusQuiet(auto);
      return;
    }

    var active = document.activeElement;
    // Meaningful focus already inside body (field, etc.) — leave it.
    if (
      active &&
      dlg.contains(active) &&
      active !== dlg &&
      !isHeaderChrome(active, dlg)
    ) {
      return;
    }

    var body = dlg.querySelector(BODY_SEL);
    var target = body || dlg;
    if (target === dlg && !dlg.hasAttribute("tabindex")) {
      dlg.setAttribute("tabindex", "-1");
    }
    if (active && dlg.contains(active) && active !== target) {
      try {
        active.blur();
      } catch (e1) {
        /* ignore */
      }
    }
    focusQuiet(target);
  }

  /** UA may assign first-focusable after showModal returns — re-settle. */
  function settleInitialFocusSoon(dlg) {
    settleInitialFocus(dlg);
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(function () {
        settleInitialFocus(dlg);
        requestAnimationFrame(function () {
          settleInitialFocus(dlg);
        });
      });
    }
    setTimeout(function () {
      settleInitialFocus(dlg);
    }, 0);
    setTimeout(function () {
      settleInitialFocus(dlg);
    }, 50);
  }

  function widthAttr(dlg) {
    return (
      dlg.getAttribute("data-dz-width") ||
      dlg.getAttribute("data-width") ||
      REST_WIDTH
    );
  }

  function setWidth(dlg, w) {
    // Always write both dialects so CSS (prefixed or gallery) matches regardless
    // of which attr the stylesheet retained after apply_prefix.
    dlg.setAttribute("data-dz-width", w);
    dlg.setAttribute("data-width", w);
  }

  function isExpandedWidth(w) {
    return w === EXPANDED_WIDTH || w === "full";
  }

  function expandControls(dlg) {
    return dlg.querySelectorAll(EXPAND_SEL);
  }

  /** Label always describes the *next* action. */
  function syncExpandControl(btn, expanded) {
    if (!btn) return;
    btn.setAttribute("aria-pressed", expanded ? "true" : "false");
    btn.setAttribute(
      "aria-label",
      expanded ? "Restore drawer panel to default width" : "Expand drawer panel"
    );
    if (!btn.querySelector("svg, img, .icon, .dz-icon")) {
      btn.textContent = expanded ? "Restore" : "Expand";
    }
  }

  function syncExpandControls(dlg) {
    var expanded = isExpandedWidth(widthAttr(dlg));
    var btns = expandControls(dlg);
    for (var i = 0; i < btns.length; i++) {
      syncExpandControl(btns[i], expanded);
    }
  }

  function toggleExpand(dlg) {
    var cur = widthAttr(dlg);
    if (isExpandedWidth(cur)) {
      var rest =
        dlg.getAttribute("data-dz-width-rest") ||
        dlg.getAttribute("data-width-rest") ||
        REST_WIDTH;
      setWidth(dlg, rest);
    } else {
      dlg.setAttribute("data-dz-width-rest", cur);
      dlg.setAttribute("data-width-rest", cur);
      setWidth(dlg, EXPANDED_WIDTH);
    }
    syncExpandControls(dlg);
  }

  function drawerHost(el) {
    return (
      (el.closest && el.closest("dialog.dz-drawer")) ||
      (el.closest && el.closest("dialog.drawer"))
    );
  }

  document.addEventListener("click", function (evt) {
    var expandBtn = evt.target.closest && evt.target.closest(EXPAND_SEL);
    if (expandBtn) {
      var host = drawerHost(expandBtn);
      if (!host) return;
      evt.preventDefault();
      evt.stopPropagation();
      toggleExpand(host);
      // Keep focus on the control after intentional activate (keyboard users),
      // but clear the false "active on open" path is separate (open settle).
      return;
    }

    var trigger =
      (evt.target.closest && evt.target.closest("[data-dz-dialog-open]")) ||
      (evt.target.closest && evt.target.closest("[data-dialog-open]"));
    if (!trigger) return;
    var id = openAttr(trigger);
    if (!id) return;
    var dlg = document.getElementById(id);
    if (!dlg || typeof dlg.showModal !== "function") return;
    evt.preventDefault();
    // Macrotask: past closedby="any" handling for this click.
    setTimeout(function () {
      if (!dlg.open) dlg.showModal();
      syncExpandControls(dlg);
      settleInitialFocusSoon(dlg);
    }, 0);
  });
})();
