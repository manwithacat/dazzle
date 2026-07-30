/* HYPERPART: toggle */
/*
 * dz-toggle — client press state for toolbar-style mode controls.
 *
 * Contract:
 *   Root: button (or role=button) with [data-dz-toggle] | [data-toggle]
 *         class .dz-toggle | .toggle is presentation only.
 *   State: aria-pressed="true"|"false" (flipped on click)
 *
 * Distinct from switch (native checkbox form boolean) and toggle-group
 * (exclusive radios). Server may set the initial aria-pressed; this
 * controller owns subsequent clicks so demos and SSR toolbars stay live
 * without a round-trip.
 *
 * Skips disabled buttons. Does not invent group exclusivity — that is
 * toggle-group's job.
 */
(function () {
  "use strict";

  var ROOT_SEL =
    "button[data-dz-toggle], button[data-toggle], " +
    "[data-dz-toggle][role='button'], [data-toggle][role='button']";

  function isPressed(el) {
    return el.getAttribute("aria-pressed") === "true";
  }

  function setPressed(el, on) {
    el.setAttribute("aria-pressed", on ? "true" : "false");
  }

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;
    var btn = t.closest(ROOT_SEL);
    if (!btn) return;
    if (btn.disabled || btn.getAttribute("aria-disabled") === "true") return;
    // Hosts that own their own bridge can opt out.
    if (btn.closest("[data-dz-widget]") || btn.closest("[data-widget]")) return;
    setPressed(btn, !isPressed(btn));
  });
})();
