"""Render layer — IR-driven HTML emission via typed Fragments.

This package does NOT use `from __future__ import annotations`. The match-
dispatch in `fragment.renderer` requires runtime type information.

The four-layer stack and where rendering lives (ADR-0038/0041; see
`docs/evaluation/back-ui-render-boundary.md`). HTML production is layered, not
duplicated — a reader looking for "where is X rendered?" routes by layer:

  http/   FastAPI routes/auth/DB; wires the layers, owns no markup.
  page/   page/route orchestration: `*_renderer.py` that coordinate
          request/context concerns, then call DOWN into render/.
  render/ (this) the PURE layer: AppSpec/spec → Fragment → HTML. `html.esc`,
          `context` (the typed *Context dataclasses), `fragment/` primitives +
          per-mode renderers, `dispatch` (surface + chrome), filters/access.
          No I/O, no Request, no SQL — serverless-testable. Enforced acyclic by
          the `render is pure` import-linter contract (`tests/unit/test_import_contracts.py`):
          render/ may not import http/ or page/.
  core/   parser / IR / AppSpec (render imports down into this).

So: change markup/primitives → render/; change page orchestration → page/;
change a route/data/auth → http/. (Layers renamed back→http, ui→page in ADR-0041.)
"""
