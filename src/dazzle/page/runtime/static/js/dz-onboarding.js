/** @ts-check */
/**
 * dz-onboarding.js — Client behaviour for guided-onboarding overlays (v0.71.6).
 *
 * The server (`dazzle.render.onboarding.renderer`) emits self-contained
 * `<dz-onboarding-step>` custom elements with `data-kind`,
 * `data-guide`, `data-step`, and per-kind extra attributes. This
 * script wires up the runtime behaviours that the renderer can't
 * express declaratively:
 *
 *  - **Auto-dismiss timer** for `data-kind="nudge"`. Reads
 *    `data-autodismiss-ms` and fires a POST to the dismiss URL after
 *    the delay so the toast clears itself.
 *  - **Focus management** for `data-kind="blocking_task"`. Native
 *    `<dialog open>` should focus the first tabbable element, but
 *    older browsers and certain a11y trees need a nudge.
 *  - **Optional positioning** for `data-kind` in {popover, spotlight}
 *    when the page carries a `data-onboarding-anchor="<step-id>"`
 *    element. Anchors are opt-in — surfaces that don't emit them
 *    fall back to the CSS-default position (bottom-of-page for
 *    popover, viewport-centred for spotlight). Adding an anchor
 *    later is purely additive; no JS changes needed.
 *  - **htmx swap re-arming** — re-runs init on `htmx:after:swap` so
 *    overlays that arrive via fragment swap get wired up too.
 *
 * Zero dependencies beyond htmx (already loaded on every Dazzle page).
 * ~2 KB minified+gzipped.
 */

(function () {
  "use strict";

  /** Selector for every onboarding-step element on the page. */
  var STEP_SELECTOR = "dz-onboarding-step";

  /** Track elements we've already wired so afterSwap doesn't double-arm. */
  var WIRED_ATTR = "data-dz-wired";

  // ── public init ─────────────────────────────────────────────────────

  function initAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var nodes = scope.querySelectorAll(STEP_SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      initOne(/** @type {HTMLElement} */ (nodes[i]));
    }
  }

  function initOne(el) {
    if (el.getAttribute(WIRED_ATTR) === "1") return;
    el.setAttribute(WIRED_ATTR, "1");
    var kind = el.getAttribute("data-kind") || "";
    if (kind === "nudge") armNudgeAutoDismiss(el);
    if (kind === "blocking_task") focusFirstTabbable(el);
    if (kind === "popover" || kind === "spotlight") positionAgainstAnchor(el);
  }

  // ── nudge auto-dismiss ──────────────────────────────────────────────

  function armNudgeAutoDismiss(el) {
    var raw = el.getAttribute("data-autodismiss-ms");
    var ms = raw ? parseInt(raw, 10) : NaN;
    if (!ms || ms <= 0) return;
    var guide = el.getAttribute("data-guide");
    var step = el.getAttribute("data-step");
    if (!guide || !step) return;
    setTimeout(function () {
      // Bail out if the user already dismissed/completed via click.
      if (!document.body.contains(el)) return;
      var url =
        "/api/onboarding/" +
        encodeURIComponent(guide) +
        "/" +
        encodeURIComponent(step) +
        "/dismiss";
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-Requested-With": "dz-onboarding" },
      })
        .catch(function () {
          // Network errors are non-fatal — the user can still
          // dismiss manually. Removing the DOM node either way so
          // it doesn't linger past the timer.
        })
        .finally(function () {
          if (el.parentNode) el.parentNode.removeChild(el);
        });
    }, ms);
  }

  // ── blocking_task focus management ──────────────────────────────────

  function focusFirstTabbable(el) {
    // Native <dialog open> tries to focus the first interactive child,
    // but several browser engines miss certain elements. Find an
    // explicit tabbable inside the dialog and move focus there.
    var dialog = el.querySelector("dialog");
    if (!dialog) return;
    var first = dialog.querySelector(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (
      first &&
      typeof /** @type {HTMLElement} */ (first).focus === "function"
    ) {
      try {
        /** @type {HTMLElement} */ (first).focus();
      } catch (_e) {
        // Ignore focus errors — the page still works.
      }
    }
  }

  // ── popover/spotlight positioning against an opt-in anchor ──────────

  function positionAgainstAnchor(el) {
    // The server-rendered step doesn't carry coordinates — instead
    // pages may opt in by adding `data-onboarding-anchor="<guide>.<step>"`
    // (or, equivalently, the step's full target path) to the
    // element they want the overlay to attach to. If we find one,
    // position the overlay's primary card relative to it; if not,
    // leave the CSS-default position alone.
    var guide = el.getAttribute("data-guide");
    var step = el.getAttribute("data-step");
    if (!guide || !step) return;
    var anchorId = guide + "." + step;
    var anchor = document.querySelector(
      '[data-onboarding-anchor="' + cssEscape(anchorId) + '"]',
    );
    if (!anchor) return;
    var rect = /** @type {HTMLElement} */ (anchor).getBoundingClientRect();
    var placement = el.getAttribute("data-placement") || "bottom";
    var card = /** @type {HTMLElement} */ (
      el.querySelector(".dz-onboarding-popover, .dz-onboarding-spotlight__card")
    );
    if (!card) return;
    // Position the card in viewport coordinates. Fixed positioning so
    // the overlay sits on top of whatever's underneath without
    // affecting page flow.
    card.style.position = "fixed";
    card.style.zIndex = "9999";
    switch (placement) {
      case "top":
        card.style.left = rect.left + rect.width / 2 + "px";
        card.style.top = rect.top + "px";
        card.style.transform = "translate(-50%, -100%)";
        break;
      case "left":
        card.style.left = rect.left + "px";
        card.style.top = rect.top + rect.height / 2 + "px";
        card.style.transform = "translate(-100%, -50%)";
        break;
      case "right":
        card.style.left = rect.right + "px";
        card.style.top = rect.top + rect.height / 2 + "px";
        card.style.transform = "translate(0, -50%)";
        break;
      case "center":
        card.style.left = "50%";
        card.style.top = "50%";
        card.style.transform = "translate(-50%, -50%)";
        break;
      case "bottom":
      default:
        card.style.left = rect.left + rect.width / 2 + "px";
        card.style.top = rect.bottom + "px";
        card.style.transform = "translate(-50%, 0)";
        break;
    }
  }

  /** Conservative CSS.escape polyfill — falls back to identity. */
  function cssEscape(value) {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(value);
    }
    return value.replace(/(["\\])/g, "\\$1");
  }

  // ── lifecycle hooks ─────────────────────────────────────────────────

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll(document);
    });
  } else {
    initAll(document);
  }

  // htmx swap re-arming. Any newly-injected onboarding overlays get
  // wired up the same as their initial-render siblings.
  document.addEventListener("htmx:after:swap", function (evt) {
    var target = /** @type {CustomEvent} */ (evt).detail.target;
    initAll(target || document);
  });
})();
