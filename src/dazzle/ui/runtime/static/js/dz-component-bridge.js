/**
 * Dazzle Component Bridge — manages vendored widget lifecycle across HTMX swaps.
 *
 * Each widget mount point is an element with:
 *   data-dz-widget   — widget type key (e.g., "datepicker", "combobox")
 *   data-dz-options  — JSON-encoded options for the widget
 *
 * Widget types are registered via window.dz.bridge.registerWidget(type, { mount, unmount }).
 *   mount(el, options)   — initialize the widget on the element, return instance
 *   unmount(el, instance) — tear down the widget
 *
 * The bridge hooks into HTMX lifecycle events:
 *   htmx:beforeSwap  — unmount widgets in the swap target
 *   htmx:afterSettle — mount widgets in the swapped content
 */
(function () {
  var REGISTRY = {};
  var INSTANCES = new WeakMap();

  function mountWidgets(root) {
    var els = root.querySelectorAll("[data-dz-widget]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (INSTANCES.has(el)) continue;
      var type = el.dataset.dzWidget;
      var handler = REGISTRY[type];
      if (!handler) continue;
      var options = {};
      try {
        options = JSON.parse(el.dataset.dzOptions || "{}");
      } catch (_) {}
      try {
        var instance = handler.mount(el, options);
        INSTANCES.set(el, { type: type, instance: instance });
      } catch (e) {
        console.error("[dz-bridge] Failed to mount widget:", type, e);
      }
    }
  }

  function unmountWidgets(root) {
    if (!root || root.nodeType !== 1) return;
    var els = root.querySelectorAll
      ? root.querySelectorAll("[data-dz-widget]")
      : [];
    // Also check root itself
    var targets =
      root.matches && root.matches("[data-dz-widget]")
        ? [root].concat(Array.prototype.slice.call(els))
        : Array.prototype.slice.call(els);
    for (var i = 0; i < targets.length; i++) {
      var el = targets[i];
      var entry = INSTANCES.get(el);
      if (!entry) continue;
      var handler = REGISTRY[entry.type];
      if (handler && typeof handler.unmount === "function") {
        try {
          handler.unmount(el, entry.instance);
        } catch (_) {}
      }
      INSTANCES.delete(el);
    }
  }

  function registerWidget(type, handler) {
    if (!type || !handler || typeof handler.mount !== "function") {
      console.error(
        "[dz-bridge] registerWidget requires type and { mount } handler",
      );
      return;
    }
    REGISTRY[type] = handler;
  }

  // Expose on window.dz namespace
  window.dz = window.dz || {};
  window.dz.bridge = {
    registerWidget: registerWidget,
    mountWidgets: mountWidgets,
    unmountWidgets: unmountWidgets,
  };

  document.addEventListener("DOMContentLoaded", function () {
    mountWidgets(document);
    document.body.addEventListener("htmx:afterSettle", function (e) {
      mountWidgets(e.target);
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      if (e.detail && e.detail.target) {
        unmountWidgets(e.detail.target);
      }
    });
  });
})();
