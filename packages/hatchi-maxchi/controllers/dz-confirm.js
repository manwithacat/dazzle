/* HYPERPART: confirm */
/*
 * dz-confirm — designed hx-confirm surface (HaTchi-MaXchi tranche 1).
 *
 * Part of the `confirm` Hyperpart — manifest in site/registry.py; the
 * designed dialog's styles are in components/alert.css (marked
 * `HYPERPART: confirm`). `python tools/hyperpart.py confirm` lists them.
 *
 * Intercepts htmx's `htmx:confirm` event and replaces window.confirm with
 * a designed <dialog class="dz-alert-dialog"> (icon + title + message +
 * destructive-styled confirm). Every existing `hx-confirm="…"` attribute
 * in the fleet upgrades automatically — no emitter changes.
 *
 * Lifecycle-as-material (taste principle 9): the dialog is created lazily,
 * reused, and the htmx request is only issued via evt.detail.issueRequest()
 * on explicit confirm — cancel closes with no request.
 *
 * Opt-out: set `data-dz-native-confirm` on the element to keep
 * window.confirm (e.g. for tests that stub it).
 */
(function () {
  "use strict";

  var dialog = null;

  var LOCK_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
    'stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "dz-alert-dialog";
    dialog.innerHTML =
      '<span class="dz-alert-dialog__icon" aria-hidden="true">' +
      LOCK_ICON +
      "</span>" +
      '<h2 class="dz-alert-dialog__title">Are you sure?</h2>' +
      '<p class="dz-alert-dialog__message"></p>' +
      '<div class="dz-alert-dialog__actions">' +
      '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-confirm-cancel>Cancel</button>' +
      '<button type="button" class="dz-button" data-dz-variant="destructive" data-dz-confirm-accept>Confirm</button>' +
      "</div>";
    document.body.appendChild(dialog);
    return dialog;
  }

  document.addEventListener("htmx:confirm", function (evt) {
    var elt = evt.detail.elt;
    if (!elt || elt.hasAttribute("data-dz-native-confirm")) return;
    var question = evt.detail.question;
    if (!question) return; // no hx-confirm on this element

    evt.preventDefault(); // suppress window.confirm; we own the flow now

    var dlg = ensureDialog();
    dlg.querySelector(".dz-alert-dialog__message").textContent = question;

    var accept = dlg.querySelector("[data-dz-confirm-accept]");
    var cancel = dlg.querySelector("[data-dz-confirm-cancel]");

    function cleanup() {
      accept.removeEventListener("click", onAccept);
      cancel.removeEventListener("click", onCancel);
      dlg.removeEventListener("close", onClose);
      if (dlg.open) dlg.close();
    }
    function onAccept() {
      cleanup();
      // true = skip re-running the confirm hook for this request
      evt.detail.issueRequest(true);
    }
    function onCancel() {
      cleanup();
    }
    function onClose() {
      // Esc / backdrop close — treat as cancel
      cleanup();
    }

    accept.addEventListener("click", onAccept);
    cancel.addEventListener("click", onCancel);
    dlg.addEventListener("close", onClose);

    dlg.showModal();
    accept.focus();
  });
})();
