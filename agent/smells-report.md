# Code Smells Report — 2026-05-15

Commit: d1706bd3 (v0.70.0)
Scope: `src/dazzle/`, `src/dazzle_back/`, `src/dazzle_ui/` (tests/, examples/, auto-generated excluded)

## Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | No swallowed exceptions (`except Exception: pass`) | **PASS** | 0 bare except-pass patterns |
| 1.2 | No redundant except tuples | **PASS** | 0 results for all three variants |
| 1.3 | Core→MCP isolation | **PASS** | 0 `from dazzle.mcp` imports in `src/dazzle/core/` |
| 1.4 | No `project_path: Any` in handlers | **PASS** | 0 results |
| 1.5 | Fallback paths log at WARNING+ | **PASS** | No silent swallowing |
| 1.5a | No silent handlers in event delivery | **PASS** | 0 bare `pass`/`return` after `except` in events/channels |
| 1.5b | `getattr()` string-literal count | **TRACK** | 1,624 (↑597 vs 1,027 last round); ≥200 threshold — likely IR dynamic access |
| 1.6 | Functions >150 lines (aspirational) | **INFO** | 135 offenders (↑16 vs 119). Top: `parse_workspace_region` (859), `get_workflow_guide` (777), `create_site_page_routes` (605), `_discover_entities` (452), `init_workspace_routes` (432) |
| 1.7 | Classes >800 lines (aspirational) | **INFO** | 11 offenders (↑2 vs 9). Top: `WorkspaceParserMixin` (2846), `EntityParserMixin` (2287), `ProcessParserMixin` (1507), `DazzleBackendApp` (1404), `MessagingParserMixin` (1190) |
| 1.8 | Alpine `@<event>.window` lifecycle leaks | **PASS** | 0 results — no #795-class lifecycle bugs |

**Hard gates 1.1–1.5a, 1.8: all PASS.** Aspirational metrics drifted up: getattr +597, fn>150 +16, classes>800 +2.

## New Patterns Found

Ordered by severity × instance count.

| # | Pattern | Category | Instances | Severity |
|---|---------|----------|-----------|----------|
| P1 | `back` ↔ `ui` bidirectional layer cycle | coupling | 23 | HIGH |
| P2 | `dazzle.core` imports from `dazzle.back` (downward violation) | coupling | 2 | HIGH |
| P3 | `except Exception` logged at DEBUG (auth/job/grant load-bearing paths) | error_handling | 207 | HIGH |
| P4 | Bare `httpx.AsyncClient/Client` bypassing `async_retrying_request` | error_handling | 27 | HIGH |
| P5 | `dazzle.core.ir` 63-importer fan-in (no facade) | coupling | 63 | MEDIUM |
| P6 | Enum `.value if hasattr(.., "value") else str(..)` dead-guard | type_safety | 33 | LOW |
| P7 | Inline `json.dumps({"error": ...})` duplicating `error_response()` | duplication | 12 | MEDIUM |
| P8 | `request: Any` in route_generator helpers (FastAPI `Request` already imported) | type_safety | 11 | MEDIUM |
| P9 | `serialize_test_design` `td: Any` despite concrete `TestDesignSpec` | type_safety | 2 | LOW |
| P10 | Dead backward-compat aliases (ADR-0003 violations) | duplication | 3 clusters | MEDIUM |
| P11 | Monolithic parse functions with extreme nesting (depth 27–53) | complexity | 6 | HIGH |
| P12 | Duplicated `_SEVERITY_ORDER` with divergent schemas | mutable_globals | 5 | MEDIUM |
| P13 | Mutable module-level singletons (ADR-0005 violations) | mutable_globals | 5 | HIGH |
| P14 | `DazzleBackendApp` god class (1403 lines, 40 methods) | complexity | 1 | HIGH |
| P15 | 592 functions >80 lines (route_generator/page_routes hotspots) | complexity | 592 | MEDIUM |

### Detailed pattern entries

**P1 — `back` ↔ `ui` bidirectional layer cycle (23 sites)**
- `src/dazzle/back/runtime/route_generator.py:430`, `src/dazzle/back/runtime/surface_access.py:24`, `src/dazzle/ui/runtime/page_routes.py:476` (`_PageDeps` callable-injection shim explicitly labelled "#679 workaround").
- ROOT_CAUSE: No enforced layer contract; rendering helpers live in `back`, `ui` reaches into `back` for data; 1,699 deferred function-level imports mask the cycle.
- FIX: Move rendering contracts into existing `dazzle.render` package. Delete `_PageDeps` shim.
- DONE: `grep -rn "from dazzle.back" src/dazzle/ui/` and reverse — both empty.
- ENFORCE: ruff banned-imports rule or pytest import-boundary test.

**P2 — `dazzle.core` → `dazzle.back` downward layer violation (2 sites)**
- `src/dazzle/core/appspec_loader.py:10`, `src/dazzle/core/project.py:9` — both pull `default_renderer_names` from runtime.
- ROOT_CAUSE: Convenience patch; the function belongs in `core`.
- FIX: Move `default_renderer_names()` into new `dazzle/core/renderer_registry.py`. `back` imports from there.
- DONE: `grep -rn "from dazzle.back" src/dazzle/core/` empty.
- ENFORCE: Same import-boundary gate as P1.

