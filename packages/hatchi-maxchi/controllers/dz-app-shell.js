/* HYPERPART: app-shell */
/*
 * dz-app-shell — the shell's sidebar toggle + persistence controller
 * (promoted verbatim from Dazzle's dz-alpine.js #1294 section; vanilla
 * and event-delegated — it never depended on Alpine).
 *
 * Contract:
 *   - root:    `.dz-app-shell` carries `data-dz-sidebar="open|closed"`
 *              (server-rendered initial state).
 *   - toggle:  `[data-dz-sidebar-toggle]` (the topbar hamburger) flips the
 *              state and mirrors it to aria-expanded.
 *   - persist: the `dz_sidebar` cookie (1y) — a cookie, not localStorage,
 *              so the SERVER renders the correct state on first paint.
 */
// ── #1294 — App-shell sidebar toggle + persistence ──────────────────
// SSR emits `data-dz-sidebar` on `.dz-app-shell` (default "open") so the
// nav is reachable on first paint. This vanilla, event-delegated
// controller (a) reads the `dz_sidebar` cookie on load and applies it as
// a universal persistence fallback for render paths that default to
// "open", and (b) flips the state + writes the cookie when the topbar
// toggle is clicked. No Alpine dependency — survives HTMX swaps.
(function () {
  "use strict";
  var COOKIE = "dz_sidebar";
  var MAX_AGE = 60 * 60 * 24 * 365; // 1 year
  function shell() {
    return document.querySelector(".dz-app-shell");
  }
  function readCookie() {
    var m = document.cookie.match(/(?:^|;\s*)dz_sidebar=(open|closed)\b/);
    return m ? m[1] : null;
  }
  function syncToggle(state) {
    var t = document.querySelector("[data-dz-sidebar-toggle]");
    if (t) t.setAttribute("aria-expanded", state === "open" ? "true" : "false");
  }
  function apply(state) {
    var el = shell();
    if (!el) return;
    el.setAttribute("data-dz-sidebar", state);
    syncToggle(state);
  }
  function init() {
    var el = shell();
    if (!el) return;
    var persisted = readCookie();
    if (persisted && persisted !== el.getAttribute("data-dz-sidebar")) {
      apply(persisted);
    } else {
      syncToggle(el.getAttribute("data-dz-sidebar") || "open");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("click", function (e) {
    var btn =
      e.target && e.target.closest
        ? e.target.closest("[data-dz-sidebar-toggle]")
        : null;
    if (!btn) return;
    var el = shell();
    if (!el) return;
    var next =
      el.getAttribute("data-dz-sidebar") === "open" ? "closed" : "open";
    apply(next);
    document.cookie =
      COOKIE + "=" + next + "; path=/; max-age=" + MAX_AGE + "; SameSite=Lax";
  });
})();
