/**
 * dz-widget-registry.js — Registers vendored widget mount/unmount handlers
 * with the Dazzle component bridge (dz-component-bridge.js).
 *
 * Each registration maps a data-dz-widget type to a { mount, unmount } pair.
 * The bridge calls mount() on htmx:afterSettle and unmount() on htmx:beforeSwap.
 *
 * Widget types: combobox, multiselect, tags, datepicker, daterange, colorpicker, richtext
 */
(function () {
  var bridge = window.dz && window.dz.bridge;
  if (!bridge) {
    console.warn("[dz-widget-registry] Bridge not found — skipping widget registration");
    return;
  }

  // ── Tom Select widgets ──────────────────────────────────────────────

  function mountTomSelect(el, options) {
    if (typeof TomSelect === "undefined") return null;
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

  bridge.registerWidget("combobox", {
    mount: function (el, options) {
      return mountTomSelect(el, Object.assign({ maxItems: 1 }, options));
    },
    unmount: unmountTomSelect,
  });

  bridge.registerWidget("multiselect", {
    mount: function (el, options) {
      return mountTomSelect(el, Object.assign({ plugins: ["remove_button"] }, options));
    },
    unmount: unmountTomSelect,
  });

  bridge.registerWidget("tags", {
    mount: function (el, options) {
      return mountTomSelect(el, Object.assign({
        plugins: ["remove_button"],
        create: true,
        createFilter: options.createFilter || null,
      }, options));
    },
    unmount: unmountTomSelect,
  });

  // ── Flatpickr widgets ───────────────────────────────────────────────

  bridge.registerWidget("datepicker", {
    mount: function (el, options) {
      if (typeof flatpickr === "undefined") return null;
      var defaults = {
        dateFormat: options.dateFormat || "Y-m-d",
        altInput: true,
        altFormat: options.altFormat || "F j, Y",
        allowInput: true,
      };
      return flatpickr(el, Object.assign(defaults, options));
    },
    unmount: function (el, instance) {
      if (instance && typeof instance.destroy === "function") {
        instance.destroy();
      }
    },
  });

  bridge.registerWidget("daterange", {
    mount: function (el, options) {
      if (typeof flatpickr === "undefined") return null;
      var defaults = {
        mode: "range",
        dateFormat: options.dateFormat || "Y-m-d",
        altInput: true,
        altFormat: options.altFormat || "F j, Y",
        allowInput: true,
      };
      return flatpickr(el, Object.assign(defaults, options));
    },
    unmount: function (el, instance) {
      if (instance && typeof instance.destroy === "function") {
        instance.destroy();
      }
    },
  });

  // ── Pickr (color picker) ────────────────────────────────────────────

  bridge.registerWidget("colorpicker", {
    mount: function (el, options) {
      if (typeof Pickr === "undefined") return null;
      var hiddenInput = el.querySelector("input[type=hidden]") || el;
      var defaults = {
        el: el.querySelector(".pcr-trigger") || el,
        theme: "nano",
        default: hiddenInput.value || options.default || "#3b82f6",
        components: {
          preview: true,
          opacity: options.opacity !== false,
          hue: true,
          interaction: {
            hex: true,
            input: true,
            save: true,
          },
        },
      };
      var pickr = Pickr.create(Object.assign(defaults, options));
      pickr.on("save", function (color) {
        if (color && hiddenInput) {
          hiddenInput.value = color.toHEXA().toString();
        }
        pickr.hide();
      });
      return pickr;
    },
    unmount: function (el, instance) {
      if (instance && typeof instance.destroyAndRemove === "function") {
        instance.destroyAndRemove();
      }
    },
  });

  // ── Quill (rich text editor) ────────────────────────────────────────

  bridge.registerWidget("richtext", {
    mount: function (el, options) {
      if (typeof Quill === "undefined") return null;
      var editorDiv = el.querySelector("[data-dz-editor]") || el;
      var hiddenInput = el.querySelector("input[type=hidden]") || el.querySelector("textarea");
      var defaults = {
        theme: "snow",
        placeholder: options.placeholder || "Write something...",
        modules: {
          toolbar: options.toolbar || [
            [{ header: [1, 2, 3, false] }],
            ["bold", "italic", "underline", "strike"],
            [{ list: "ordered" }, { list: "bullet" }],
            ["link", "blockquote", "code-block"],
            ["clean"],
          ],
        },
      };
      var quill = new Quill(editorDiv, Object.assign(defaults, options));
      // Sync content to hidden input on change.
      // quill.root.innerHTML is Quill-managed markup, not raw user input — safe to read.
      if (hiddenInput) {
        if (hiddenInput.value) {
          // nosemgrep: innerHTML-set — restoring persisted Quill markup into Quill's own root
          quill.root.innerHTML = hiddenInput.value;
        }
        quill.on("text-change", function () {
          hiddenInput.value = quill.root.innerHTML;
        });
      }
      return quill;
    },
    unmount: function (_el, _instance) {
      // Quill does not have a destroy method — it is cleaned up when the DOM is removed
    },
  });

  // ── Range slider with value tooltip ─────────────────────────────────

  bridge.registerWidget("range-tooltip", {
    mount: function (el) {
      var input = el.querySelector("input[type=range]");
      var tooltip = el.querySelector("[data-dz-range-value]");
      if (!input || !tooltip) return null;
      var update = function () { tooltip.textContent = input.value; };
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
