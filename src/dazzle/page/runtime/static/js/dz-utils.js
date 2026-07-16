/*
 * dz-utils.js — Dazzle's vanilla runtime helpers.
 *
 * The live remainder of dz-alpine.js, DELETED in Tier F4e (2026-07-06)
 * when the last Alpine island converted and the vendored Alpine runtime
 * (+persist/anchor/collapse/focus plugins, ~100KB) left the bundle:
 *   - haptic feedback (window.dzHaptic, #958)
 *   - toast dispatch + CSV download (window.dz.toast / dz.downloadCsv)
 *   - ref-filter select population (window.dz.filterRefSelect, #973 —
 *     auto-mounted on select[data-ref-api], replacing the old x-init)
 *   - row_action delegated POST handler (#1233)
 * The four x-* directives (flip/pull-to-refresh/swipe/optimistic) were
 * removed with Alpine: zero mounts fleet-wide (git history has the
 * implementations if a consumer asks for a vanilla rebuild).
 */

// ── Haptic feedback (#958 cycle 5) ──────────────────────────────────
//
// Opt-in haptic feedback via the Vibration API. Activated by the
// presence of `<meta name="dz-haptic" content="on">` in the page —
// emitted by base.html when `[ui] haptic = true` in dazzle.toml.
//
// Auto-fires on:
//   - showToast(success) → tap pattern (single 10ms pulse)
//   - showToast(error)   → error pattern (two short pulses)
//   - swipe-left / swipe-right → tap pattern
//   - htmx:after:request with status >= 400 → error pattern
//
// Silently no-ops when navigator.vibrate is unsupported (most
// desktop browsers), when the meta tag is absent, OR when the user
// has prefers-reduced-motion set (vibration is a motion adjacent
// signal and the same accessibility intent applies).
//
// Exposed as `window.dzHaptic` for adopters who want manual
// triggers (e.g. inside an Alpine handler).
(function () {
  const meta = document.querySelector('meta[name="dz-haptic"]');
  const enabled =
    meta &&
    meta.getAttribute("content") === "on" &&
    typeof navigator !== "undefined" &&
    typeof navigator.vibrate === "function";

  const reduce =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const vibrate = (pattern) => {
    if (!enabled || reduce) return false;
    try {
      return navigator.vibrate(pattern);
    } catch {
      return false;
    }
  };

  window.dzHaptic = {
    enabled: !!enabled && !reduce,
    tap: () => vibrate(10),
    success: () => vibrate(10),
    error: () => vibrate([20, 40, 20]),
    warning: () => vibrate([10, 30, 10]),
    raw: vibrate,
  };

  if (!enabled || reduce) return;

  // Auto-wire to standard event names. document.body may not exist
  // yet when this script runs — use document and let bubbling carry.
  document.addEventListener("showToast", (e) => {
    const detail = e && e.detail;
    if (detail && detail.type === "error") {
      window.dzHaptic.error();
    } else {
      window.dzHaptic.success();
    }
  });
  document.addEventListener("swipe-left", () => window.dzHaptic.tap());
  document.addEventListener("swipe-right", () => window.dzHaptic.tap());
  document.addEventListener("htmx:after:request", (e) => {
    const xhr = e && e.detail && e.detail.ctx && e.detail.ctx.response;
    if (xhr && xhr.status >= 400) window.dzHaptic.error();
  });
})();

