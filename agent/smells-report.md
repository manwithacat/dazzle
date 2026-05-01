# Code Smells Report — 2026-05-01

**Commit:** `83b34645`
**Previous round:** 2026-04-16 (commit `e91d9066`)
**Scope:** `src/dazzle/`, `src/dazzle_back/`, `src/dazzle_ui/`

## Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | No swallowed exceptions | **FAIL** | **28** bare `except Exception: pass` blocks in production code (down from 44 last round, ↓16). Concentrated in `agent/playwright_helper.py` (4), `qa/server.py` (2), `cli/ux.py` (2), `cli/ux_interactions.py` (2), `agent/executor.py`, `agent/missions/journey.py`, `cli/demo.py`, `cli/runtime_impl/serve.py`, `cli/qa.py`, `e2e/runner.py`, `testing/ux/runner.py`, `testing/ux/interactions/card_add.py`, `combined_server.py`, `service_generator.py`, `route_generator.py` (intentional/documented), `workspace_route_builder.py`. |
| 1.2 | No redundant except tuples | **PASS** | 0 results across all three patterns. |
| 1.3 | Core→MCP isolation | **PASS** | 0 imports of `dazzle.mcp` in `src/dazzle/core/`. |
| 1.4 | No `project_path: Any` in handlers | **PASS** | 0 results. |
| 1.5 | Fallback paths log at WARNING+ | N/A | No 1.2 hits to spot-check. |
| 1.5a | No silent handlers in event delivery | **PASS** | 0 silent handlers in `src/dazzle_back/events/` and `src/dazzle_back/channels/` (improved from previous: 1 was failing). |
| 1.5b | `getattr()` string-literal count | **TRACK** | **916** calls (threshold <200). Driven by agent/parser/IR introspection — `getattr` as safe attribute probe. Awareness only. |
| 1.6 | Function length (>150 lines) | **INFO** | 115 functions exceed 150 lines. Top 5: `_workspace_region_handler` (1138 ln, `dazzle_back/runtime/workspace_rendering.py:562`), `parse_workspace_region` (781 ln, `core/dsl_parser_impl/workspace.py:1287`), `get_workflow_guide` (777 ln, `mcp/cli_help.py:485`), `_discover_entities` (452 ln, `mcp/server/handlers/spec_analyze.py:48`), `_generate_stack_code` (424 ln, `deploy/stacks/tigerbeetle.py:30`). |
| 1.7 | Class length (>800 lines) | **INFO** | 9 classes exceed 800 lines: `EntityParserMixin` (2286 ln), `WorkspaceParserMixin` (2047 ln), `ProcessParserMixin` (1507 ln), `DazzleBackendApp` (1205 ln), `MessagingParserMixin` (1190 ln), `TestRunner` (1131 ln), `PopulationHandlers` (862 ln), `LLMParserMixin` (827 ln), `IntegrationParserMixin` (824 ln). |
| 1.8 | Alpine `@<event>.window` bindings (#795) | **PASS** | 0 results across all `src/dazzle_ui/templates/` HTML files. |

**Summary:** 1 hard FAIL (1.1 — bare except-pass), 1 TRACK (getattr count), 2 INFO size metrics. All other gates green. **Net trend vs last round:** 1.1 improved by 16 sites; 1.5a went from FAIL → PASS; previously failing event-delivery silent handlers all eliminated.

---

## New Patterns Found (Phase 2)

Ordered by severity × instance count.

| # | Pattern | Category | Instances | Severity | Recommendation |
|---|---------|----------|-----------|----------|----------------|
| P1 | Silent exception swallowing in infrastructure paths | error_handling | 93 | HIGH | Introduce `@degrade_gracefully` decorator scoped to genuinely non-critical sidecars; remove bare-pass elsewhere |
| P2 | Fragmented exception hierarchy (53 classes orphaned from `DazzleError`) | error_handling | 53 | HIGH | Add `BackendError`-rooted hierarchy in `dazzle_back` and feature sub-packages; drift gate via AST walk |
| P3 | `dazzle_back` ↔ `dazzle_ui` bidirectional coupling with deferred-import workarounds | coupling | 37 | HIGH | Extract shared types to `dazzle.core` or new `dazzle_shared`; add `import-linter` contract |
| P4 | God classes in parser mixin layer | complexity | 8 (>800 lines) | HIGH | Extract sub-mixins by concern (e.g. `EntityFieldParserMixin`, `EntityScopeParserMixin`) — overlaps with 1.7 INFO |
| P5 | Dispatch-table depth in DSL parsers (`while/elif` fan-out) | complexity | 125 fns ≥7 levels deep | MEDIUM | Replace `while/elif` chains with `dict[TokenType, Callable]` dispatch tables |
| P6 | Active backward-compat shims violating ADR-0003 | coupling | 5 live shims | MEDIUM | Remove each shim (no compat guarantee at this stage); drift gate forbids comment markers `# shim` / `Backward.compat` |
| P7 | Module-level mutable singletons in `dazzle_back` (ADR-0005 regression) | mutable_globals | 3 | MEDIUM | Move state to `request.app.state` / `RuntimeServices`; enable Ruff `PLW0603` for `dazzle_back` |
| P8 | Parameter-list bloat in `route_generator.py` | complexity | 11 fns >14 args | MEDIUM | Introduce `RouteGeneratorConfig` + `ListHandlerContext` dataclasses parallel to `ServerConfig` |
| P9 | Cross-module access to `_`-prefixed private symbols | coupling | 5 | MEDIUM | Promote each to public API (rename, add to `__all__`) or extract to shared module |
| P10 | Monolithic orchestrator functions (`_setup_routes`, `_workspace_region_handler`) | complexity | 2 fns >300 lines | MEDIUM | Extract per-subsystem registrars; introduce `RegionRenderer` protocol with one class per display-mode family |
| P11 | Module-level mutable registry with thread lock | mutable_globals | 2 | MEDIUM | Move registries to per-app context (`app.state` or owning subsystem class) |
| P12 | Public-API parameters typed `Any` where concrete IR type is known | type_safety | 6 | LOW | Replace with concrete types (`TestDesignSpec`, `UserRecord`, `list[dict[str, Any]]`); enable `disallow_any_explicit` for `dazzle.mcp.server.handlers` |
| P13 | Bare `dict` without type args + `# type: ignore[type-arg]` | type_safety | 6 | LOW | Replace with `dict[str, Any]` and remove ignore; enable `--disallow-any-generics` |
| P14 | Mixin methods calling sibling-mixin methods with `# type: ignore[attr-defined]` | type_safety | 5 | LOW | Introduce shared `ParserProtocol` (mirroring KG protocol pattern); cast `self` to it for cross-mixin calls |
| P15 | KG-setup boilerplate copy-pasted across `test_intelligence.py` handlers | duplication | 5 | LOW | Extract `_require_graph(project_root)` helper |
| P16 | Sitespec load + `SiteSpecError` block copy-pasted across `sitespec.py` handlers | duplication | 5 | LOW | Extract `_load_sitespec(project_root)` helper |
| P17 | Dispatch-dict key lookup with `# type: ignore[arg-type]` | type_safety | 5 | LOW | Add explicit `if operation is None: return ...` guard before `dict.get()` |

---

## Recommended Next Actions

1. **Fix the 1.1 regression** (28 bare-pass sites). Of the 28, ~5 are intentional (Playwright timeouts, regex parse fallbacks, documented `# pragma: no cover` cases). The remaining ~23 should either log at WARNING+ via the proposed `@degrade_gracefully` decorator OR raise. Tractable in a single cycle. Drift gate: extend `test_error_handling_discipline.py` (new) to walk the AST and assert bare-pass count stays at zero.

2. **Audit ADR-0003 shims (P6) — 5 sites.** Per ADR-0003 backward-compat is not a requirement; the live shims (state.py `_StateModule` proxy, runtime_tools `__init__.py` delegating functions, agent_e2e.py wrapper) are themselves smells. Each can be removed in a focused cycle. Drift gate: pre-commit hook scanning for `# shim` / `Backward.compat` markers.

3. **Audit ADR-0005 globals (P7) — 3 sites.** `_AUTH_STORE`, `_event_framework`, `_sa` in `dazzle_back` regress the `RuntimeServices on app.state` rule. Migrate each to the documented pattern. Drift gate: enable Ruff `PLW0603` for `src/dazzle_back/`.

Items 1-3 are all small, well-scoped, ADR-aligned, and produce mechanical drift gates. The remaining items (P4-P17) are larger / more diffuse — pick from them opportunistically when touching the affected modules, or batch a cleanup cycle if pre-1.0 surface freeze approaches.

---

## Comparison with Previous Round (2026-04-16)

| Check | Previous | Current | Trend |
|---|---|---|---|
| 1.1 bare except-pass | 44 (FAIL) | 28 (FAIL) | ↓16 sites; still failing |
| 1.5a silent event handlers | 1 (FAIL) | 0 (PASS) | ✅ resolved |
| 1.6 functions >150 lines | (not tracked numerically) | 115 | new metric |
| 1.7 classes >800 lines | (not tracked) | 9 | new metric |
| 1.8 Alpine `@*.window` | (added later in cycle) | 0 (PASS) | clean since introduction |

**Resolved since last round:**
- All silent handlers in event delivery path eliminated (1.5a now PASS)
- Bare except-pass sites reduced from 44 → 28 (significant progress; remaining 28 are mostly Playwright/QA helpers)
- Note: previous round filed #787 (TaskStoreBackend protocol design) — status unverified in this scan

**New patterns surfaced this round:**
- ADR-0003 shim audit (P6) — 5 specific live shims with names
- Cross-module private-symbol imports (P9) — 5 sites identified
- Mixin attribute-error suppressions (P14) — pattern named, fix prescribed (`ParserProtocol`)
- Dispatch-table depth pattern (P5) — 125 functions named via measurable threshold

---

## Drift gate proposals

The patterns above suggest these new drift gates worth adding (in priority order):

1. `tests/unit/test_error_handling_discipline.py` — AST walk asserting bare `except Exception: pass` count == 0 in production code (for 1.1)
2. `tests/unit/test_no_shims.py` — scan for `# shim` / `Backward.compat` markers (for P6)
3. Ruff `PLW0603` enabled for `src/dazzle_back/` (for P7)
4. `tests/unit/test_exception_hierarchy.py` — AST walk asserting all `*Error` / `*Exception` classes inherit from `DazzleError` (for P2)
5. `import-linter` contract: `dazzle_back` ⊥ `dazzle_ui` at module level (for P3)

Each is mechanical, single-file, and aligned with an existing or proposed ADR.
