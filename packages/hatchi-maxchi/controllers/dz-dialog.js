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
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var trigger = evt.target.closest("[data-dz-dialog-open]");
    if (!trigger) return;
    var id = trigger.getAttribute("data-dz-dialog-open");
    if (!id) return;
    var dlg = document.getElementById(id);
    // Guard: only drive a real <dialog> (showModal is dialog-only). A
    // missing id or wrong element type is a no-op, not a throw.
    if (dlg && typeof dlg.showModal === "function") {
      evt.preventDefault();
      dlg.showModal();
    }
  });
})();
