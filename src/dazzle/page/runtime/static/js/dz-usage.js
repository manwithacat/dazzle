/** @ts-check */
/**
 * dz-usage.js — first-party form-field engagement beacon (ADR-0050 Phase 5 / 1a).
 *
 * On a form field's FIRST focus, fires a fire-and-forget `navigator.sendBeacon`
 * to `POST /_dz/usage/field` with `{surface, field}`, so the render-time
 * form-widget inferer (1a) can adapt to which fields users actually engage.
 *
 * - `field` comes from the input's `data-dazzle-field` attribute (emitted on
 *   every form input by the form renderer).
 * - `surface` is the enclosing form's `data-dazzle-form` (the entity name) — a
 *   field's usage is about the field regardless of create vs edit, so the entity
 *   is the natural key, and it's already on the `<form>` (no markup change).
 *
 * Best-effort, privacy-safe: it sends only the surface + field *names* (no
 * values), once per (surface, field) per page load, and same-origin so the CSRF
 * origin gate admits it. A missing beacon just means slightly sparser data — the
 * inferer already falls back to the declared widget on thin/absent signal.
 *
 * Zero dependencies. ~0.5 KB minified.
 */

(function () {
  "use strict";

  var ENDPOINT = "/_dz/usage/field";
  var sent = Object.create(null); // "surface|field" -> true, dedup per page load

  document.addEventListener(
    "focusin",
    function (e) {
      var el = e.target;
      if (!el || typeof el.getAttribute !== "function") return;
      var field = el.getAttribute("data-dazzle-field");
      if (!field) return;
      var form =
        typeof el.closest === "function"
          ? el.closest("[data-dazzle-form]")
          : null;
      if (!form) return;
      var surface = form.getAttribute("data-dazzle-form");
      if (!surface) return;

      var key = surface + "|" + field;
      if (sent[key]) return;
      sent[key] = true;

      try {
        if (!navigator.sendBeacon) return;
        var fd = new FormData();
        fd.append("surface", surface);
        fd.append("field", field);
        navigator.sendBeacon(ENDPOINT, fd);
      } catch (err) {
        // Best-effort telemetry — never let a beacon failure affect the form.
        void err;
      }
    },
    true,
  );
})();