(function () {
  "use strict";
  // ── Client toast dispatch + CSV download (window.dz utilities) ─────
  // Global toast function (backward compat with dz.toast). Accepts either
  // (message, type) or a single detail object { message, type?, title?, actions? }
  // so callers can use structured slots without clobbering the dz-toast host.
  window.dz = window.dz || {};
  window.dz.toast = (message, type = "info") => {
    const detail =
      message && typeof message === "object"
        ? message
        : { message, type };
    const el = document.getElementById("dz-toast");
    if (el) el.dispatchEvent(new CustomEvent("toast", { detail }));
    else
      document.dispatchEvent(new CustomEvent("showToast", { detail }));
  };

  /**
   * Download a CSV export via fetch + Blob (v0.61.2, #862).
   *
   * `<a download>` is ignored by Safari for same-origin responses with
   * `Content-Type: text/csv` — Safari treats the navigation as a document
   * load and renders the CSV inline, losing the user's workspace context.
   * The server-side `Content-Disposition: attachment` header is set
   * correctly but Safari honours its own heuristic over the header in
   * this case.
   *
   * This helper:
   *   1. Fetches the endpoint with same-origin credentials.
   *   2. Converts the response to a Blob (any Content-Type works).
   *   3. Creates a transient object-URL + synthetic <a download> element.
   *   4. Triggers a programmatic click (always a download, never a nav).
   *   5. Revokes the URL on next tick to free memory.
   *
   * Errors surface via toast + console — callers don't need to wrap.
   */
  window.dz.downloadCsv = async (endpoint, filename) => {
    const url = endpoint.includes("?")
      ? endpoint + "&format=csv"
      : endpoint + "?format=csv";
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        window.dz.toast(
          "CSV export failed: " + response.status + " " + response.statusText,
          "error",
        );
        return;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || "export.csv";
      // Appending to body is required on some browsers before click() works.
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Revoke on next tick so the browser has time to begin the download.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (err) {
      window.dz.toast("CSV export failed: network error", "error");
      console.error("[dz.downloadCsv]", err);
    }
  };
})();

// ── Ref-filter select population (#973) ─────────────────────────────
//
// Fetches the referenced entity's options from data-ref-api and
// populates the <select>, pre-selecting data-selected-value. Written
// so idiomorph never sees client-mutated attributes on morphable
// nodes.
//
// "remove the surface idiomorph trips on" rather than "make idiomorph
// understand Alpine."
//
// Reads two data-* attributes from the <select>:
//   - data-ref-api: API endpoint (e.g. /clients) to fetch options from
//   - data-selected-value: the persisted filter value to pre-select
//
// Both are HTML-escaped server-side (no tojson-in-attr footgun).
window.dz = window.dz || {};
window.dz.filterRefSelect = function (selectEl) {
  if (!selectEl || selectEl.tagName !== "SELECT") return;
  const refApi = selectEl.dataset.refApi;
  if (!refApi) return;
  const selectedValue = selectEl.dataset.selectedValue || "";
  // #973 (round 2): wire AbortController to both htmx:before:swap and
  // pagehide. Round 1 only checked `document.body.contains(selectEl)`
  // in .catch — that worked for in-page htmx swaps but not for full
  // browser navigation (Playwright `page.goto`, link clicks, form
  // submits). On full nav the fetch rejects with `TypeError: Failed
  // to fetch` BEFORE the element leaves the DOM, so the contains-
  // check fired too early and the warn still logged.
  //
  // The robust discriminator is an explicit AbortController. We trip
  // it on:
  //   - htmx:before:swap (htmx is about to morph the DOM under us)
  //   - pagehide (full browser navigation, also covers BFCache)
  // Both fire BEFORE the fetch is cancelled, so the rejection arrives
  // as a known AbortError we can swallow cleanly.
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  window.addEventListener("htmx:before:swap", onAbort, { once: true });
  window.addEventListener("pagehide", onAbort, { once: true });

  fetch(refApi + "?page_size=100", {
    headers: { Accept: "application/json" },
    signal: controller.signal,
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const items = data.items || [];
      const display = (item) => {
        return (
          item.__display__ ||
          item.name ||
          item.company_name ||
          ((item.first_name || "") + " " + (item.last_name || "")).trim() ||
          item.title ||
          item.label ||
          item.email ||
          item.id ||
          ""
        );
      };
      const fragment = document.createDocumentFragment();
      for (const item of items) {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = display(item);
        if (String(item.id) === String(selectedValue)) {
          opt.selected = true;
        }
        fragment.appendChild(opt);
      }
      selectEl.appendChild(fragment);
    })
    .catch((err) => {
      // Explicit AbortError from our controller — silent. Covers both
      // htmx swap and full-browser-nav cancellation paths.
      if (err && err.name === "AbortError") return;
      // Defense-in-depth: if the element is gone (e.g. ancestor
      // removed without firing one of our abort signals), still
      // swallow.
      if (!document.body.contains(selectEl)) return;
      console.warn("Filter ref-entity load failed for", refApi, ":", err);
    })
    .finally(() => {
      // Detach listeners — listener accumulation across many filter
      // dropdowns on one page would otherwise grow unbounded. After
      // pagehide this is moot (page going away) but harmless.
      window.removeEventListener("htmx:before:swap", onAbort);
      window.removeEventListener("pagehide", onAbort);
    });
};

