# Route-override response contract + authoring guardrails (#1392 item 2) — Design

**Status:** Approved (2026-06-19). The final remaining slice of #1392 ("let custom renderers /
route-overrides opt back into the framework's structural guarantees"). Items 1 (output
contract, v0.82.66), 4 (conformance harness, v0.82.77), 3 (emitted-target verification,
v0.83.22) shipped. This **supersedes** the narrower chrome-only spec
(`2026-06-19-chrome-enforced-route-overrides-1392-design.md`): chrome-wrap is reframed as one
consumer of a declared **response contract**.

## Problem

A `# dazzle:route-override` has **no declared response contract**. The framework can't tell
whether the handler returns a full HTML page, an HTML fragment (inner content for the app
shell's `#main-content`), a raw HTML partial (a targeted HTMX swap), JSON, a file, or a
redirect — it sniffs or ignores. That single gap is the root of three symptoms:

- **Chrome escape / inconsistency.** An override can return a full `<!doctype>` document that
  bypasses the app shell; a top-level `hx-boost` nav swaps it into `<body>`, deleting the
  sidebar. There's no way to say "wrap me in chrome; I return inner HTML" and have it enforced.
- **Novel-UX vs escape is indistinguishable.** A deliberately full-bleed UI (a kiosk view, a
  fullscreen canvas, a page hosting client-side `island` components) returning a full document
  looks identical to a handler that *forgot* the shell. Punishing the full document would punish
  legitimate novel UI.
- **Opaque responses** (the #1421/#1422 lesson). With no declared shape, response handling and
  failures are sniffed/collapsed rather than reasoned about.

(`island` is a separate construct — client-side JS embedded *inside* a chromed page via a
`data-island-props` placeholder + `fallback`; it is not itself a chromeless route. The novel
full-bleed case is a route-override that renders such a UI.)

## Goal

Give route-overrides a **declared response contract** so the framework can wrap fragments in
chrome, leave declared full-bleed pages alone, and enforce *consistency* — and give authoring
agents a crisp guardrail model: **RBAC is mandatory; response shape + chrome are a declared
choice.**

## The guardrail model (the heart of this work)

Two lines, communicated explicitly to authoring agents (docs + counter-prior + Agent Guidance):

- **RBAC is the line — mandatory, not a choice.** Any domain-touching route declares
  `# dazzle:implements <Entity>.<op> via <param>` or fails `dazzle rbac routes --strict`
  (#1420/ADR-0040 — already enforced). Novel UI does not get to skip permit/scope.
- **Response shape + chrome are your declared choice — novel UI welcome.** Declare
  `# dazzle:returns <kind>` to say what you return and whether you live in the app shell. The
  framework enforces *consistency with what you declared*, never a particular UX.

## Design — four units + a guidance deliverable

### 1. `build_app_page_context(request)` (prerequisite extraction)

The nav/persona/tenant-config `PageContext` assembly currently **inline** in `_page_handler`
(`src/dazzle/page/runtime/page_routes.py` ~L2376 — `_resolve_nav_model` + `PageContext(...)` +
chrome css/js/theme/favicon resolution) is extracted into a reusable, request-only function
returning the `PageContext` **and** the chrome asset tuples (`css_links`, `js_scripts`, `theme`,
`favicon`, `font_preconnect`) that `dispatch_render_page` needs. `_page_handler` is refactored to
call it — **behavior-preserving**, pinned by the existing page-render tests + a parity test. The
architecture-material change everything else builds on.

### 2. `# dazzle:returns <kind>` marker

A scannable header alongside `# dazzle:route-override` (read at discovery, like
`# dazzle:implements`/`# dazzle:emits`). New `_RETURNS_RE` in `route_overrides.py`;
`RouteOverrideDescriptor.returns_kind: str | None` (None = undeclared). Closed vocabulary:

| kind | meaning | framework action |
|------|---------|------------------|
| `fragment` | inner HTML that lives in the app shell | **shell-wrap** (HTMX-aware, ↓) |
| `partial` | raw HTML for a targeted HTMX swap (not `#main-content`) | serve as-is (no chrome) |
| `page` | a full HTML document (novel/full-bleed UX, island host, kiosk) | serve as-is — **declared, never refused** |
| `json` | a JSON API response | pass through |

`redirect`/`file` responses pass through implicitly (not HTML; no declaration needed). An
unknown kind is a discovery-time error. **The kind encodes chrome** — only `fragment` is
wrapped; there is no separate `chrome:` attribute.

### 3. `_wrap_with_response_contract` dispatch wrapper

Applied at route-override mount, composed **outside** `_wrap_with_policy_gate` (RBAC runs first,
then the contract wraps the result). By `returns_kind`:

- **`fragment`** — HTMX-aware: for an `HX-Request` (swaps into `#main-content`) return the
  handler's inner HTML as-is; for a full-page navigation call `build_app_page_context(request)` +
  `dispatch_render_page(ctx, inner_html, chrome=True)` → a full chromed document. So an hx-boost
  top-level nav can't delete the sidebar. *Consistency:* a full `<!doctype>`/`<html>` body → a
  typed error ("declared `fragment`, returned a full page — return inner HTML; the shell is the
  framework's").
- **`partial`** — serve the handler's HTML as-is (no chrome). *Consistency:* full-doc body → the
  same typed error.
- **`page`** — serve the full document as-is. The novel-UX / island-host / full-bleed case;
  **never refused** (this resolves the islands concern). No consistency assertion (a `page`
  *is* the full response).
- **`json`** — pass through (light check: warn if the body sniffs as HTML, since that contradicts
  a `json` declaration).
- **undeclared (`None`)** — pass through (today's behaviour) + the nudge ↓.

Only HTML bodies are inspected; non-HTML `Response`s (JSON/redirect/file) pass through. Handler
status/headers are honoured for the as-is kinds; the chromed `fragment` case returns
`HTMLResponse`.

### 4. Runtime advisory nudge (#1422 fail-loud style)

When an **undeclared** route-override under the `/app` prefix returns `text/html` on a full-page
(non-`HX-Request`) response, log a **one-time** advisory (keyed by route path, like the #1413
renderer signpost): "route-override `<path>` returns HTML but declares no `# dazzle:returns` —
declare `page` (full-bleed), `fragment` (live in the app shell), or `partial` (raw HTMX swap) so
the framework knows whether to chrome it." Steers agents toward declared intent **without
blocking novel UI**. Never fires for JSON/file/redirect, non-`/app`, or HTMX responses.

### 5. Authoring-guardrail deliverable (first-class)

- **`docs/counter-priors/` entry** (e.g. `custom-route-undeclared-response.md`) — the pathology
  "a route-override returns HTML with no declared shape / no RBAC binding," with the right shape
  (`# dazzle:route-override` + `# dazzle:implements` + `# dazzle:returns`). Ingested by the KG so
  `knowledge counter_prior` surfaces it when an agent writes a custom route.
- **`docs/reference/` section** — the route-override declaration vocabulary (`route-override`,
  `implements`, `emits`, `returns`) + the two-line guardrail model.
- **CHANGELOG `### Agent Guidance`** bullet carrying the model.

## Model-driven failure-modes check (per CLAUDE.md)

1. **Failure mode risked?** *Hidden side-channel semantics* — an undeclared custom-handler
   response. We **reduce** it: the response shape is declared + consistency-enforced; the RBAC
   line is unchanged + orthogonal.
2. **Detector if wrong?** The consistency assertion (live), the scannable marker, the advisory
   nudge, and (RBAC) the existing matrix gate.
3. **Live or documented?** Live — request-time enforcement + the authoring counter-prior.
4. **Traceable to AppSpec?** The override's declared `returns`/`implements` headers are the source.
5. **Preserves auth/Postgres/UI semantics?** Preserves — composes outside the RBAC gate; UI gains
   declared shell consistency; no session/data change. Novel UI is *enabled* (declared `page`),
   not blocked.

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `build_app_page_context(request)` | Reusable nav/persona PageContext + chrome assets | nav model, auth ctx |
| `route_overrides._RETURNS_RE` + `returns_kind` | Scan `# dazzle:returns` | discovery |
| `_wrap_with_response_contract` | Per-kind wrap/serve/refuse + consistency | build_app_page_context, dispatch_render_page |
| advisory nudge | One-time log for undeclared `/app` HTML | wrapper |
| guardrail docs/counter-prior | The RBAC-vs-choice authoring model | — |

## Testing

- **Extraction parity:** `build_app_page_context(request)` ≡ the inline `_page_handler` path
  (existing page-render tests stay green + a parity test).
- **Marker:** each kind → `returns_kind`; unknown kind → discovery error; absent → `None`.
- **Wrapper per kind:** `fragment` returns inner HTML on `HX-Request` and a chromed document on a
  full-page request; `partial` raw; `page` as-is (full doc allowed); `json` passthrough; a
  `fragment`/`partial` handler returning a full doc raises the typed error.
- **Nudge:** an undeclared `/app` HTML override logs exactly one advisory; JSON/HTMX/non-`/app`
  do not.
- **Composition:** RBAC (`_wrap_with_policy_gate`) still runs with the contract wrapper present.
- **Counter-prior drift:** the new counter-prior passes `test_counter_priors_drift.py`.
- **Dogfood:** a fixture route-override declares `# dazzle:returns fragment`, returns inner HTML,
  renders chromed; another declares `page` and serves full-bleed un-refused.

## Implementation phases (for writing-plans)

- **P1** — extract `build_app_page_context` from `_page_handler` (behavior-preserving + parity).
- **P2** — `# dazzle:returns` marker scan → `returns_kind` (+ unknown-kind error) + tests.
- **P3** — `_wrap_with_response_contract` (per-kind + consistency) + the advisory nudge, wired at
  mount outside the policy gate + tests.
- **P4** — guardrail deliverable (counter-prior + reference docs + Agent Guidance) + dogfood
  fixtures + ship + **close #1392** (items 1/3/4 already shipped; this completes it).
