/* HYPERPART: pdf */
/*
 * dz-pdf — a progressively enhanced PDF viewing shell (the hx-pdf
 * primitive). The application renders the shell + controls access
 * (the server-side range proxy); PDF.js renders the document; this
 * controller glues them: lazy library load, toolbar wiring, page/zoom
 * state, URL deep-links, loading/error status.
 *
 * Mount: every `[data-dz-pdf]` root at load + htmx settle (including
 * the swap target itself). The PDF.js library is NOT bundled — it
 * lazy-loads as an ES module from `data-dz-pdf-lib` (+ optional
 * `data-dz-pdf-worker`) only when the first viewer scrolls into view.
 *
 * Root attributes (the spec §7 contract, dz-namespaced):
 *   data-dz-pdf-src           bytes URL (the /_dazzle/documents proxy)
 *   data-dz-pdf-lib           PDF.js module URL (required to enhance)
 *   data-dz-pdf-worker        PDF.js worker URL
 *   data-dz-pdf-initial-page  1-based start page
 *   data-dz-pdf-state         "url" syncs ?dzpdf-page/?dzpdf-zoom via
 *                             replaceState; anything else keeps state
 *                             local (default)
 * Toolbar slots (wired when present, all optional):
 *   [data-dz-pdf-prev] [data-dz-pdf-next] [data-dz-pdf-page]
 *   [data-dz-pdf-page-count] [data-dz-pdf-zoom-in] [data-dz-pdf-zoom-out]
 *   [data-dz-pdf-fit-width] [data-dz-pdf-status] [data-dz-pdf-viewer]
 *
 * Leftover honesty (cycle 2151): leftover page junk must not invent a
 * page. parseInt("2abc", 10) === 2 / "zzz" / "99" on a 2-page doc is
 * invalid — the canvas stays put and the input fails custom validity
 * so change/Enter cannot jump as if the leftover were accepted.
 * Empty input on blur restores from the current page (empty is not
 * leftover junk). Valid whole numbers in [1, numPages] render.
 * Out-of-range does not invent by clamping. Same class as number
 * leftover junk (2149) and money leftover junk (2121). Gallery
 * rest-state is unchanged (oral #33).
 *
 * No JS → the <noscript> download link inside the viewer region is the
 * whole experience (progressive enhancement, spec §2).
 */