// Auto-mount: populate every ref-filter select at load and after htmx
// settles (replaces the per-element Alpine `x-init` mounts).
(function () {
  "use strict";
  function mountRefSelects(scope) {
    var host = scope || document;
    var nodes = Array.prototype.slice.call(
      host.querySelectorAll("select[data-ref-api]"),
    );
    if (host.matches && host.matches("select[data-ref-api]")) nodes.push(host);
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i]._dzRefMounted) continue;
      nodes[i]._dzRefMounted = true;
      window.dz.filterRefSelect(nodes[i]);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountRefSelects(document);
    });
  } else {
    mountRefSelects(document);
  }
  document.body &&
    document.body.addEventListener("htmx:after:settle", function (e) {
      mountRefSelects((e.detail && e.detail.target) || document);
    });
})();

/* ------------------------------------------------------------------ */
/* #1233 — row_action client handler                                  */
/* ------------------------------------------------------------------ */
/**
 * Delegated click handler for [data-dz-row-action] buttons emitted by
 * `_render_row_action_button` (workspace_card_bodies.py). The button
 * carries:
 *   data-dz-row-action       — the action_id (declared surface action)
 *   data-dz-row-args         — JSON payload of bound row values
 *   data-dz-row-action-url   — POST endpoint resolved server-side from
 *                              the appspec's CREATE surfaces (#1233)
 *
 * When data-dz-row-action-url is present, POST the JSON payload via
 * htmx.ajax so CSRF + redirect/swap behaviour matches the rest of the
 * HTMX-driven runtime. When missing (no matching CREATE surface in the
 * AppSpec), emit a console.warn and no-op — preserves the pre-#1233
 * shape rather than 404ing.
 */
document.addEventListener("click", function (evt) {
  const btn = evt.target.closest("[data-dz-row-action]");
  if (!btn) return;
  // Don't double-fire if a parent already handled this (e.g. surface
  // action machinery hijacks the same data attribute).
  if (evt.defaultPrevented) return;

  const url = btn.getAttribute("data-dz-row-action-url") || "";
  const actionId = btn.getAttribute("data-dz-row-action") || "";
  if (!url) {
    console.warn(
      "[dz] row_action '" +
        actionId +
        "' has no resolved URL " +
        "(data-dz-row-action-url missing) — declare a matching CREATE " +
        "surface in the DSL or check the surface name.",
    );
    return;
  }

  let args = {};
  const argsRaw = btn.getAttribute("data-dz-row-args");
  if (argsRaw) {
    try {
      args = JSON.parse(argsRaw);
    } catch (parseErr) {
      console.warn(
        "[dz] row_action '" +
          actionId +
          "': data-dz-row-args is not " +
          "valid JSON; sending empty body. (" +
          parseErr.message +
          ")",
      );
    }
  }

  evt.preventDefault();
  btn.classList.add("dz-loading");
  btn.disabled = true;

  // htmx.ajax composes CSRF + drives swap. Settle handler restores the
  // button so subsequent clicks fire (no-op rather than disabled forever).
  const htmx = window.htmx;
  if (!htmx || typeof htmx.ajax !== "function") {
    console.warn(
      "[dz] row_action '" +
        actionId +
        "': htmx is not loaded; " +
        "cannot POST. Ensure the runtime bundle is loaded.",
    );
    btn.classList.remove("dz-loading");
    btn.disabled = false;
    return;
  }

  htmx
    .ajax("POST", url, {
      values: args,
      // No target/swap — server typically responds 303 → GET, which
      // htmx follows. If the response is HTML, default swap into body.
      target: "body",
      swap: "none",
    })
    .then(function () {
      btn.classList.remove("dz-loading");
      btn.disabled = false;
    })
    .catch(function (ajaxErr) {
      console.warn(
        "[dz] row_action '" + actionId + "' POST to " + url + " failed: ",
        ajaxErr,
      );
      btn.classList.remove("dz-loading");
      btn.disabled = false;
    });
});
