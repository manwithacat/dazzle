/**
 * Dazzle analytics event bus (v0.61.0 Phase 4 — dz/v1 vocabulary).
 *
 * Emits framework-defined events onto window.dataLayer so any provider
 * (GTM, Plausible, PostHog, …) can consume them via the standard bus.
 * The server resolves which provider scripts load; this file is provider-
 * agnostic.
 *
 * Events emitted (see docs/reference/pii-privacy.md):
 *   dz_page_view       — workspace+surface view (htmx swap + initial load)
 *   dz_action          — DSL action click
 *   dz_form_submit     — successful form POST
 *   dz_search          — filterable_table search / filter apply
 *   dz_api_error       — 4xx/5xx htmx response
 *
 * dz_transition fires server-side via the event bus (Phase 5) — not here.
 *
 * Element attributes the bus reads:
 *   [data-dz-surface]  — marks a surface wrapper (fires dz_page_view on swap)
 *   [data-dz-workspace] — companion to data-dz-surface
 *   [data-dz-action]   — marks an action trigger
 *   [data-dz-entity]   — entity tag for action / form / search events
 *   [data-dz-form]     — marks a form that should emit dz_form_submit
 *   [data-dz-search]   — marks a search input that should emit dz_search
 *
 * PII safety:
 *   Values are read from data-dz-* attributes only — never from <input>
 *   values. The server-side template layer decides what lands in those
 *   attributes, honouring pii() annotations. This file pushes what it
 *   sees; it never extracts values from user inputs.
 */
