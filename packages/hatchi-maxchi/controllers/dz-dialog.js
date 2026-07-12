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
 * initial focus: showModal focuses the first focusable (often the ✕
 * close). WebKit paints that as :focus-visible after a pointer open, so
 * the close control looks "active" until the user clicks away. After
 * open we settle focus on [autofocus] if present, else the dialog shell
 * (tabindex=-1, outline suppressed in CSS) so chrome is not lit until
 * the user Tabs. Esc / focus trap still work — focus remains inside.
 */
(function () {
  "use strict";

  var CLOSE_SEL =
    ".dz-drawer__close, .drawer__close, .dz-dialog__close, .dialog__close";

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

  function isCloseControl(el) {
    return !!(el && el.closest && el.closest(CLOSE_SEL));
  }

  /**
   * After showModal, avoid leaving focus on the dismiss ✕ (looks active
   * under WebKit :focus-visible). Honour [autofocus]; otherwise hold
   * focus on the dialog shell.
   */
  function settleInitialFocus(dlg) {
    var auto = dlg.querySelector("[autofocus]");
    if (auto) {
      focusQuiet(auto);
      return;
    }
    var active = document.activeElement;
    if (!active || !dlg.contains(active) || !isCloseControl(active)) {
      // Already on a meaningful control (or dialog) — leave it.
      if (active && dlg.contains(active) && active !== dlg) return;
    }
    if (!dlg.hasAttribute("tabindex")) {
      dlg.setAttribute("tabindex", "-1");
    }
    focusQuiet(dlg);
  }

  document.addEventListener("click", function (evt) {
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
      settleInitialFocus(dlg);
    }, 0);
  });
})();
