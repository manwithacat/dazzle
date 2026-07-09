/**
 * dz-widget-registry.js — Registers vendored widget mount/unmount handlers
 * with the Dazzle component bridge (dz-component-bridge.js).
 *
 * Each registration maps a data-dz-widget type to a { mount, unmount } pair.
 * The bridge calls mount() on htmx:after:settle and unmount() on htmx:before:swap.
 *
 * Widget types: range-tooltip.
 * (Note: combobox is now HM-native — controllers/dz-combobox.js (HMC-018
 * slice 1); tags is now HM-native — controllers/dz-tags.js (HMC-018
 * slice 2). multiselect (+ the vendored TomSelect runtime it used) retired
 * in HMC-018 slice 3 — 0 fleet usage, no emitter. colorpicker dropped in
 * #976 — `widget=color` uses native input. richtext moved to dz-richtext.js
 * in #977 cycle 4 — Dazzle-native editor, no vendor dependency.)
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) {
    console.warn(
      "[dz-widget-registry] Bridge not found — skipping widget registration",
    );
    return;
  }

  // combobox (widget=combobox) + tags (widget=tags) are HM-native —
  // progressively-enhanced native <select data-dz-combobox> /
  // <input data-dz-tags> driven by delegated controllers/dz-combobox.js +
  // controllers/dz-tags.js (HMC-018 slices 1-2). The vendored TomSelect
  // runtime that formerly backed combobox/tags/multiselect was removed in
  // HMC-018 slice 3 (multiselect had 0 fleet usage and no emitter).

  // ── Color picker — native <input type="color"> (#976 — dropped Pickr).
  // No bridge registration needed: the form_field.html macro emits a
  // bare native input wired up via Alpine's `x-model`. The widget
  // registry entry that lived here was 30+ lines of Pickr glue.

  // ── Rich text editor (#977 cycle 4) ─────────────────────────────────
  // The "richtext" bridge is now registered by dz-richtext.js
  // (Dazzle-native, no vendor dependency). Quill removed in cycle 4.

  // ── Range slider with value tooltip ─────────────────────────────────

  bridge.registerWidget("range-tooltip", {
    mount: function (el) {
      var input = el.querySelector("input[type=range]");
      var tooltip = el.querySelector("[data-dz-range-value]");
      if (!input || !tooltip) return null;
      var update = function () {
        tooltip.textContent = input.value;
      };
      input.addEventListener("input", update);
      update();
      return { input: input, handler: update };
    },
    unmount: function (_el, instance) {
      if (instance && instance.input) {
        instance.input.removeEventListener("input", instance.handler);
      }
    },
  });
})();
