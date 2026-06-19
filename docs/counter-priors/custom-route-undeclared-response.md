---
id: custom_route_undeclared_response
name: Custom route with an undeclared response shape (and/or no RBAC binding)
layer: inference
status: active
summary: >-
  A project's custom route handler (a `routes/*.py` override) that returns HTML
  should declare its response shape with `# dazzle:returns page|fragment|partial|json`
  so the framework knows whether to wrap it in the app shell — and ANY handler that
  touches a domain entity MUST declare `# dazzle:implements <Entity>.<op> via <param>`
  (or fail `dazzle rbac routes --strict`). The two are different postures: chrome /
  response-shape is a declared CHOICE (novel UI is welcome — declare `page` for
  full-bleed), RBAC is the mandatory LINE. An undeclared HTML override that returns a
  full `<!doctype>` can be swapped into `<body>` by an hx-boost nav and delete the
  app chrome; an unbound domain-touching handler bypasses permit/scope (ADR-0040).
triggers_text:
  - "custom route handler"
  - "route override"
  - "novel UI"
  - "full screen"
  - "custom page"
  - "return an HTML page from a handler"
  - "render my own layout"
triggers_code:
  - '#\s*dazzle:route-override'
  - 'return\s+HTMLResponse'
  - '<!doctype'
---

## The corpus prior

LLM training data is full of web handlers that just `return HTMLResponse("<html>…")`
— a self-contained page that owns its whole document and layout. Ported into a Dazzle
project, that handler escapes the app shell (an `hx-boost` navigation swaps the returned
document into `<body>`, deleting the sidebar/nav) and, if it touches a domain entity,
silently bypasses the permit/scope model the rest of the app enforces. Both happen
because the handler declared *nothing* about what it returns or what it touches.

## Wrong shape

```python
# routes/dashboard.py
# dazzle:route-override GET /app/dashboard

async def handler(request):
    rows = some_repo.all()                     # touches a domain entity, no RBAC binding
    return HTMLResponse(f"<!doctype html><html>…{rows}…</html>")  # owns the whole document
```

Nothing tells the framework this returns a full document (so it can't chrome it, and an
hx-boost nav deletes the shell), and nothing binds the entity access to permit/scope.
`dazzle validate`/lint pass; the failure shows up only at runtime.

## Right shape

Declare BOTH — the response shape (your choice) and the RBAC binding (mandatory):

```python
# routes/dashboard.py
# dazzle:route-override GET /app/dashboard
# dazzle:implements Report.list via report_id   # RBAC: the mandatory line
# dazzle:returns fragment                        # response shape: live in the app shell

async def handler(request, report_id: str):
    rows = some_repo.scoped(request)             # permit/scope already ran (the binding)
    return "<section>…rows…</section>"           # inner HTML — the framework chromes it
```

- Want a deliberately full-bleed / novel UI (a kiosk, a fullscreen canvas, a page
  hosting `island` components)? Declare `# dazzle:returns page` — it is served as-is and
  **never refused**. Novel UI is welcome.
- Returning a raw fragment for a targeted HTMX swap (not `#main-content`)?
  `# dazzle:returns partial`.
- Returning data? `# dazzle:returns json`.

## Why this matters here

Two guardrails, two postures — get them straight:

- **RBAC is the line (mandatory).** A domain-touching route declares
  `# dazzle:implements` or fails the `dazzle rbac routes --strict` matrix-completeness
  gate (#1420/ADR-0040). Novel UI does not get to skip permit/scope.
- **Response shape + chrome are your declared choice (novel UI welcome).** Declare
  `# dazzle:returns` to say what you return and whether you live in the shell. The
  framework enforces *consistency with what you declared* — a `fragment`/`partial` that
  returns a full `<!doctype>` is a loud error; a `page` is served untouched. An
  undeclared HTML override under `/app` gets a one-time advisory steering you to declare
  intent (#1392 item 2) — it is a nudge, never a block.
