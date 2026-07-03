/* ── controllers/dz-confirm.js ── */
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
      '<button type="button" class="dz-button dz-button-outline" data-dz-confirm-cancel>Cancel</button>' +
      '<button type="button" class="dz-button dz-button-destructive" data-dz-confirm-accept>Confirm</button>' +
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

/* ── controllers/dz-command.js ── */
/* HYPERPART: command */
/*
 * dz-command — command-palette controller (HaTchi-MaXchi tranche 2B).
 *
 * Part of the `command` Hyperpart — see its manifest in site/registry.py
 * (partial + exchange contract) and its styles in components/hm-core.css
 * (also marked `HYPERPART: command`). `python tools/hyperpart.py command`
 * lists every part.
 *
 * The palette itself is server-rendered markup (dialog.dz-command with an
 * hx-get input); this controller only owns the purely-client bits:
 *   - ⌘K / Ctrl-K opens the first .dz-command dialog on the page
 *   - Esc closes explicitly (the palette's input is type="search", whose
 *     native behaviour swallows the first Esc to clear its value — so
 *     relying on <dialog>'s built-in cancel needs TWO presses mid-query)
 *   - ArrowUp/ArrowDown move [aria-selected] over .dz-command__item
 *   - Enter activates the selected item (click — works for <a> and
 *     <button hx-*> items alike)
 * Results arrive via htmx swaps; selection resets on each swap.
 */
(function () {
  "use strict";

  function palette() {
    return document.querySelector("dialog.dz-command");
  }

  function items(dlg) {
    return Array.prototype.slice.call(
      dlg.querySelectorAll(".dz-command__item"),
    );
  }

  function select(dlg, index) {
    var list = items(dlg);
    list.forEach(function (el, i) {
      if (i === index) {
        el.setAttribute("aria-selected", "true");
        el.scrollIntoView({ block: "nearest" });
      } else {
        el.removeAttribute("aria-selected");
      }
    });
    return index;
  }

  function selectedIndex(dlg) {
    var list = items(dlg);
    for (var i = 0; i < list.length; i++) {
      if (list[i].getAttribute("aria-selected") === "true") return i;
    }
    return -1;
  }

  document.addEventListener("keydown", function (evt) {
    var dlg = palette();
    if (!dlg) return;

    if ((evt.metaKey || evt.ctrlKey) && (evt.key === "k" || evt.key === "K")) {
      evt.preventDefault();
      if (dlg.open) {
        dlg.close();
      } else {
        dlg.showModal();
        var input = dlg.querySelector(".dz-command__input");
        if (input) input.focus();
      }
      return;
    }

    if (!dlg.open) return;

    if (evt.key === "Escape") {
      evt.preventDefault();
      dlg.close();
    } else if (evt.key === "ArrowDown" || evt.key === "ArrowUp") {
      evt.preventDefault();
      var count = items(dlg).length;
      if (!count) return;
      var cur = selectedIndex(dlg);
      var next = evt.key === "ArrowDown" ? cur + 1 : cur - 1;
      if (next < 0) next = count - 1;
      if (next >= count) next = 0;
      select(dlg, next);
    } else if (evt.key === "Enter") {
      var idx = selectedIndex(dlg);
      if (idx >= 0) {
        evt.preventDefault();
        items(dlg)[idx].click();
      }
    }
  });

  // Reset selection whenever htmx swaps new results in.
  document.addEventListener("htmx:afterSwap", function (evt) {
    var dlg = palette();
    if (dlg && dlg.open && dlg.contains(evt.target)) {
      if (items(dlg).length) select(dlg, 0);
    }
  });

  // Pointer dismiss — the ONLY way to close on a touch device with no
  // Esc key. The palette has padding:0 so its children fill it; a click
  // whose target is the <dialog> itself is therefore a backdrop click
  // (outside the box). Also handles the explicit close button. Native
  // `<dialog closedby="any">` gives this for free where supported (recent
  // Chromium); this handler is the cross-browser floor.
  document.addEventListener("click", function (evt) {
    var dlg = palette();
    if (!dlg || !dlg.open) return;
    if (evt.target === dlg || evt.target.closest("[data-hm-close-command]")) {
      dlg.close();
    }
  });
})();
