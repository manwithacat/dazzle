/** @ts-check */
/**
 * dz-csrf.js — Double-submit CSRF wiring for HTMX-powered Dazzle apps.
 *
 * The CSRF middleware (`back/runtime/csrf.py`) is enabled for EVERY security
 * profile. It sets a `dazzle_csrf` cookie `httponly=False` precisely so this
 * front-end handler can read it, and 403s any state-changing request
 * (POST/PUT/DELETE/PATCH) whose `X-CSRF-Token` header doesn't echo the cookie.
 *
 * Without this module every UI write from a generated /app form 403s in a real
 * browser — masked in CI only because the test clients (htmx_client.py,
 * rbac/verification_harness.py, test_runner.py) echo the cookie by hand (#1337).
 *
 * This listens for `htmx:config:request` (fired on every htmx request, bubbling
 * to document.body) and copies the cookie into the header. Safe methods are
 * left alone — the middleware ignores the header on GET/HEAD, so attaching it
 * there would be harmless but we skip it to keep request headers minimal and to
 * drive the loud-warn only where a missing token would actually break a write.
 *
 * Cookie/header names mirror CSRFConfig's framework defaults
 * (`dazzle_csrf` / `X-CSRF-Token`); downstream apps don't override them.
 *
 * Zero dependencies beyond HTMX. ~0.4 KB minified+gzipped.
 */

(function () {
  "use strict";

  // htmx 4 migration: attribute inheritance is explicit-by-default in htmx 4.
  // Dazzle's emitted markup relies on htmx 2's implicit inheritance (e.g.
  // inherited hx-target/hx-headers on ancestor containers). Restore the htmx 2
  // behaviour here while a markup audit converts to explicit `:inherited`.
  // Set synchronously at bundle-eval time — runs before htmx's DOMContentLoaded
  // init since the bundle is deferred. (ADR htmx4 migration; revisit in the
  // inheritance-audit follow-up.)
  if (window.htmx && window.htmx.config) {
    window.htmx.config.implicitInheritance = true;
  }

  var COOKIE_NAME = "dazzle_csrf";
  var HEADER_NAME = "X-CSRF-Token";
  var UNSAFE = { POST: 1, PUT: 1, DELETE: 1, PATCH: 1 };
  var warned = false;

  function readCookie(name) {
    var prefix = name + "=";
    var parts = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(prefix) === 0) {
        return parts[i].slice(prefix.length);
      }
    }
    return "";
  }

  document.body.addEventListener("htmx:config:request", function (evt) {
    var detail = /** @type {CustomEvent} */ (evt).detail;
    var token = readCookie(COOKIE_NAME);

    // Attach whenever the cookie exists, regardless of method. The middleware
    // ignores the header on safe methods, so this is harmless on GET/HEAD — and
    // it means the echo can never silently regress on htmx's `verb` field not
    // being what we expect. Method is used ONLY to scope the missing-cookie warn
    // to writes (the requests that would actually 403).
    if (token) {
      detail.ctx.request.headers[HEADER_NAME] = token;
      return;
    }

    var method = String(
      (detail.ctx && detail.ctx.request && detail.ctx.request.method) || "get",
    ).toUpperCase();
    if (UNSAFE[method] && !warned) {
      // Loud once-per-page: a mutating request is going out with no CSRF
      // cookie to echo, so the middleware will 403 it. Surfaces the #1337
      // failure mode (wiring present but cookie absent) instead of a silent
      // rejected write.
      warned = true;
      console.warn(
        "[dz-csrf] " +
          method +
          " request with no '" +
          COOKIE_NAME +
          "' cookie — '" +
          HEADER_NAME +
          "' header not attached; the CSRF middleware will reject this write.",
      );
    }
  });
})();