**P3 — `except Exception → logger.debug(...)` on load-bearing paths (207 sites)**
- `src/dazzle/back/runtime/llm_queue.py:161` (loses AIJob audit), `src/dazzle/ui/runtime/page_routes.py:557` (auth failures invisible in prod), `src/dazzle/back/runtime/workspace_region_prelude.py:111` (scope-bypass risk unlogged).
- ROOT_CAUSE: DEBUG overloaded as "best-effort"; security/audit-load-bearing paths share the same level as cosmetic enrichment.
- FIX: Triage all 207; auth/grant/job/seed paths log WARNING + `exc_info=True`. Reserve DEBUG for cosmetic-only.
- DONE: `grep -rn -A2 "except Exception" src/dazzle/ | grep logger.debug | grep -E "auth|job|grant|seed"` empty.
- ENFORCE: Semgrep rule — `except Exception` + nearby `logger.debug` on flagged keywords fails CI.

**P4 — Bare `httpx.AsyncClient/Client` bypassing retry helper (27 sites)**
- `src/dazzle/back/runtime/health_aggregator.py:419` (no retry → transient 503 marks dependency unhealthy), `src/dazzle/back/graphql/adapters/base.py:664` (only `TimeoutException` caught, not `ConnectError`/502/503), `src/dazzle/back/runtime/api_tracker.py:389`.
- ROOT_CAUSE: `dazzle.core.http_client.async_retrying_request` added after callers existed; adoption never enforced.
- FIX: Replace with `async_retrying_request`. Exempt `agent/`/`testing/` with `# noqa: DZ-HTTP-NORETRY`.
- DONE: `grep -rn "httpx\.AsyncClient(" src/dazzle/back/ src/dazzle/mcp/ src/dazzle/cli/` — only retry-wrapped or noqa hits.
- ENFORCE: Semgrep rule fails CI.

**P5 — `dazzle.core.ir` fan-in (63 importers)**
- `route_generator.py`, `mcp/server/handlers/sitespec.py`, `sentinel/models.py` — all import concrete IR classes.
- ROOT_CAUSE: No protocol facade; every layer touches concrete types.
- FIX: Introduce `dazzle/core/ir/protocols.py` (`EntityLike`, `SurfaceLike`, `FieldLike`); `back`/`mcp` import protocols.
- DONE: `grep -rn "from dazzle.core.ir.appspec\|surfaces\|domain" src/dazzle/back/` empty.
- ENFORCE: ruff `TID252` banned imports outside `core/` and `back/specs/`.

**P6 — Dead StrEnum value-extraction guard (33 sites)**
- `src/dazzle/core/validator.py:2005`, `src/dazzle/back/runtime/route_generator.py:908`, `src/dazzle/back/runtime/workspace_columns.py:36`.
- ROOT_CAUSE: `FieldType.kind: FieldTypeKind` is non-Optional StrEnum but accessed via `getattr(..., None)` introducing a fictional union.
- FIX: Direct attribute access `field.type.kind`.
- DONE: `grep -r 'hasattr.*value.*else str(' src/dazzle/` empty.
- ENFORCE: Semgrep matching the always-redundant pattern.

**P7 — Inline `json.dumps({"error": ...})` (12 sites)**
- `src/dazzle/mcp/server/handlers/feedback.py:41`, `llm.py:56`, `testing.py:33`. Inconsistent `indent=` → divergent wire output.
- FIX: Use `error_response()` from `common.py`. Delete dead aliases `handler_error_json`/`async_handler_error_json` at `common.py:98-99` (zero importers).
- DONE: `grep -r 'json\.dumps.*"error"' src/dazzle/mcp/server/handlers/ | grep -v common.py` empty.
- ENFORCE: ruff custom or CI grep gate.

**P8 — `request: Any` in route_generator helpers (11 sites)**
- `route_generator.py:183, 247, 257, 669, 784, 798, 837, …` — `Request` already imported at line 54.
- FIX: `request: Request`.
- DONE: mypy passes with `disallow-untyped-defs` on those helpers.
- ENFORCE: mypy `[[overrides]]` for `route_generator.py`.

**P9 — `serialize_test_design(td: Any)` (2 sites)**
- `src/dazzle/mcp/server/handlers/serializers.py:84, 90`.
- FIX: Import `TestDesignSpec` under `TYPE_CHECKING`; annotate.
- DONE: `grep 'serialize_test_design.*Any' src/dazzle/` empty.

**P10 — Dead backward-compat aliases (3 clusters)**
- `mcp/server/handlers/common.py:98-99` (zero importers), `core/ir/layout.py:212` `LayoutArchetype = Stage` (9 callers in `layout/archetypes.py`), `back/runtime/exception_handlers.py:563-564` `register_site_404_handler` (1 caller).
- FIX: Migrate callers to canonical names; delete aliases. ADR-0003 prohibits compat shims.
- DONE: `grep -r 'LayoutArchetype\|handler_error_json\|register_site_404_handler' src/` empty.

