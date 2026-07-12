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
 * initial focus: showModal focuses the first focusable in the dialog —
 * often header chrome (✕ close, Expand, …). WebKit paints that as
 * :focus-visible after a pointer open, so the control looks "active"
 * until the user clicks away. After open we ALWAYS settle focus on
 * [autofocus] if present, else the dialog shell (tabindex=-1, outline
 * suppressed in CSS) so *any* chrome control is not lit until the user
 * Tabs. Do not special-case only close — a later header button becomes
 * first focusable and reintroduces the same bug. Esc / focus trap still
 * work — focus remains inside the dialog.
 *
 * panel width: Expand / Restore is a 2-state toggle (resting width ↔ xl),
 * not a multi-step cycle. A unipolar "Widen" cycle lied on the last press
 * (reset to default). Labels always name the next action. Separate job
 * from "Open full page" (navigation to an owned URL).
 */
(function () {
  "use strict";

  var REST_WIDTH = "md";
  var EXPANDED_WIDTH = "xl";
  var EXPAND_SEL =
    "[data-dz-drawer-expand], [data-drawer-expand], " +
    "[data-dz-drawer-widen], [data-drawer-widen]";

  function openAttr(el) {
    return (
      el.getAttribute("data-dz-dialog-open") || el.getAttribute("data-dialog-open")
    );
  }

  function focusQuiet(el) {
    if (!el || typeof el.focus !== "function") return;
    try {
      // focusVisible: false when supported — no ring on programmatic settle
      el.focus({ preventScroll: true, focusVisible: false });
    } catch (e1) {
      try {
        el.focus({ preventScroll: true });
      } catch (e2) {
        /* ignore */
      }
    }
  }

  /**
   * After pointer-driven showModal: never leave focus on header chrome.
   * Honour [autofocus]; otherwise hold focus on the dialog shell.
   */
  function settleInitialFocus(dlg) {
    var auto = dlg.querySelector("[autofocus]");
    if (auto) {
      focusQuiet(auto);
      return;
    }
    if (!dlg.hasAttribute("tabindex")) {
      dlg.setAttribute("tabindex", "-1");
    }
    focusQuiet(dlg);
  }

  function widthAttr(dlg) {
    return dlg.getAttribute("data-dz-width") || dlg.getAttribute("data-width") || REST_WIDTH;
  }

  function setWidth(dlg, w) {
    dlg.setAttribute("data-dz-width", w);
    dlg.setAttribute("data-width", w); // gallery unprefixed dialect
  }

  function isExpandedWidth(w) {
    return w === EXPANDED_WIDTH || w === "full";
  }

  function expandControls(dlg) {
    return dlg.querySelectorAll(EXPAND_SEL);
  }

  /** Label always describes the *next* action (honest after multi-state cycle). */
  function syncExpandControl(btn, expanded) {
    if (!btn) return;
    btn.setAttribute("aria-pressed", expanded ? "true" : "false");
    btn.setAttribute(
      "aria-label",
      expanded ? "Restore drawer panel to default width" : "Expand drawer panel"
    );
    // Text-only chrome (gallery); leave icon-only buttons to aria-label alone.
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
      // Remember resting width so Restore returns to author default (sm/md/lg).
      dlg.setAttribute("data-dz-width-rest", cur);
      dlg.setAttribute("data-width-rest", cur);
      setWidth(dlg, EXPANDED_WIDTH);
    }
    syncExpandControls(dlg);
  }

  document.addEventListener("click", function (evt) {
    var expandBtn =
      evt.target.closest && evt.target.closest(EXPAND_SEL);
    if (expandBtn) {
      var host =
        expandBtn.closest("dialog.dz-drawer") || expandBtn.closest("dialog.drawer");
      if (!host) return;
      evt.preventDefault();
      toggleExpand(host);
      return;
    }

    var trigger =
      (evt.target.closest && evt.target.closest("[data-dz-dialog-open]")) ||
      (evt.target.closest && evt.target.closest("[data-dialog-open]"));
    if (!trigger) return;
    var id = openAttr(trigger);
    if (!id) return;
    var dlg = document.getElementById(id);
    // Guard: only drive a real <dialog> (showModal is dialog-only). A
    // missing id or wrong element type is a no-op, not a throw.
    if (!dlg || typeof dlg.showModal !== "function") return;
    evt.preventDefault();
    // Macrotask: past closedby="any" handling for this click.
    setTimeout(function () {
      if (!dlg.open) dlg.showModal();
      syncExpandControls(dlg);
      settleInitialFocus(dlg);
    }, 0);
  });
})();
