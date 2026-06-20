# ADR-0041 — Layer rename: `back/` → `http/`, `ui/` → `page/`

**Status:** Accepted (2026-06-20). Implemented in one pass (the rename + tree-wide import rewrite).
**Completes:** ADR-0038 (rendering layer boundary; the four-layer stack) and the `docs/evaluation/back-ui-render-boundary.md` assessment, which concluded the runtime *is* a four-layer stack but that the **names** `back`/`ui` are a vestige of the pre-SSR era and would read clearer as `http → page → render → core`. This ADR does not change behaviour, dependencies, or the layer rule — only the package names.
**Supersedes:** the `back`/`ui` package naming established informally at the #1055 package merge (`dazzle_back`/`dazzle_ui` → `dazzle.back`/`dazzle.ui`). The layer *boundaries* (ADR-0038, the import-linter contracts) are unchanged; only their labels move.

## Context

The `back/` vs `ui/` split predates server-side rendering. ADR-0011 (SSR + htmx, no SPA) and ADR-0023 (typed Fragment substrate, Jinja2 removed at #1042) turned what was once a "FastAPI-routes vs Jinja-templates" division into a four-layer dependency stack:

```
back/   FastAPI runtime: routes, auth, DB, handlers, HX-* contract   (the app / I/O)
  ↓
ui/     page/route orchestration: *_renderer.py + converters + static assets
  ↓
render/ pure AppSpec → Fragment → HTML (no I/O, serverless-testable)
  ↓
core/   parser / IR / AppSpec
```

A four-agent investigation (2026-06-20) confirmed the boundary is sound — `ui ↛ back` holds at zero allow-list, the only real import cycle was an intra-`back` one (broken separately, v0.83.33), and the worst misplacement (pure rendering in `back/`) was already fixed by ADR-0038. What remained was purely **nominal**: the names `back`/`ui` evoke a dead client/server dichotomy and actively mislead — a FastAPI router lived at `ui/runtime/page_routes.py` ("sounded like UI, was backend", per the #1055 merge commit), and HTML was produced under `back/runtime/renderers/`. After the v0.83.32–34 cleanups (naming sweep, cycle break, server-runtime relocation), the names were the last vestige.

## Decision

Rename the two layer packages so the names match the topology:

- **D1.** `src/dazzle/back/` → `src/dazzle/http/` (the HTTP/I/O layer — routes, auth, DB, the app).
- **D2.** `src/dazzle/ui/` → `src/dazzle/page/` (the page-orchestration layer — `*_renderer.py`, converters, static assets).
- **D3.** `render/` and `core/` are unchanged. The stack is now `http → page → render → core`.
- **D4.** Mechanical, tree-wide: a single word-bounded rewrite of every `dazzle.back`/`dazzle.ui`/`dazzle/back`/`dazzle/ui` reference across code, tests, configs, docs, package-data keys, the mypy-override list, the import-linter contracts, and the drift baselines (regenerated). No behaviour, dependency, or API-surface change — the public package name (`dazzle-dsl`) and import root (`dazzle`) are unchanged; only the two sub-packages move. Clean break (ADR-0003): no `back`/`ui` compatibility shims.

The import-linter contracts (`test_import_contracts.py`) keep enforcing the same rules under the new names: `core ↛ http/page`, `page ↛ http`, `render ↛ http/page`, `http` is Postgres-only.

## Consequences

- **Legibility:** a reader routes by layer name — "change a route/data/auth" → `http/`; "change page orchestration" → `page/`; "change markup/primitives" → `render/`. The names no longer lie.
- **Churn (one-time):** ~1000 `.py` files plus the config/baseline surfaces (cf. the inverse #1055 merge, a 909-file release). Verified with the full non-e2e suite, mypy, `lint-imports`, `dazzle serve` boot, and a wheel build + package-data inspection (the static-asset/alembic globs moved to `dazzle.page`/`dazzle.http`).
- **History:** ADRs and docs that referenced `src/dazzle/back/` now read `src/dazzle/http/`; this ADR is the record of why. The `dazzle_back`/`dazzle_ui` underscore names (pre-#1055) survive only in a couple of legacy comments.

## Rejected alternatives

- **Keep `back`/`ui`.** The names mislead; every new reader re-derives that `page_routes` is backend and that HTML comes from three places. The eval flagged this as a standing comprehension tax.
- **Merge the two layers.** The boundary is real and valuable (pure, serverless-testable rendering separated from I/O); the investigation disproved the "the split is the coupling cause" hypothesis. Merging would discard a sound seam.
- **Defer indefinitely.** The rename is pure churn with no behaviour change, so it only gets more expensive as the tree grows; doing it as a focused, fully-gated pass while the layering is fresh is cheapest.
