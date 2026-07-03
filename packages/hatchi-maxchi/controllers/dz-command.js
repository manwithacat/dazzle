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
