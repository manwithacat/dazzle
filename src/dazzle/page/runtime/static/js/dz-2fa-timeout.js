/** @ts-check */
/**
 * dz-2fa-timeout.js — warn before a pending two-factor sign-in times out (#1842).
 *
 * WCAG 2.2.1 Timing Adjustable. The server (`two_factor_views._timeout_warning`)
 * renders a `[data-dz-2fa-timeout]` block on the sign-in code page carrying:
 *
 *  - `data-expires-in`   seconds until the challenge times out, from render
 *                        (relative, so a skewed client clock does not matter);
 *  - `data-warn-seconds` how long before the deadline to warn (>= 20s);
 *  - an empty `role="alert"` message element holding the copy in data attributes;
 *  - a hidden actions group with a native "More time" form
 *    (`[data-dz-2fa-extend]`, posts to /auth/2fa/challenge/extend) and, for email
 *    codes, an "Email me a new code" form;
 *  - a hidden "Sign in again" link shown once time is up.
 *
 * Shortly before the deadline the message is filled (announced by the alert
 * region) and the actions are revealed. Focus is not moved: the alert is read
 * out and the button is the next stop in tab order. "More time" is posted with
 * fetch (Accept: application/json, X-CSRF-Token echoed from the `dazzle_csrf`
 * cookie); on success the clock restarts and focus returns to the code field
 * (the focused button just disappeared). Without this script the forms are
 * plain posts that 303 back to the page. No inline handlers (CSP-safe).
 */

(function () {
  "use strict";

  var ROOT = "[data-dz-2fa-timeout]";
  var CSRF_COOKIE = "dazzle_csrf";

  function readCookie(name) {
    var prefix = name + "=";
    var parts = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(prefix) === 0) return parts[i].slice(prefix.length);
    }
    return "";
  }

  function wire(root) {
    if (root.getAttribute("data-dz-wired") === "1") return;
    root.setAttribute("data-dz-wired", "1");
    var message = root.querySelector("[data-dz-2fa-timeout-message]");
    var actions = root.querySelector("[data-dz-2fa-timeout-actions]");
    var restart = root.querySelector("[data-dz-2fa-timeout-restart]");
    var extendForm = root.querySelector("form[data-dz-2fa-extend]");
    var warnSeconds = parseInt(root.getAttribute("data-warn-seconds") || "60", 10);
    var warnTimer = 0;
    var expireTimer = 0;

    function say(attr) {
      if (message) message.textContent = message.getAttribute(attr) || "";
    }

    function arm(expiresIn) {
      clearTimeout(warnTimer);
      clearTimeout(expireTimer);
      warnTimer = window.setTimeout(warn, Math.max(0, expiresIn - warnSeconds) * 1000);
      expireTimer = window.setTimeout(expire, Math.max(0, expiresIn) * 1000);
    }

    function warn() {
      say("data-warn-text");
      if (actions) actions.hidden = false;
    }

    function expire() {
      clearTimeout(warnTimer);
      say("data-expired-text");
      if (actions) actions.hidden = true;
      if (restart) restart.hidden = false;
    }

    function focusCode() {
      var input = document.querySelector("input[name='code']");
      if (input) /** @type {HTMLElement} */ (input).focus();
    }

    if (extendForm) {
      extendForm.addEventListener("submit", function (evt) {
        evt.preventDefault();
        var form = /** @type {HTMLFormElement} */ (extendForm);
        fetch(form.action, {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-CSRF-Token": readCookie(CSRF_COOKIE) },
        })
          .then(function (resp) {
            if (!resp.ok) throw new Error(String(resp.status));
            return resp.json();
          })
          .then(function (body) {
            if (actions) actions.hidden = true;
            if (!body.extendable) form.remove();
            say("data-extended-text");
            focusCode();
            arm(Number(body.expires_in) || 0);
          })
          .catch(function () {
            // The server refused (time already up, or the cap was reached): fall
            // back to the native post, which lands on the honest page.
            form.submit();
          });
      });
    }

    arm(parseInt(root.getAttribute("data-expires-in") || "0", 10));
  }

  function init() {
    var roots = document.querySelectorAll(ROOT);
    for (var i = 0; i < roots.length; i++) wire(roots[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // The code form posts through htmx and swaps the body (e.g. a wrong code), which
  // brings a fresh block with a fresh clock; timers on the detached one are inert.
  document.addEventListener("htmx:after:swap", init);
})();
