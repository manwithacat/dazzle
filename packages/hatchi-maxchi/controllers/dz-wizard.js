/* HYPERPART: wizard */
/*
 * dz-wizard — multi-stage form navigation via the stepper.
 *
 * Delegated from document; state lives in the DOM: the `[data-dz-wizard]`
 * root carries `data-dz-step`, stages are `[data-dz-stage]` blocks toggled
 * via the native `hidden` attribute, and each stepper item carries
 * `data-dz-state="complete|current|pending"` (the completed checkmark is
 * pure CSS off that attribute) plus `is-active` on its circle/label/
 * connector for the visual trail.
 *
 * Navigation contract (ported from the dzWizard island, which was
 * production-dead — nothing mounted x-data after the Jinja teardown):
 * clicking a stepper item goes BACK freely; FORWARD only one step at a
 * time, and only when every required input in the current stage is valid
 * (reportValidity so the browser surfaces what's missing).
 */
(function () {
  "use strict";

  function stageValid(root, step) {
    var stage = root.querySelector('[data-dz-stage="' + step + '"]');
    if (!stage) return true;
    var inputs = stage.querySelectorAll(
      "input[required], select[required], textarea[required]",
    );
    for (var i = 0; i < inputs.length; i++) {
      if (!inputs[i].checkValidity()) {
        inputs[i].reportValidity();
        return false;
      }
    }
    return true;
  }

  function render(root, step) {
    root.setAttribute("data-dz-step", String(step));
    var stages = root.querySelectorAll("[data-dz-stage]");
    for (var i = 0; i < stages.length; i++)
      stages[i].hidden =
        parseInt(stages[i].getAttribute("data-dz-stage"), 10) !== step;
    var items = root.querySelectorAll("[data-dz-step-to]");
    for (var j = 0; j < items.length; j++) {
      var idx = parseInt(items[j].getAttribute("data-dz-step-to"), 10);
      var state = idx < step ? "complete" : idx === step ? "current" : "pending";
      // state + aria-current live on the <li> (the button's host item);
      // the button is the keyboard-operable trigger.
      var host = items[j].closest("li") || items[j];
      host.setAttribute("data-dz-state", state);
      if (idx === step) host.setAttribute("aria-current", "step");
      else host.removeAttribute("aria-current");
      var active = idx <= step;
      var circle = host.querySelector(".dz-form-stepper-circle");
      var label = host.querySelector(".dz-form-stepper-label");
      var conn = host.querySelector(".dz-form-stepper-connector");
      if (circle) circle.classList.toggle("is-active", active);
      if (label) label.classList.toggle("is-active", active);
      // the connector after item idx lights once the NEXT step is reached
      if (conn) conn.classList.toggle("is-active", idx < step);
      var sr = host.querySelector("[data-dz-step-status]");
      if (sr) sr.textContent = state;
    }
  }

  // #1548: an early Submit with an invalid required field in a LATER
  // (hidden) stage must not be a silent no-op. The submit event never
  // fires in that case — the browser's constraint validation runs
  // FIRST and drops the submission because a hidden control is
  // unfocusable (console noise only). The reliable hook is the
  // `invalid` event, which fires per failing control during any
  // validation pass (native submit OR htmx's reportValidity): on the
  // first invalid control inside a HIDDEN wizard stage, jump the
  // wizard there and surface the bubble on the now-visible input.
  // Controls in the visible stage keep the native UI untouched.
  document.addEventListener(
    "invalid",
    function (evt) {
      var input = evt.target;
      if (!input || !input.closest) return;
      var root = input.closest("[data-dz-wizard]");
      if (!root) return;
      var stage = input.closest("[data-dz-stage]");
      if (!stage || !stage.hidden) return; // visible → native bubble is fine
      // One validation pass fires one invalid event PER failing
      // control — only the first may drive the jump, or a later
      // hidden stage would immediately steal the render.
      if (root.__dzWizardJumping) {
        evt.preventDefault();
        return;
      }
      root.__dzWizardJumping = true;
      setTimeout(function () {
        root.__dzWizardJumping = false;
      }, 0);
      evt.preventDefault(); // suppress the unfocusable-control drop
      render(root, parseInt(stage.getAttribute("data-dz-stage"), 10));
      input.focus();
      input.reportValidity();
    },
    true,
  );

  document.addEventListener("click", function (evt) {
    var item = evt.target.closest && evt.target.closest("[data-dz-step-to]");
    if (!item) return;
    var root = item.closest("[data-dz-wizard]");
    if (!root) return;
    var target = parseInt(item.getAttribute("data-dz-step-to"), 10);
    var current = parseInt(root.getAttribute("data-dz-step") || "0", 10);
    if (target === current) return;
    if (target > current) {
      // forward: one step at a time, current stage must validate
      if (target !== current + 1 || !stageValid(root, current)) return;
    }
    render(root, target);
  });
})();
