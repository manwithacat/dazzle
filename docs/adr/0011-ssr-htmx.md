# ADR-0011: Server-Side Rendering with HTMX

**Status:** Accepted
**Date:** 2026-01-01

## Context

Dazzle generates live applications directly from DSL specifications. The UI layer must be produced programmatically from DSL constructs (surfaces, fields, modes) without requiring a separate frontend build pipeline or framework expertise.

Early prototypes used a React SPA approach, which introduced:

1. **Build complexity** — Node.js, bundlers, and package management alongside Python
2. **Two-repo tension** — Frontend and backend as separate concerns with separate deployment cycles
3. **DSL impedance mismatch** — DSL-generated UI required serialising full app state to JSON for the client
4. **Security surface** — Client-side routing and token handling added XSS and CSRF exposure

## Decision

Adopt **FastAPI** for the API layer, **Jinja2** for server-side HTML rendering, and **HTMX** for interactivity. No JavaScript SPA framework in the main application.

### Why SSR with Jinja2?

| Criterion | SSR + Jinja2 | React SPA | Vue SPA |
|-----------|-------------|-----------|---------|
| DSL → UI generation | Direct template render | JSON serialisation step | JSON serialisation step |
| Build step required | No | Yes | Yes |
| Python-native | Yes | No | No |
| Security defaults | Strong (CSRF built-in) | Manual | Manual |
| Time to first byte | Fast | Slow (JS parse + hydrate) | Slow |
| LLM-generated code quality | High | Variable | Variable |

### Why HTMX?

HTMX replaces the interactivity layer without introducing a JavaScript framework:

- **Partial page updates** via `hx-get`, `hx-post` — server returns HTML fragments
- **No client state** — all state lives on the server, consistent with DSL-first design
- **Progressive enhancement** — pages work without JS, enhanced with it
- **Minimal JS** — no bundler, no `node_modules`, no transpilation

### Architecture

```
DSL Surface → Jinja2 Template → HTML response
                ↑
          FastAPI route handler
                ↑
          AppSpec (IR)
```

HTMX triggers return rendered HTML partials from the same Jinja2 layer. No JSON API needed for UI interactions.

## Consequences

### Positive

- No frontend build step — `dazzle serve` starts immediately
- DSL constructs map directly to template variables and partials
- CSRF and XSS protections apply uniformly at the FastAPI layer
- Single language (Python) for all application logic
- LLM-generated templates are straightforward Jinja2, not JSX or component trees

### Negative

- Rich client interactions (drag-and-drop, offline) require custom JS beyond HTMX
- Team members with SPA backgrounds face a learning curve
- Browser history and deep-linking require explicit HTMX push-url configuration

### Neutral

- Static assets (CSS, icons) served from `dazzle_ui/static/` without a bundler
- JavaScript islands remain available for complex widgets via `<script>` tags

## Alternatives Considered

### 1. React SPA

Separate React frontend consuming a JSON API from FastAPI.

**Rejected:** Adds Node.js build toolchain, complicates DSL → UI code generation, increases security surface.

### 2. Vue SPA

Same architecture as React with Vue instead.

**Rejected:** Same drawbacks as React. No meaningful advantage for a DSL-generated UI.

### 3. Separate Frontend and Backend Repositories

Independent deployment of UI and API with a CDN in front.

**Rejected:** Operational overhead without benefit at current scale. DSL spec ties UI and API together by design.

## Implementation

Templates live in `src/dazzle_ui/templates/`. HTMX is loaded from CDN or vendored into `src/dazzle_ui/static/`. FastAPI route handlers in `src/dazzle_back/` return `TemplateResponse` objects backed by Jinja2.
