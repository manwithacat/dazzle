/* HYPERPART: confirm-panel */
/*
 * dz-confirm-gate — the irreversible-action consent gate.
 *
 * Delegated from document; every `change` inside a `[data-dz-confirm-gate]`
 * root recounts the checked REQUIRED boxes (`input[data-dz-required="true"]`)
 * against `data-dz-required-count` and arms/disarms the `.dz-confirm-primary`
 * anchor. State lives entirely in the DOM: while disarmed the anchor carries
 * `aria-disabled="true"` and its destination stays parked in
 * `data-dz-confirm-href`; arming promotes the href and drops aria-disabled.
 * A wholesale recount (never a +/- counter) means any real `change`
 * event self-heals the gate — including after an htmx morph (the SSR
 * markup arrives disarmed; the first user change recounts honestly).
 *
 * Zero required boxes = always armed — the server simply emits the anchor
 * with a live href and no aria-disabled, and this controller never fires
 * (no data-dz-required inputs to change). Optional boxes never gate.
 *
 * Replaces the Alpine `dzConfirmGate` island (x-data + :href/:aria-disabled
 * bindings) per the HM Hyperpart idiom: delegated vanilla controller,
 * server-owned markup, no framework runtime.
 */
(function () {
  "use strict";

  // A parked destination is only promoted into a live `href` if it is a
  // relative URL or an http(s) absolute — never a `javascript:`/`data:`
  // scheme. Control chars and surrounding whitespace are stripped first so a
  // `java\tscript:` cannot smuggle past the scheme check (browsers ignore
  // them when parsing the scheme). Returns the href if safe, else null.
  function safeHref(raw) {
    var v = String(raw == null ? "" : raw).replace(/[\u0000-\u0020]+/g, "");
    var scheme = /^([a-zA-Z][a-zA-Z0-9+.\-]*):/.exec(v);
    if (!scheme) return raw; // scheme-less = relative (#, /, ?, …) — safe
    var s = scheme[1].toLowerCase();
    return s === "http" || s === "https" ? raw : null;
  }

  document.addEventListener("change", function (evt) {
    var input = evt.target;
    if (!input || !input.matches || !input.matches('input[type="checkbox"]'))
      return;
    var root = input.closest("[data-dz-confirm-gate]");
    if (!root) return;

    var declared = parseInt(
      root.getAttribute("data-dz-required-count") || "0",
      10,
    );
    var required = root.querySelectorAll(
      'input[type="checkbox"][data-dz-required="true"]',
    );
    var needed = declared > 0 ? declared : required.length;

    var ticked = 0;
    for (var i = 0; i < required.length; i++) if (required[i].checked) ticked++;

    var primary = root.querySelector(".dz-confirm-primary");
    if (!primary) return;
    var href = primary.getAttribute("data-dz-confirm-href");

    if (needed === 0 || ticked >= needed) {
      var safe = href && safeHref(href);
      if (safe) primary.setAttribute("href", safe);
      primary.removeAttribute("aria-disabled");
    } else {
      primary.removeAttribute("href");
      primary.setAttribute("aria-disabled", "true");
    }
  });
})();
