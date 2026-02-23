/**
 * Dazzle UI Islands — lazy-loads ES module islands into server-rendered pages.
 *
 * Each island mount point is a <div data-island="name"> with:
 *   data-island-src   — JS entry point (ES module with mount() export)
 *   data-island-props — JSON-encoded props
 *   data-island-api-base — API prefix for the island's CRUD endpoints
 *
 * The island module must export: mount({ el, props, apiBase }) => void
 * It may optionally return an unmount function stored on el._dzIslandUnmount.
 */
(function () {
  var MOUNTED = new WeakSet();

  function mountIslands(root) {
    root.querySelectorAll("[data-island]").forEach(function (el) {
      if (MOUNTED.has(el)) return;
      MOUNTED.add(el);
      var src = el.dataset.islandSrc;
      if (!src) return;
      var props = {};
      try { props = JSON.parse(el.dataset.islandProps || "{}"); } catch (_) {}
      var apiBase = el.dataset.islandApiBase || "";
      import(src).then(function (mod) {
        if (typeof mod.mount === "function") {
          var cleanup = mod.mount({ el: el, props: props, apiBase: apiBase });
          if (typeof cleanup === "function") {
            el._dzIslandUnmount = cleanup;
          }
        }
      }).catch(function (e) {
        console.error('[dz-islands] Failed to mount "' + el.dataset.island + '":', e);
      });
    });
  }

  function unmountIslands(nodes) {
    nodes.forEach(function (node) {
      if (node.nodeType !== 1) return;
      var islands = node.matches && node.matches("[data-island]")
        ? [node]
        : Array.prototype.slice.call(node.querySelectorAll("[data-island]") || []);
      islands.forEach(function (el) {
        if (typeof el._dzIslandUnmount === "function") {
          try { el._dzIslandUnmount(el); } catch (_) {}
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    mountIslands(document);
    document.body.addEventListener("htmx:afterSettle", function (e) { mountIslands(e.target); });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      if (e.detail && e.detail.target) unmountIslands([e.detail.target]);
    });
  });
})();
