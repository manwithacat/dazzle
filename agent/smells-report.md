## Code Smells Report — 2026-06-21

HEAD: `36d431cf8` · Regressions failed: **0** · New patterns: **15** · Decay: ratchet **clean**, import contracts **kept** (allow-list 3)

### Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | no-swallowed-exceptions | PASS | 0 inline `except Exception: pass` in `src/`; the only multi-line except→pass hits are 3 in `http/tests/` (best-effort cleanup) — all test code. |
| 1.2 | no-redundant-except-tuples | PASS | 0 hits for `(ImportError, Exception)` / `(json.JSONDecodeError, Exception)` / `(JSONDecodeError, Exception)`. |
| 1.3 | core-mcp-isolation | PASS | 0 `from dazzle.mcp` imports in `core/`; consistent with the live import-linter contract (KEPT). |
| 1.4 | no-project-path-Any | PASS | 0 `project_path: Any` in `mcp/server/handlers/`. |
| 1.5a | no-silent-event-handlers | PASS | 17 except+pass/return in `http/events` & `http/channels`, all narrow specific types (CancelledError/TimeoutError/…); no bare `except Exception`. |
| 1.5b | getattr-string-literals | TRACK | 2165 `getattr(` across `src/` (>200 threshold) — standing defensive dynamic-attr debt. |
| 1.6 | complexity-creep | TRACK | `complexity_baseline.json`: 22 files at MI-rank C; highest CC `core/linker_impl.py::validate_references` = **119**. Ratchet gates new CC>15/MI drops. |
| 1.7 | god-files | TRACK | 22 files at MI rank C (incl. `linker_impl`, `http/runtime/{store,page_routes,repository,server,workspace_aggregation}`, `validation/extended`, `template_compiler`, `lsp/server`). |
| 1.8 | alpine-window-bindings | PASS | 0 `@<event>.window` bindings in `page/` templates. |
| 1.9 | import-contract-allowlist | PASS | `lint-imports` exit 0 — 5 contracts kept, 0 broken (1482 files, 9183 deps). Allow-list 3 documented edges, no growth. |

**0 FAIL-class regressions.** All established rules hold; the TRACK rows are standing baselines the live CI ratchet/contracts already gate.

### New Patterns Found

Ordered by severity × instance count.