(function () {
  "use strict";

  var libPromise = null;
  var live = [];

  function loadLib(root) {
    if (libPromise) return libPromise;
    var url = root.getAttribute("data-dz-pdf-lib");
    if (!url) return Promise.reject(new Error("data-dz-pdf-lib missing"));
    libPromise = import(url).then(function (mod) {
      var lib = mod.default || mod;
      var worker = root.getAttribute("data-dz-pdf-worker");
      if (worker && lib.GlobalWorkerOptions)
        lib.GlobalWorkerOptions.workerSrc = worker;
      return lib;
    });
    return libPromise;
  }

  function q(root, slot) {
    return root.querySelector("[data-dz-pdf-" + slot + "]");
  }

  function leftoverMessage() {
    return "Enter a page number";
  }

  function markPage(el, bad) {
    if (!el) return;
    if (el.setCustomValidity)
      el.setCustomValidity(bad ? leftoverMessage() : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  // kind: empty | invalid | ok. parseInt("2abc", 10) === 2, so leftover
  // junk is invalid — not a silent page jump. Out-of-[1,max] is
  // invalid (do not invent by clamping).
  function parsePage(val, max) {
    var raw = String(val == null ? "" : val).trim();
    if (!raw) return { kind: "empty" };
    if (!/^\d+$/.test(raw)) return { kind: "invalid" };
    var num = parseInt(raw, 10);
    if (!isFinite(num) || num < 1) return { kind: "invalid" };
    if (isFinite(max) && num > max) return { kind: "invalid" };
    return { kind: "ok", value: num };
  }

  function urlState() {
    var p = new URLSearchParams(location.search);
    var parsed = parsePage(p.get("dzpdf-page") || "", Infinity);
    return {
      page: parsed.kind === "ok" ? parsed.value : null,
      zoom: p.get("dzpdf-zoom") || null,
    };
  }

  function writeUrlState(page, zoom) {
    var p = new URLSearchParams(location.search);
    p.set("dzpdf-page", String(page));
    p.set("dzpdf-zoom", String(zoom));
    // replaceState, never pushState: Back stays page navigation.
    history.replaceState(
      history.state,
      "",
      location.pathname + "?" + p + location.hash,
    );
  }

  async function boot(root) {
    var status = q(root, "status");
    var viewer = q(root, "viewer");
    var say = function (t) {
      if (status) status.textContent = t;
    };
    if (!viewer) return;
    try {
      say("Loading document…");
      var lib = await loadLib(root);
      var src = root.getAttribute("data-dz-pdf-src");
      // #1556: open big PDFs on first-page bytes instead of prefetching the
      // whole file. disableAutoFetch stops PDF.js's background whole-file
      // pull, so large documents stream pages on demand over HTTP ranges.
      // PDF.js still fetches SMALL PDFs in one shot — it only issues range
      // GETs when the server-sent Content-Length exceeds its internal
      // threshold — so tiny documents pay no extra round-trips (size-gated by
      // PDF.js). The server route (serve_bytes) already advertises
      // Accept-Ranges + Content-Length, which is what PDF.js keys off.
      var doc = await lib.getDocument({
        url: src,
        disableAutoFetch: true,
        disableStream: false,
        rangeChunkSize: 65536,
      }).promise;

      var syncUrl = root.getAttribute("data-dz-pdf-state") === "url";
      var fromUrl = syncUrl ? urlState() : { page: null, zoom: null };
      var seeded = fromUrl.page;
      if (seeded == null) {
        var initParsed = parsePage(
          root.getAttribute("data-dz-pdf-initial-page") || "1",
          Infinity,
        );
        seeded = initParsed.kind === "ok" ? initParsed.value : 1;
      }
      var state = {
        page: Math.min(doc.numPages, Math.max(1, seeded)),
        // zoom: a number, or "fit" (fit-width, the default)
        zoom: fromUrl.zoom || "fit",
      };

      var pageCount = q(root, "page-count");
      if (pageCount) pageCount.textContent = "of " + doc.numPages;
      var pageInput = q(root, "page");
      var gen = 0;

      async function render() {
        var g = ++gen;
        var page = await doc.getPage(state.page);
        var base = page.getViewport({ scale: 1 });
        var scale =
          state.zoom === "fit"
            ? Math.max(0.1, (viewer.clientWidth - 16) / base.width)
            : parseFloat(state.zoom) || 1;
        state.renderedScale = scale;
        var viewport = page.getViewport({ scale: scale });
        var canvas = document.createElement("canvas");
        var ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = Math.floor(viewport.width) + "px";
        canvas.style.height = Math.floor(viewport.height) + "px";
        var ctx = canvas.getContext("2d");
        ctx.scale(ratio, ratio);
        await page.render({ canvasContext: ctx, viewport: viewport }).promise;
        if (g !== gen) return; // a newer render superseded this one
        viewer.replaceChildren(canvas);
        if (pageInput) pageInput.value = String(state.page);
        if (syncUrl) writeUrlState(state.page, state.zoom);
        say("");
        root.setAttribute("data-dz-pdf-ready", "true");
      }

      function go(page) {
        var target = Math.min(doc.numPages, Math.max(1, page || state.page));
        if (target === state.page) return;
        state.page = target;
        render();
      }

      function applyPageInput(normalize) {
        if (!pageInput) return;
        var parsed = parsePage(pageInput.value, doc.numPages);
        if (parsed.kind === "ok") {
          markPage(pageInput, false);
          go(parsed.value);
          if (normalize) pageInput.value = String(state.page);
          return parsed;
        }
        if (parsed.kind === "empty") {
          markPage(pageInput, false);
          if (normalize) pageInput.value = String(state.page);
          return parsed;
        }
        // leftover junk stays visible — must not vanish / revert
        markPage(pageInput, true);
        return parsed;
      }

      function rezoom(factor) {
        // step from the scale the last render actually used — this is
        // how "fit" resolves to a number when the user starts zooming
        var current = state.renderedScale || 1;
        state.zoom = String(Math.min(8, Math.max(0.25, current * factor)));
        render();
      }

      root.addEventListener("click", function (e) {
        if (e.target.closest("[data-dz-pdf-prev]")) go(state.page - 1);
        else if (e.target.closest("[data-dz-pdf-next]")) go(state.page + 1);
        else if (e.target.closest("[data-dz-pdf-zoom-in]")) rezoom(1.25);
        else if (e.target.closest("[data-dz-pdf-zoom-out]")) rezoom(0.8);
        else if (e.target.closest("[data-dz-pdf-fit-width]")) {
          state.zoom = "fit";
          render();
        }
      });
      if (pageInput) {
        pageInput.addEventListener("input", function () {
          var parsed = parsePage(pageInput.value, doc.numPages);
          markPage(pageInput, parsed.kind === "invalid");
        });
        pageInput.addEventListener("change", function () {
          applyPageInput(false);
        });
        pageInput.addEventListener(
          "blur",
          function () {
            var parsed = parsePage(pageInput.value, doc.numPages);
            if (parsed.kind === "empty") applyPageInput(true);
            else if (parsed.kind === "ok") applyPageInput(true);
            // leftover junk stays visible — must not vanish / revert
          },
          true,
        );
        pageInput.addEventListener("keydown", function (evt) {
          if (evt.key !== "Enter") return;
          evt.preventDefault();
          applyPageInput(false);
        });
      }

      // teardown for the mount sweep: swapping this viewer out must
      // release the PDF.js document (and its worker) — spec §7 cleanup.
      root._dzPdfCleanup = function () {
        gen++; // cancel any in-flight render
        try {
          doc.destroy();
        } catch (e) {
          /* already destroyed */
        }
      };

      await render();
    } catch (err) {
      say("Failed to load document.");
      root.setAttribute("data-dz-pdf-error", "true");
    }
  }

  function mount(root) {
    if (root._dzPdfMounted) return;
    root._dzPdfMounted = true;
    live.push(root);
    if (!("IntersectionObserver" in window)) {
      boot(root);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          io.disconnect();
          boot(root);
          return;
        }
      }
    });
    io.observe(root);
  }

  function mountAll(scope) {
    // release documents whose viewer left the DOM (htmx swaps)
    for (var i = live.length - 1; i >= 0; i--) {
      if (!live[i].isConnected) {
        if (live[i]._dzPdfCleanup) live[i]._dzPdfCleanup();
        live.splice(i, 1);
      }
    }
    var host = scope || document;
    var roots = Array.prototype.slice.call(
      host.querySelectorAll("[data-dz-pdf]"),
    );
    if (host.matches && host.matches("[data-dz-pdf]")) roots.push(host);
    roots.forEach(mount);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountAll(document);
    });
  } else {
    mountAll(document);
  }
  function onSettle(e) {
    mountAll((e.detail && e.detail.target) || document);
  }
  // dual-bound for htmx 4 (colon) and htmx <=2 (camelCase) consumers —
  // the package convention (see dz-grid.js).
  document.addEventListener("htmx:after:settle", onSettle);
  document.addEventListener("htmx:afterSettle", onSettle);
})();
