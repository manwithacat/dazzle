/* HYPERPART: app-shell */
/*
 * dz-app-shell — the shell's sidebar toggle + persistence controller
 * (promoted verbatim from Dazzle's dz-alpine.js #1294 section; vanilla
 * and event-delegated — it never depended on Alpine).
 *
 * Contract:
 *   - root:    `.dz-app-shell` carries `data-dz-sidebar="open|closed"`
 *              (server-rendered initial state) — the DESKTOP (>= 64rem)
 *              state.
 *   - toggle:  `[data-dz-sidebar-toggle]` (chrome and/or rail hamburgers)
 *              flips the state and mirrors it to aria-expanded on every
 *              matching control (#1602 dual placement).
 *   - persist: the `dz_sidebar` cookie (1y) — a cookie, not localStorage,
 *              so the SERVER renders the correct state on first paint.
 *   - drawer:  below 64rem the toggle drives `data-dz-drawer="open"` on the
 *              root instead (#1798) — transient, never persisted; the
 *              desktop state and cookie are left alone. The server-emitted
 *              `[data-dz-sidebar-backdrop]` scrim, Escape and a sidebar
 *              nav-link click close it; focus returns to the chrome toggle.
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
  // One breakpoint, one number: the CSS narrow blocks are its exact
  // complement, `@media (width < 64rem)`.
  var wide = window.matchMedia("(min-width: 64rem)");
  function shell() {
    return document.querySelector(".dz-app-shell");
  }
  function readCookie() {
    var m = document.cookie.match(/(?:^|;\s*)dz_sidebar=(open|closed)\b/);
    return m ? m[1] : null;
  }
  function syncToggle(state) {
    var expanded = state === "open" ? "true" : "false";
    var nodes = document.querySelectorAll("[data-dz-sidebar-toggle]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].setAttribute("aria-expanded", expanded);
    }
  }
  function apply(state) {
    var el = shell();
    if (!el) return;
    el.setAttribute("data-dz-sidebar", state);
    syncToggle(state);
  }
  // ── #1798 — narrow off-canvas drawer ───────────────────────────────
  function drawerOpen() {
    var el = shell();
    return !!el && el.getAttribute("data-dz-drawer") === "open";
  }
  function focusChromeToggle() {
    var btn = document.querySelector(".dz-sidebar-toggle--chrome");
    if (btn) btn.focus();
  }
  function setDrawer(open) {
    var el = shell();
    if (!el) return;
    if (open) {
      el.setAttribute("data-dz-drawer", "open");
      syncToggle("open");
      var first = el.querySelector(".dz-sidebar a[href], .dz-sidebar summary");
      if (first) first.focus();
    } else {
      el.removeAttribute("data-dz-drawer");
      syncToggle("closed");
    }
  }
  function init() {
    var el = shell();
    if (!el) return;
    if (!wide.matches) {
      // Narrow: the drawer state, not the desktop state, drives the toggles.
      syncToggle(drawerOpen() ? "open" : "closed");
      return;
    }
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
    var target = e.target && e.target.closest ? e.target : null;
    var btn = target ? target.closest("[data-dz-sidebar-toggle]") : null;
    if (!wide.matches) {
      if (btn) {
        setDrawer(!drawerOpen());
      } else if (drawerOpen() && target) {
        if (target.closest("[data-dz-sidebar-backdrop]")) {
          setDrawer(false);
          focusChromeToggle();
        } else if (target.closest(".dz-sidebar a[href]")) {
          setDrawer(false);
        }
      }
      return;
    }
    if (!btn) return;
    var el = shell();
    if (!el) return;
    var next =
      el.getAttribute("data-dz-sidebar") === "open" ? "closed" : "open";
    apply(next);
    document.cookie =
      COOKIE + "=" + next + "; path=/; max-age=" + MAX_AGE + "; SameSite=Lax";
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !wide.matches && drawerOpen()) {
      setDrawer(false);
      focusChromeToggle();
    }
  });
  function onViewportChange() {
    var el = shell();
    if (el && wide.matches) el.removeAttribute("data-dz-drawer");
    init();
  }
  if (wide.addEventListener) wide.addEventListener("change", onViewportChange);
})();
