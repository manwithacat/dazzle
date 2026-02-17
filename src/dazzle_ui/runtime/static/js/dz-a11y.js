/** @ts-check */
/**
 * dz-a11y.js — Accessibility event listeners for HTMX-powered Dazzle apps.
 *
 * Provides:
 *  - aria-busy management on live regions during HTMX requests
 *  - Page navigation announcements for hx-boost
 *  - Focus management: move focus to first invalid field after form swap
 *  - Focus management: move focus to main content after page navigation
 *
 * Zero dependencies (beyond HTMX being loaded). ~1 KB minified+gzipped.
 */

(function () {
  "use strict";

  // ── aria-busy management ──────────────────────────────────────────────
  //
  // When HTMX fires a request targeting a live region, set aria-busy="true"
  // so screen readers know content is loading. Clear it after the swap.

  document.addEventListener("htmx:beforeRequest", function (evt) {
    var targetSel =
      /** @type {HTMLElement} */ (evt.target).getAttribute("hx-target");
    if (!targetSel) return;
    var target = document.querySelector(targetSel);
    if (target && target.hasAttribute("aria-live")) {
      target.setAttribute("aria-busy", "true");
    }
  });

  document.addEventListener("htmx:afterSwap", function (evt) {
    var target = /** @type {CustomEvent} */ (evt).detail.target;
    if (target && target.hasAttribute("aria-live")) {
      target.setAttribute("aria-busy", "false");
    }
  });

  // ── Page navigation announcements for hx-boost ────────────────────────
  //
  // When hx-boost pushes a new URL into history, screen readers don't know
  // the page changed. Announce the new page title and move focus to <main>.

  document.addEventListener("htmx:pushedIntoHistory", function () {
    requestAnimationFrame(function () {
      // Announce new page title
      var announcer = document.getElementById("dz-page-announcer");
      if (announcer) {
        var title = document.title || "Page loaded";
        announcer.textContent = "";
        // Small delay so screen reader registers the change
        setTimeout(function () {
          announcer.textContent = title;
        }, 100);
      }

      // Move focus to main content
      var main = document.querySelector(
        "main, #main-content, [role='main']",
      );
      if (main) {
        if (!main.hasAttribute("tabindex")) {
          main.setAttribute("tabindex", "-1");
        }
        /** @type {HTMLElement} */ (main).focus({ preventScroll: false });
      }
    });
  });

  // ── Focus first invalid field after form swap ─────────────────────────
  //
  // After HTMX swaps form content (e.g. server-side validation), focus the
  // first field with aria-invalid="true" so the user knows what to fix.

  document.addEventListener("htmx:afterSwap", function (evt) {
    var target = /** @type {CustomEvent} */ (evt).detail.target;
    if (!target) return;
    var form = target.querySelector("form, [data-dz-form]");
    if (form) {
      var firstInvalid = form.querySelector("[aria-invalid='true']");
      if (firstInvalid) {
        /** @type {HTMLElement} */ (firstInvalid).focus();
      }
    }
  });

  // ── Page title update for fragment navigation ────────────────────────
  //
  // Fragment-targeted navigation (hx-target="#main-content") doesn't
  // include <title> in the response. The server sends the page title
  // via an HX-Trigger event instead.

  document.addEventListener("dz:titleUpdate", function (evt) {
    var title = /** @type {CustomEvent} */ (evt).detail.value;
    if (title) {
      document.title = title;
    }
  });

  // ── aria-current update after navigation ──────────────────────────────
  //
  // After hx-boost or fragment navigation, update aria-current="page"
  // on nav links to reflect the new active page.

  document.addEventListener("htmx:pushedIntoHistory", function () {
    requestAnimationFrame(function () {
      var path = window.location.pathname;
      document.querySelectorAll("[data-dazzle-nav]").forEach(function (link) {
        var route = link.getAttribute("data-dazzle-nav") || "";
        if (route === path) {
          link.setAttribute("aria-current", "page");
          link.classList.add("active");
        } else {
          link.removeAttribute("aria-current");
          link.classList.remove("active");
        }
      });
    });
  });
})();
