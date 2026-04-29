/**
 * dz-debug.js — introspection helper for the Alpine × HTMX bridge.
 *
 * Issue: #947. Exposes a `window.dzDebug` namespace that tests
 * (and humans) use to verify invariants about the bridge between
 * HTMX morphs and Alpine reactivity:
 *
 *   - Has the most recent `htmx:afterSettle` fired? When?
 *   - Is the `$data` proxy on a given selector the SAME instance
 *     it was before the last morph, or did it get re-attached?
 *   - Which `[x-data]` component roots are currently mounted?
 *
 * The proxy-identity API is the load-bearing piece. After
 * `Alpine.destroyTree(root)` + `Alpine.initTree(root)` (the #945
 * fix), the new `$data` is a fresh proxy. Tests assert the
 * identity changed; without that signal they can only see "cards
 * count is right" which #945 demonstrated wasn't sufficient.
 *
 * No external dependencies. Loads cheap. Methods only do work
 * when called. Production deployments that don't want the
 * introspection surface can omit this script from base.html
 * without runtime impact.
 */
(function () {
  if (typeof window === "undefined") return;

  var registry = {
    lastSettleAt: 0,
    lastSettleTarget: null,
    dataProxies: typeof WeakMap !== "undefined" ? new WeakMap() : null,
    nextProxyId: 1,
  };

  // Track every settle so tests can poll for "did the morph
  // actually run yet" without sleep-and-pray. Uses event capture
  // so it fires before any user-bound handlers and the timestamp
  // reflects the actual settle moment.
  if (
    typeof document !== "undefined" &&
    document.body &&
    typeof document.body.addEventListener === "function"
  ) {
    document.body.addEventListener("htmx:afterSettle", function (e) {
      registry.lastSettleAt = Date.now();
      registry.lastSettleTarget =
        e && e.detail && e.detail.target ? e.detail.target : null;
    });
  }

  function _resolveData(selector) {
    if (!selector) return null;
    if (typeof document === "undefined") return null;
    var el = document.querySelector(selector);
    if (!el) return null;
    if (!window.Alpine || typeof window.Alpine.$data !== "function") {
      return null;
    }
    return window.Alpine.$data(el);
  }

  function dataIdentity(selector) {
    // Return a stable string identity for the `$data` proxy
    // currently bound to the element at `selector`. Two calls
    // return the same string iff the same proxy is active. After
    // `Alpine.destroyTree` + `initTree` (the #945 fix), a fresh
    // proxy lands and the identity changes — that's how tests
    // verify the watcher graph actually re-attached, not just
    // "values look right" (which the cycle 936 fix achieved
    // without the watcher graph reattaching).
    var data = _resolveData(selector);
    if (!data) return null;
    if (!registry.dataProxies) {
      // Older browsers without WeakMap: fall back to "always new"
      // — caller can compare to a previous result by stringifying.
      return "proxy-" + Date.now() + "-" + Math.random();
    }
    var existing = registry.dataProxies.get(data);
    if (existing) return existing;
    var id = "proxy-" + registry.nextProxyId++;
    registry.dataProxies.set(data, id);
    return id;
  }

  function componentRoots() {
    // List all `[x-data]` roots in the current DOM with their
    // proxy id. Useful for quickly spotting "did a morph leave a
    // zombie root behind" (length should be 1 for the typical
    // workspace, more if nested components are present).
    if (typeof document === "undefined") return [];
    var nodes = document.querySelectorAll("[x-data]");
    var out = [];
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var selector;
      if (n.id) {
        selector = "#" + n.id;
      } else {
        // Fallback: tagName-based, deterministic for the i-th match.
        selector = n.tagName.toLowerCase() + ":nth-of-type(" + (i + 1) + ")";
      }
      out.push({
        tagName: n.tagName,
        id: n.id || null,
        xData: n.getAttribute("x-data"),
        proxyId: dataIdentity(selector),
      });
    }
    return out;
  }

  function lastSettleAt() {
    return registry.lastSettleAt;
  }

  function lastSettleTarget() {
    return registry.lastSettleTarget;
  }

  function reset() {
    // Test convenience: drop the proxy registry between cases so
    // proxy-id counters don't leak across tests in the same
    // browser context.
    registry.dataProxies =
      typeof WeakMap !== "undefined" ? new WeakMap() : null;
    registry.nextProxyId = 1;
    registry.lastSettleAt = 0;
    registry.lastSettleTarget = null;
  }

  window.dzDebug = {
    dataIdentity: dataIdentity,
    componentRoots: componentRoots,
    lastSettleAt: lastSettleAt,
    lastSettleTarget: lastSettleTarget,
    reset: reset,
  };
})();