| Pattern | Category | Inst. | Root cause (short) | Canonical fix |
|---------|----------|-------|--------------------|---------------|
| Logger acquired by string literal instead of `__name__` | Error handling | 131 | 281 modules use `getLogger(__name__)`, 131 hand-write `getLogger('dazzle.server')`; rename re-parents records under wrong logger, breaks per-module filtering. | `getLogger(__name__)` everywhere; reserve string names for deliberate shared channels, defined once as a constant. |
| Runtime error reporting via `print()` not the logger | Error handling | 4 | `analytics_collector.py` logs a flush failure with `logger.warning(exc_info=True)` but `print()`s store/emit failures in the same path; `hot_reload.py` same. Errors invisible to operators, stack trace lost. | Replace error `print()` in `http/*`,`page/*` with `logger.exception/warning`; keep `print()` only for the serve banner / `__main__`. |
| Outbound network I/O bypasses the retry helper | Error handling | 5 | `core/http_client.request_with_retries` exists & is used by domain call sites, but `agent/*` + `http/runtime/{api_middleware,health_aggregator,api_tracker}` issue raw httpx/requests — opt-in helper, so new calls default to no-retry. | Make retry the default transport: construct the AsyncClient with the backoff transport at the composition root and inject it. |
| Deferred (function-body) `dazzle.*` imports as cycle avoidance | Coupling | 2218 | `dazzle/__init__` eagerly imports `http` → transitive cycles, so top-level imports trip a real cycle; function-level import is the workaround. Hides the dep graph, defers ImportError to first-call. Concentrated in `server.py` (105), `auth/store.py` (41), `app_factory.py` (40). | Break the cycle (leaf extraction à la #1426/#1055), hoist imports to top; true plugin boundaries → injected via RuntimeServices (ADR-0005). |
| Backward-compat shims / wrappers despite ADR-0003 | Coupling | 25 | `evaluate_permission_bool` wrapper; ~6 linker delegated `@property` shims; fragment/region builder legacy aliases — kept because migrating all callers is locally costly. Two ways to call the same thing. | Per ADR-0003: delete the shim, migrate all callers in the same commit. |
| BC re-export / fallback shims (second source of truth) | Duplication | 6 | `pptx_gen` re-exports ~40 primitives "for backwards compatibility"; `realtime_client.py` keeps a 900+-line `_REALTIME_CLIENT_JS_INLINE` duplicate of `static/js/realtime.js`; `mcp/knowledge_graph/store` re-exports for compat. | Migrate importers in one commit, delete the re-export/inline duplicate; serve the real static asset or fail loud. |
| Inline entity-slug `name.lower().replace('_','-')` re-derived | Duplication | 10 | #1426 made `page.app_paths.entity_slug` the ONE formula + a drift gate, but the gate only guards the page/template path; callers in http/core/agent/testing re-type the one-liner. | Import & call `entity_slug()` (or the `*_path` builders); delete the inline form. |
| Raw `raise HTTPException(404, …)` instead of `require_found` | Duplication | 34 | `require_found` + `test_no_inline_404_guard` exist, but the gate regex only matches the EXACT default `"Not found"` message; domain-specific messages and positional `HTTPException(404, …)` sidestep it (34 raw vs 9 helper). | Use `require_found(fetch(), "<Thing> not found")` — takes custom detail + narrows `T|None`→`T`. |
| Inline id-first identity fallback `getattr(x,'id',None) or getattr(x,'name',…)` | Duplication | 8 | `spec_display_id` + its gate only handle `name`-then-`id`; PersonaSpec is `.id`-first, so id-first sites re-inline and evade the gate (`lsp/server.py`, `persona_journey.py`). | Add `spec_display_id(spec, prefer='id')` / a `persona_display_id` sibling; route id-first sites through it. |
| IR-typed params annotated `Any` (appspec/workspace/entity/surface) | Type safety | 27 | Renderer-stack functions take known IR objects but annotate `Any` (leftover cycle-dodge); masks attr typos, kills mypy on the most-passed objects. | Annotate with the concrete `dazzle.core.ir` type (core is the bottom layer — no cycle); use a Protocol if only a subset is needed. |
| Parser match-ladder in `entity.py`/`workspace.py` never adopted `parse_block_with_dispatch` | Complexity | 2 | The table-driven dispatch helper was adopted by 16 mixins; the two largest/oldest block parsers (`parse_entity` 3021 LOC / 86 elif arms; `_dispatch_workspace_keyword` 24-arm ladder) were never migrated — each new keyword appends an arm → unbounded growth, MI-rank C (#2 & #5 hotspots). | Migrate both to `parse_block_with_dispatch[StateT]` with an `_EntityState`/`_WorkspaceState` accumulator; collapse the elif chain to a lookup. |
| Lazy module-level mutable cache + `global` + test-only `reset_*` | Mutable globals | 5 | `_signer_cache`, `_WIDGET_KIND_TO_FORM_TYPE`, `_dispatch_cache`, `_sa`, `_fingerprint_cache` — `_X=None` rebound via `global`, paired with a `reset_*` whose existence is the shared-state tell. Mostly unsynchronized (boot/render race). `# noqa: PLW0603` licenses it. | `functools.cache` for pure idempotent values (tests call `cache_clear`); RuntimeServices/ServerState for lifetime-bound state. Delete global + reset. |
| Self-rolled `get_default_*()/set_*()` singleton (ADR-0005 violation) | Mutable globals | 2 | `_DEFAULT_ACCUMULATOR` (retry_accumulator) and `_DEFAULT_BACKEND` (task_store) — docstrings admit "process-wide singleton … not any FastAPI app", and `set_task_store` admits "swapping mid-flight strands in-flight tasks". | Move onto RuntimeServices/ServerState as injected fields; delete the module global + get/set free functions + reset helper. |
| Boot-time boolean config flag via `configure_*()` + Jinja getter | Mutable globals | 2 | `_DARK_MODE_TOGGLE_ENABLED` / `_HAPTIC_ENABLED` in `theme.py` are copy-paste module booleans, while the same file correctly uses ContextVar one screen up. Blocks per-tenant override, makes tests order-dependent. | Store on manifest/ServerState (frozen UIChrome field), bind into the Jinja env like `theme_variant()` reads the ContextVar. |
| God class — `TestRunner` / `DazzleClient` mega-classes | Complexity | 2 | `DazzleClient` (25 methods) mixes transport/CSRF/auth/CRUD/FK-cleanup/residue/data-gen; `TestRunner` (44 methods) orchestrates on top. Each new capability is one more method (responsibility accretion), MI-rank C (#7 hotspot). | Split into transport / EntityClient / CleanupManager / DataGenerator collaborators that TestRunner composes via injection. |

### Structural Decay (live harness)

The CI complexity ratchet + import contracts gate *new* decay; this is the standing baseline.

- **Ratchet:** `clean` (no regressions vs baseline)   **Import contracts:** `kept` (5/5), allow-list size **3** (unchanged — no growth)
- **Priority refactor targets** (high-churn × MI-rank-C): `dsl_parser_impl/workspace.py`, `dsl_parser_impl/entity.py`, `testing/test_runner.py`, `cli/testing.py`, `core/linker_impl.py`

| Rank | Hotspot file | Score | Churn | MI |
|------|--------------|-------|-------|----|
| 1 | `mcp/server/handlers_consolidated.py` | 8343.9 | 111 | A |
| 2 | `core/dsl_parser_impl/workspace.py` | 6100 | 61 | **C** |
| 3 | `core/lexer.py` | 5649.3 | 79 | A |
| 4 | `core/ir/workspaces.py` | 5415.7 | 64 | B |
| 5 | `core/dsl_parser_impl/entity.py` | 5200 | 52 | **C** |
| 6 | `render/fragment/primitives/data.py` | 5107.2 | 60 | B |
| 7 | `testing/test_runner.py` | 4900 | 49 | **C** |
| 8 | `core/linker.py` | 4578.7 | 62 | A |

Highest-CC functions: `linker_impl.py:validate_references (cc 119)`, `page_routes.py:_build_dispatch_ctx (cc 108)`, `template_compiler.py:compile_appspec_to_templates (cc 101)`, `render/fragment/renderer/_emit.py:FragmentRenderer._emit (cc 98)`, `page_routes.py:create_page_routes (cc 84)`.

Note: decay is holding flat — ratchet passes clean, all 5 contracts kept, allow-list still 3 edges. Best single refactor target: `dsl_parser_impl/workspace.py` (#2 hotspot, MI-rank C) — directly overlaps the **parser match-ladder** semantic pattern above (migrate to `parse_block_with_dispatch`). `linker_impl.py` is a close second (priority queue + owns the CC-119 function).

### Recommended Next Actions

1. **Logger-by-string-literal (131 sites).** Highest-instance semantic smell the harness can't see; a real operability footgun (rename → orphaned logger, broken per-module filtering). Fix = mechanical `getLogger(__name__)` + a drift gate mirroring `test_no_regex_in_parser`. Best ROI this round.
2. **Broaden two near-miss dedup gates that are being evaded** — `require_found` (34 raw `HTTPException(404)` sidestep the exact-message regex) and the id-first identity fallback (8 sites evade the name-first gate). Both helpers already exist; the fix is widening the gate regex + the id-first ordering, then migrating callers. Cheap, stops silent regrowth.
3. **`dsl_parser_impl/workspace.py` → `parse_block_with_dispatch`** (the one decay target where a finder named a concrete smell). Migrating the two unconverted parser ladders (workspace + entity) attacks the #2 and #5 hotspots at their root and stops the per-keyword ladder growth.

### Comparison with Previous Round (2026-06-19, a07c2a09b / v0.83.28)

- **Regressions:** 0 failed both rounds — all established rules still hold.
- **New patterns:** 15 this round vs 13 prior — similar surface; the recurring spine (deferred imports, ADR-0003 shims, IR-typed `Any`, god classes, 404-guard / identity-fallback dedup) persists.
- **Resolved/shifted since last round:** the prior "inline `HTTPException(404, "Not found")`" and "identity fallback" patterns were *partially* closed — the `require_found` and `spec_display_id` helpers + gates now exist, so this round's findings are specifically **gate-evasion variants** (custom-detail 404s; id-first identity order) — a narrower, more accurate diagnosis. The prior "state-machine state normalisation" pattern did not resurface (helper adopted). New this round: logger-by-string-literal, retry-helper bypass, the `print()`-not-logger split, and the mutable-globals cluster (lazy caches / self-rolled singletons / boot config flags) called out individually.
- **Decay delta:** ratchet still `clean`; import allow-list still **3** (no growth — good). Hotspot ranking stable; `workspace.py`/`entity.py`/`test_runner.py` remain the MI-rank-C priority targets. No file newly *climbed* into the C-rank set vs the prior table.
