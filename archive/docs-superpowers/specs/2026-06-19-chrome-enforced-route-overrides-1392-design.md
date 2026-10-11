> **SUPERSEDED (2026-06-19)** by `2026-06-19-route-override-response-contract-1392-design.md` — the chrome-wrap is reframed as one consumer of a declared route-override **response contract** (`# dazzle:returns page|fragment|partial|json`), so islands/novel full-bleed UX are a declared `page` kind (never refused) and the RBAC line stays orthogonal+mandatory. Kept for history.

# Chrome-enforced route-overrides (#1392 item 2a) — Design

**Status:** Approved (2026-06-19). The final remaining slice of #1392 ("let custom renderers /
route-overrides opt back into the framework's structural guarantees"). Items 1 (output
contract, v0.82.66), 4 (conformance harness, v0.82.77), and 3 (emitted-target verification,
v0.83.22) shipped. This is **item 2**, scoped to **2a** (route-override chrome-wrap). The
related sub-problem 2b (hx-boost-into-`<body>` targeting guard) is explicitly deferred.

## Problem

A `# dazzle:route-override` returns whatever its handler returns — `_wrap_with_policy_gate`
adds the RBAC gate (#1126) but nothing wraps the output in the app shell. So an override can
return a full `<!doctype html>` document that bypasses the shell, and a top-level `hx-boost`
navigation swaps it into `<body>`, deleting the sidebar/nav. There is no way for a handler to
say "wrap me in chrome; I'll return inner HTML" and have the framework enforce it.

Custom `render:`/`mode: custom` *surfaces* are NOT the vector — they render through the page
route, which already chromes them via `dispatch_render_page`. The escape is route-overrides.

## Goal

Let a route-override declare `# dazzle:chrome` to have its returned **inner HTML** wrapped in
the app shell, and **refuse** a full-document return — so a custom handler cannot escape the
shell. Opt-in: no header ⇒ today's behaviour (handler owns its full response).

## Non-goals (YAGNI / deferred)

- **2b** (hx-boost top-level nav swapping inner HTML into `<body>`) — a different mechanism
  (HTMX `hx-target` conventions); separate pass.
- **CTA retargeting** (the issue's "retarget its CTAs to `#main-content`") — the handler owns
  its inner HTML's `hx-target`s; the framework owns the shell. Forcing HTML surgery isn't
  needed for "can't escape the shell." Possible follow-on.
- Chrome-wrapping `mode: custom` *surfaces* — already chromed via the page route.

## Architecture — three units

### 1. `build_app_page_context(request) -> PageContext` (prerequisite extraction)

The nav/persona/tenant-config `PageContext` assembly currently **inline** in `_page_handler`
(`src/dazzle/page/runtime/page_routes.py` ~L2376 — `_resolve_nav_model` + `PageContext(...)` +
chrome css/js/theme/favicon resolution) is extracted into a reusable, request-only function.
`_page_handler` is refactored to call it — **behavior-preserving** (same `PageContext`), pinned
by the existing page-render tests + an extraction-parity test. This is the architecture-material
change; everything else builds on it. It returns the `PageContext` plus the chrome asset tuples
(css_links/js_scripts/theme/favicon/font_preconnect) the `dispatch_render_page` call needs.

### 2. `# dazzle:chrome` marker

A scannable header alongside `# dazzle:route-override` (read at discovery, like
`# dazzle:implements`/`# dazzle:emits`). New `_CHROME_RE` in `route_overrides.py`;
`RouteOverrideDescriptor.wants_chrome: bool = False`. No IR (runtime/tooling).

### 3. `_wrap_with_chrome` dispatch wrapper

Applied at route-override mount when `wants_chrome`, composed **outermost** of
`_wrap_with_policy_gate` (RBAC runs first, then chrome the result). Behaviour:

- **HTMX-aware.** For an HTMX request targeting the content region (`HX-Request` header
  present), return the handler's **inner HTML** as-is (it swaps into `#main-content` — no
  chrome). For a full-page navigation (no `HX-Request`, incl. a top-level `hx-boost` nav),
  call `build_app_page_context(request)` + `dispatch_render_page(ctx, inner_html, chrome=True)`
  to return the chromed document. This is the inner-vs-full split the page handler already
  makes, so an hx-boost nav gets a full chromed document and can't delete the sidebar.
- **Refuse loud.** If the handler returns a **full document** (`<!doctype`/`<html` sniff on the
  rendered body) while `# dazzle:chrome` is declared, raise a typed error (500 with a pointed
  message: handler declared `# dazzle:chrome` but returned a full document — return inner HTML;
  the framework owns the shell). Mirrors item 1's `_assert_custom_render_output` discipline.
- The handler's returned `Response` status / headers / content-type are honoured for the inner
  case; the chromed case returns `HTMLResponse`. Non-HTML responses (JSON, redirects, files)
  pass through unwrapped (chrome only applies to HTML bodies).

## Model-driven failure-modes check (per CLAUDE.md)

1. **Failure mode risked?** *Hidden side-channel semantics* — a custom handler's full-document
   escape from the shell. We **reduce** it: chrome becomes a declared, enforced wrap.
2. **Detector if wrong?** The refuse-loud assertion (live at request time) + the statically
   scannable `# dazzle:chrome` marker.
3. **Live or documented?** Live — request-time enforcement, not just docs.
4. **Traceable to AppSpec?** The override + its `# dazzle:chrome` declaration is the source.
5. **Preserves auth/Postgres/UI semantics?** Preserves — composes outside `_wrap_with_policy_gate`
   (RBAC unchanged); UI gains shell consistency. No session/data-layer change.

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `build_app_page_context(request)` | Reusable nav/persona PageContext + chrome assets | nav model, auth ctx |
| `route_overrides._CHROME_RE` + `wants_chrome` | Scan `# dazzle:chrome` | discovery |
| `_wrap_with_chrome` | HTMX-aware shell wrap + refuse-loud full-doc | build_app_page_context, dispatch_render_page |
| mount wiring | Apply chrome wrap when `wants_chrome` (outside policy gate) | route-override registration |

## Testing

- **Extraction parity:** `build_app_page_context(request)` yields the same `PageContext` the
  inline `_page_handler` path produced (and the existing page-render tests stay green).
- **Marker:** `# dazzle:chrome` → `wants_chrome=True`; absent → `False`.
- **Wrapper:** an `HX-Request` returns the handler's inner HTML unchromed; a full-page request
  returns a chromed document containing the inner HTML + the nav shell; a full-document return
  from a chrome-declared handler raises the typed error; a non-HTML response passes through.
- **Composition:** RBAC (`_wrap_with_policy_gate`) still runs when both are present.
- **Dogfood:** a fixture route-override declares `# dazzle:chrome`, returns inner HTML, and
  renders chromed.

## Implementation phases (for writing-plans)

- **P1 — extract `build_app_page_context`** from `_page_handler` (behavior-preserving refactor +
  parity test; the architecture-material prerequisite).
- **P2 — `# dazzle:chrome` marker** scan → `RouteOverrideDescriptor.wants_chrome` + tests.
- **P3 — `_wrap_with_chrome`** (HTMX-aware + refuse-loud), wired at mount outside the policy gate
  + tests.
- **P4 — dogfood + docs + ship + close #1392** (item 2 completes #1392; items 1/3/4 already
  shipped).