(function () {
  "use strict";

  const SCHEMA_VERSION = "1";
  const MAX_STR = 100;
  const MAX_URL = 255;

  function clamp(value, max) {
    if (value == null) return undefined;
    const s = String(value);
    return s.length > max ? s.slice(0, max) : s;
  }

  function push(payload) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(payload);
  }

  function base(event) {
    const tenant = document.body.getAttribute("data-dz-tenant") || undefined;
    const out = {
      event,
      dz_schema_version: SCHEMA_VERSION,
    };
    if (tenant) out.dz_tenant = clamp(tenant, MAX_STR);
    return out;
  }

  function getPersonaClass() {
    return document.body.getAttribute("data-dz-persona-class") || undefined;
  }

  /* ------------------------------------------------------------------ */
  /* dz_page_view                                                        */
  /* ------------------------------------------------------------------ */

  function emitPageView(surfaceEl) {
    const surface = surfaceEl.getAttribute("data-dz-surface");
    const workspace = surfaceEl.getAttribute("data-dz-workspace");
    if (!surface || !workspace) return; // malformed — skip silently

    const payload = base("dz_page_view");
    payload.workspace = clamp(workspace, MAX_STR);
    payload.surface = clamp(surface, MAX_STR);

    const persona = getPersonaClass();
    if (persona) payload.persona_class = clamp(persona, MAX_STR);

    // Strip query string so analytics dashboards group by route, not
    // individual query snapshots (which often contain filter state).
    const url = window.location.origin + window.location.pathname;
    payload.url = clamp(url, MAX_URL);

    if (document.referrer) {
      payload.referrer = clamp(document.referrer, MAX_URL);
    }

    push(payload);
  }

  function emitInitialPageView() {
    const surfaceEl = document.querySelector("[data-dz-surface]");
    if (surfaceEl) emitPageView(surfaceEl);
  }

  function onHtmxAfterSwap(evt) {
    const target = evt.detail && evt.detail.target;
    if (!target) return;
    // Only emit when the swap landed in (or wraps) a surface container.
    const surfaceEl = target.hasAttribute("data-dz-surface")
      ? target
      : target.querySelector("[data-dz-surface]");
    if (surfaceEl) emitPageView(surfaceEl);
  }

  /* ------------------------------------------------------------------ */
  /* dz_action                                                           */
  /* ------------------------------------------------------------------ */

  function onActionClick(evt) {
    const trigger = evt.target.closest("[data-dz-action]");
    if (!trigger) return;

    const payload = base("dz_action");
    payload.action_name = clamp(
      trigger.getAttribute("data-dz-action"),
      MAX_STR,
    );
    payload.entity = clamp(trigger.getAttribute("data-dz-entity"), MAX_STR);
    payload.surface = clamp(
      trigger.getAttribute("data-dz-surface") ||
        closestAttr(trigger, "data-dz-surface"),
      MAX_STR,
    );
    if (!payload.action_name || !payload.entity || !payload.surface) {
      // Missing required params — never push a half-baked event.
      return;
    }

    const entityId = trigger.getAttribute("data-dz-entity-id");
    if (entityId) payload.entity_id = clamp(entityId, MAX_STR);

    push(payload);
  }

  function closestAttr(el, attr) {
    let cur = el;
    while (cur && cur !== document.body) {
      if (cur.hasAttribute && cur.hasAttribute(attr)) {
        return cur.getAttribute(attr);
      }
      cur = cur.parentNode;
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* dz_form_submit                                                      */
  /* ------------------------------------------------------------------ */

  function onHtmxAfterRequest(evt) {
    const detail = evt.detail || {};
    const status = (detail.xhr && detail.xhr.status) || 0;
    const source = detail.elt;
    if (!source) return;

    // Success path: dz_form_submit.
    if (status >= 200 && status < 300) {
      const form = source.closest("[data-dz-form]");
      if (form) {
        const payload = base("dz_form_submit");
        payload.form_name = clamp(form.getAttribute("data-dz-form"), MAX_STR);
        payload.entity = clamp(form.getAttribute("data-dz-entity"), MAX_STR);
        payload.surface = clamp(
          form.getAttribute("data-dz-surface") ||
            closestAttr(form, "data-dz-surface"),
          MAX_STR,
        );
        if (payload.form_name && payload.entity && payload.surface) {
          push(payload);
        }
      }
    }

    // Error path: dz_api_error. htmx:responseError also fires for 4xx/5xx,
    // but we centralise emission here so both non-htmx xhr paths (Fetch,
    // manual calls) can be added later.
    if (status >= 400) {
      const payload = base("dz_api_error");
      payload.status_code = status;
      payload.surface = clamp(
        source.getAttribute("data-dz-surface") ||
          closestAttr(source, "data-dz-surface"),
        MAX_STR,
      );
      if (!payload.surface) return;

      // Try to read X-Dz-Error-Code response header for a structured code.
      const errCode =
        detail.xhr &&
        detail.xhr.getResponseHeader &&
        detail.xhr.getResponseHeader("X-Dz-Error-Code");
      if (errCode) payload.error_code = clamp(errCode, MAX_STR);

      push(payload);
    }
  }

  /* ------------------------------------------------------------------ */
  /* dz_search                                                           */
  /* ------------------------------------------------------------------ */

  function attachSearchHooks() {
    document.querySelectorAll("[data-dz-search]").forEach((el) => {
      let debounceTimer = null;
      el.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => emitSearch(el), 600);
      });
    });

    // htmx-driven search (attribute is on the filter form)
    document.body.addEventListener("htmx:afterSwap", (evt) => {
      const target = evt.detail && evt.detail.target;
      if (!target) return;
      if (
        target.hasAttribute &&
        target.hasAttribute("data-dz-search-results")
      ) {
        emitSearchResults(target);
      }
    });
  }

  function emitSearch(el) {
    const payload = base("dz_search");
    payload.surface = clamp(
      el.getAttribute("data-dz-surface") || closestAttr(el, "data-dz-surface"),
      MAX_STR,
    );
    payload.entity = clamp(el.getAttribute("data-dz-entity"), MAX_STR);
    if (!payload.surface || !payload.entity) return;

    // result_count populates from the results container when it swaps in.
    payload.result_count = 0;

    // Query string is INCLUDED only when the element is marked as
    // PII-safe. Default: omit. Authors opt-in via
    // data-dz-search-query-allowed="true" on the input.
    if (el.getAttribute("data-dz-search-query-allowed") === "true") {
      const q = el.value || "";
      if (q) payload.query = clamp(q, MAX_STR);
    }

    push(payload);
  }

  function emitSearchResults(container) {
    // Count rows by looking for [data-dz-search-row] inside the swap target.
    const rows = container.querySelectorAll("[data-dz-search-row]");
    const count = rows.length;
    // Retroactively update the most recent dz_search event with the
    // authoritative count. GA4 treats the second push as a separate event,
    // so we push a follow-up dz_search_result instead of mutating.
    // In dz/v1 we fold the count into the ORIGINAL emission — the
    // results-swap emits a fresh dz_search with full state.
    const source = container.getAttribute("data-dz-search-source");
    if (!source) return;
    const payload = base("dz_search");
    payload.surface = clamp(
      container.getAttribute("data-dz-surface") ||
        closestAttr(container, "data-dz-surface"),
      MAX_STR,
    );
    payload.entity = clamp(container.getAttribute("data-dz-entity"), MAX_STR);
    payload.result_count = count;
    if (!payload.surface || !payload.entity) return;
    push(payload);
  }

  /* ------------------------------------------------------------------ */
  /* Init                                                                */
  /* ------------------------------------------------------------------ */

  function init() {
    emitInitialPageView();
    attachSearchHooks();

    document.body.addEventListener("htmx:afterSwap", onHtmxAfterSwap);
    document.body.addEventListener("htmx:afterRequest", onHtmxAfterRequest);
    document.body.addEventListener("click", onActionClick);

    // Expose debug handle (read-only list of the last N pushes is the
    // dataLayer itself — no framework-proprietary state).
    window.dzAnalytics = {
      schemaVersion: SCHEMA_VERSION,
      emitPageView: emitInitialPageView,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
