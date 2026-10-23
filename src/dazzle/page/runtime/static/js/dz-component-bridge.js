/**
 * Dazzle Component Bridge — manages vendored widget lifecycle across HTMX swaps.
 *
 * Each widget mount point is an element with:
 *   data-dz-widget   — widget type key (e.g., "combobox", "tags")
 *   data-dz-options  — JSON-encoded options for the widget
 *
 * Widget types are registered via window.dz.bridge.registerWidget(type, { mount, unmount }).
 *   mount(el, options)   — initialize the widget on the element, return instance
 *   unmount(el, instance) — tear down the widget
 *
 * The bridge hooks into HTMX lifecycle events:
 *   htmx:before:swap  — unmount widgets in the swap target
 *   htmx:after:settle — mount widgets in the swapped content, then dispatch
 *                       `dz:region-loaded` (below)
 *
 * `dz:region-loaded` (#1845) is Dazzle's documented host contract for "a
 * workspace region's content was swapped in": a bubbling CustomEvent
 * dispatched on the `[data-dz-region]` element after the swap settles and
 * the bridge has mounted its widgets, with `detail.name` = the region's
 * `data-dz-region-name`. It fires once per swap whose target is the region
 * or lies inside it. Host scripts key enhancements off it instead of htmx
 * event names, which changed between htmx 2 and htmx 4.
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

  var REGION = "[data-dz-region]";

  // The region a settled swap landed in: the swap target or its nearest
  // region ancestor; for an outerHTML swap the old target is detached, so
  // fall back to the new content htmx reports.
  function settledRegion(e) {
    var candidates = [e.target];
    var fresh = e.detail && e.detail.newContent;
    if (fresh && fresh.length) {
      candidates = candidates.concat(Array.prototype.slice.call(fresh));
    }
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      if (!el || el.nodeType !== 1 || !el.isConnected || !el.closest) continue;
      var region = el.closest(REGION);
      if (region) return region;
    }
    return null;
  }

  function announceRegionLoaded(e) {
    var region = settledRegion(e);
    if (!region) return;
    region.dispatchEvent(
      new CustomEvent("dz:region-loaded", {
        bubbles: true,
        detail: { name: region.getAttribute("data-dz-region-name") || "" },
      }),
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    mountWidgets(document);
    document.body.addEventListener("htmx:after:settle", function (e) {
      mountWidgets(e.target);
      announceRegionLoaded(e);
    });
    document.body.addEventListener("htmx:before:swap", function (e) {
      if (e.detail && e.detail.target) {
        unmountWidgets(e.detail.target);
      }
    });
  });
})();