**P11 — Monolithic parsers (6)**
- `parse_workspace_region` (858 lines, nesting depth 53), `parse_entity` (depth 27), `parse_surface` (depth 19).
- FIX: One `_parse_<region_kind>(tokens) -> RegionSpec` per region type; top-level becomes a `match` router.
- DONE: AST check — max function length in `dsl_parser_impl/` ≤100 lines.
- ENFORCE: pytest function-length quality gate on `dsl_parser_impl/`.

**P12 — Duplicated `_SEVERITY_ORDER` (5 sites, divergent schemas)**
- `qa/report.py:7`, `qa/trial_report.py:37`, `cli/runtime_impl/ux_cycle_impl/visual_tier2_ingest.py:36` share 3-level; `agent/journey_analyser.py:27` adds `"critical":0` (shifted); `sentinel/orchestrator.py:26` uses `Severity` enum.
- FIX: Single `src/dazzle/core/severity.py` with 4-level `{critical:0, high:1, medium:2, low:3}`.
- DONE: `grep -r '_SEVERITY_ORDER' src/dazzle/` empty.

**P13 — ADR-0005 mutable module-level singletons (5)**
- `back/runtime/auth/current.py:41` `_AUTH_STORE`, `back/runtime/auth/events.py:30` `_event_framework`, `mcp/runtime_tools/handlers.py:24` `_TOOL_DISPATCH` (mutated at module scope by line 817), `compliance/analytics/tenant_resolver.py:150` `_resolver_registry`.
- FIX: Move into `ServerState`/`RuntimeServices`. Rewrite `_TOOL_DISPATCH` as a `build_dispatch_table()` factory called once.
- DONE: `grep -rn 'global _AUTH_STORE\|global _event_framework\|_TOOL_DISPATCH.update' src/dazzle/` empty.
- ENFORCE: Remove per-site `# noqa: PLW0603` so ruff fails.

**P14 — `DazzleBackendApp` god class (1403 lines, 40 methods)**
- `_setup_routes` 416 lines / 36 if-branches, `_wire_service_hooks` 109, `_create_app` 107.
- FIX: Extract `RouteRegistry.register(router, prefix, tags)` + `ServiceRegistry`. Features self-register at import.
- DONE: AST check — max method length in `back/runtime/server.py` ≤80.
- ENFORCE: Add to `tests/unit/test_code_quality.py`.

**P15 — 592 functions >80 lines (codebase-wide)**
- `route_generator.py:_list_handler_body` (364), `ui/runtime/page_routes.py:create_page_routes` (408), `ui/converters/template_compiler.py:compile_appspec_to_templates` (287).
- FIX: ruff `C901 max-complexity=12` + pytest AST gate ≤120 lines for `back/runtime/`+`ui/runtime/` (refactor outliers first).

## Recommended Next Actions

1. **P3 — DEBUG-level swallowing on auth/job/grant paths (207 sites).** Highest correctness/security exposure. Triage by keyword (auth|job|grant|seed) and reclassify to WARNING + `exc_info=True`. Lock with semgrep gate. The bare-except-pass gate (1.1) is green, but this is the same bug class slipping past at a more permissive log level.
2. **P13 + P2 — ADR-0005 singletons and core→back violation.** Architectural drift that compounds: `_TOOL_DISPATCH` mutating at module scope and `core/appspec_loader.py` importing from `back` together threaten the import-time invariant `core` was built on. Move `default_renderer_names` first (small), then rewrite `_TOOL_DISPATCH` as a factory.
3. **P1 + P5 — `back`↔`ui` cycle and IR fan-in.** Tackle as a single refactor: the protocols facade (`dazzle.core.ir.protocols`) is also what lets the `dazzle.render` package be a clean boundary. Land in one PR, delete `_PageDeps` shim.

## Comparison With Previous Round (2026-05-04 baseline)

- **Regressions resolved:** 1.1 stays at 0; the silent-swallow gate added last round held.
- **Regressions worsened:**
  - 1.5b `getattr()` 1,027 → **1,624** (+597). Mostly IR dynamic access; below action threshold but accelerating.
  - 1.6 functions >150 lines 119 → **135** (+16).
  - 1.7 classes >800 lines 9 → **11** (+2). New offenders likely in parser mixins.
- **Patterns resolved since last round:**
  - lru_cache singleton cluster (was 6) — no longer surfaced; appears collapsed into the 5 ADR-0005 sites in P13.
  - ADR-0003 shim modules from last round — partially addressed; 3 alias clusters still remain (P10), down from 5.
- **New patterns this round:** P3 (DEBUG-level swallowing — new framing of the silent-failure family), P4 (bare httpx adoption gap), P11 (parse-function depth-53 quantified for the first time), P12 (divergent severity schemas).
- **Net direction:** Hard gates holding; aspirational metrics drifting upward. P11/P14/P15 all point to the same root: no enforced function/class-length gate. The complexity backlog grows ~15 fns/round.
