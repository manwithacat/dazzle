/**
 * dz-widget-registry.js — Registers vendored widget mount/unmount handlers
 * with the Dazzle component bridge (dz-component-bridge.js).
 *
 * Each registration maps a data-dz-widget type to a { mount, unmount } pair.
 * The bridge calls mount() on htmx:after:settle and unmount() on htmx:before:swap.
 *
 * Widget types: multiselect, range-tooltip.
 * (Note: combobox is now HM-native — controllers/dz-combobox.js (HMC-018
 * slice 1); tags is now HM-native — controllers/dz-tags.js (HMC-018
 * slice 2). colorpicker dropped in #976 — `widget=color`
 * uses native input. richtext moved to dz-richtext.js in #977 cycle 4
 * — Dazzle-native editor, no vendor dependency.)
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) {
    console.warn(
      "[dz-widget-registry] Bridge not found — skipping widget registration",
    );
    return;
  }

  // ── Tom Select widgets ──────────────────────────────────────────────

  function mountTomSelect(el, options) {
    if (typeof TomSelect === "undefined") {
      console.warn(
        "[dz-widget-registry] TomSelect vendor JS not loaded — combobox/FK-ref widget left inert. Ensure /static/vendor/tom-select.min.js is served (see app_chrome.js_scripts).",
      );
      return null;
    }
    var defaults = {
      plugins: options.plugins || [],
      maxItems: options.maxItems || null,
      create: options.create || false,
      placeholder: el.getAttribute("placeholder") || "",
    };
    return new TomSelect(el, Object.assign(defaults, options));
  }

  function unmountTomSelect(el, instance) {
    if (instance && typeof instance.destroy === "function") {
      instance.destroy();
    }
  }

  // combobox (widget=combobox) is now HM-native — a progressively-enhanced
  // native <select data-dz-combobox> driven by the delegated
  // controllers/dz-combobox.js (HMC-018 slice 1). No TomSelect mount here.
  // TomSelect still backs multiselect + tags below until later slices.

  bridge.registerWidget("multiselect", {
    mount: function (el, options) {
      return mountTomSelect(
        el,
        Object.assign({ plugins: ["remove_button"] }, options),
      );
    },
    unmount: unmountTomSelect,
  });

  // tags (widget=tags) is now HM-native — a progressively-enhanced native
  // <input data-dz-tags> carrying a comma-joined value, driven by the
  // delegated controllers/dz-tags.js (HMC-018 slice 2). No TomSelect mount
  // here. TomSelect still backs multiselect above until slice 3.

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
