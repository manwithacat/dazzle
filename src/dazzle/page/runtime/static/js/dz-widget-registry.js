/**
 * dz-widget-registry.js — Registers vendored widget mount/unmount handlers
 * with the Dazzle component bridge (dz-component-bridge.js).
 *
 * Each registration maps a data-dz-widget type to a { mount, unmount } pair.
 * The bridge calls mount() on htmx:after:settle and unmount() on htmx:before:swap.
 *
 * Widget types: combobox, multiselect, tags, datepicker, daterange,
 * range-tooltip. (Note: colorpicker dropped in #976 — `widget=color`
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

  bridge.registerWidget("combobox", {
    mount: function (el, options) {
      // #927: when the combobox is bound to an FK (data-dz-ref-api set
      // on the <select>), wire TomSelect's remote-load callback so it
      // fetches options from the target entity's list endpoint at first
      // open + on every type-to-search query. Without this branch the
      // <select> stays empty (it has no static <option>s — the form
      // template intentionally leaves them out so this code path
      // populates them) and TomSelect renders a useless empty dropdown.
      var refApi = el.getAttribute("data-dz-ref-api");
      if (refApi) {
        var fkOptions = Object.assign(
          {
            maxItems: 1,
            valueField: "id",
            labelField: "__display__",
            searchField: ["__display__"],
            load: function (query, callback) {
              var url =
                refApi +
                (refApi.indexOf("?") >= 0 ? "&" : "?") +
                "page_size=100";
              fetch(url, { headers: { Accept: "application/json" } })
                .then(function (r) {
                  return r.json();
                })
                .then(function (data) {
                  var items = (data && data.items) || [];
                  // Defensive fallback for entities without display_field —
                  // TomSelect would render `undefined` otherwise.
                  items.forEach(function (it) {
                    if (it.__display__ == null)
                      it.__display__ = it.name || it.id || "";
                  });
                  callback(items);
                })
                .catch(function () {
                  callback();
                });
            },
            preload: "focus",
          },
          options,
        );
        return mountTomSelect(el, fkOptions);
      }
      return mountTomSelect(el, Object.assign({ maxItems: 1 }, options));
    },
    unmount: unmountTomSelect,
  });

  bridge.registerWidget("multiselect", {
    mount: function (el, options) {
      return mountTomSelect(
        el,
        Object.assign({ plugins: ["remove_button"] }, options),
      );
    },
    unmount: unmountTomSelect,
  });

  bridge.registerWidget("tags", {
    mount: function (el, options) {
      return mountTomSelect(
        el,
        Object.assign(
          {
            plugins: ["remove_button"],
            create: true,
            createFilter: options.createFilter || null,
          },
          options,
        ),
      );
    },
    unmount: unmountTomSelect,
  });

  // ── Flatpickr widgets ───────────────────────────────────────────────

  function warnFlatpickrMissing() {
    console.warn(
      "[dz-widget-registry] flatpickr vendor JS not loaded — datepicker/daterange widget left inert. Ensure /static/vendor/flatpickr.min.js is served (see app_chrome.js_scripts).",
    );
  }

  bridge.registerWidget("datepicker", {
    mount: function (el, options) {
      if (typeof flatpickr === "undefined") {
        warnFlatpickrMissing();
        return null;
      }
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
      if (typeof flatpickr === "undefined") {
        warnFlatpickrMissing();
        return null;
      }
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
