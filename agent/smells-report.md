# Code Smells Report — 2026-05-04

**Commit:** 0c625b7376ab1870785d1e2aeff40fc3e41e03ee (v0.65.14)
**Previous round:** 2026-05-01 (commit `83b34645`)
**Scope:** `src/dazzle/`, `src/dazzle_back/`, `src/dazzle_ui/`
**Mode:** read-only analysis, 4 parallel subagents

---

## Phase 1 — Regression Check Results

| # | Check | Status | Details |
|---|---|---|---|
| 1.1 | No swallowed exceptions (`except Exception: pass`) | PASS | 0 bare-pass patterns matching the strict regex |
| 1.2 | No redundant except tuples | PASS | 0 across all three patterns |
| 1.3 | Core→MCP isolation | PASS | 0 `from dazzle.mcp` imports in `src/dazzle/core/` |
| 1.4 | No `project_path: Any` in handlers | PASS | 0 |
| 1.5a | No silent handlers in event delivery path | PASS | 0 |
| 1.5b | `getattr()` usage count | TRACK | **1,027** (threshold 200; +111 vs 2026-05-01 baseline of 916) |
| 1.6 | Functions > 150 lines | TRACK | **119** offenders. Worst: `workspace_rendering.py:562 _workspace_region_handler` (1,138L), `workspace.py:1316 parse_workspace_region` (781L), `cli_help.py:485 get_workflow_guide` (777L), `spec_analyze.py:48 _discover_entities` (452L), `tigerbeetle.py:30 _generate_stack_code` (424L) |
| 1.7 | Classes > 800 lines | TRACK | **9** offenders. Worst: `entity.py:60 EntityParserMixin` (2,287L), `workspace.py:21 WorkspaceParserMixin` (2,076L), `process.py:176 ProcessParserMixin` (1,507L) |
| 1.8 | Alpine `.window` binding leaks (#795) | PASS | 0 |

**Hard gates: 6/6 PASS.** Track-only metrics still drifting up; the parser-mixin god classes remain the largest aspirational debt.

---

## Phase 2 — New / Recurring Patterns

Ordered by `severity × instance count`.

| Pattern | Category | Instances | Root cause | Fix |
|---|---|---|---|---|
| **Silent exception swallow (variants)** | error_handling | **~85** | The strict gate matches `except Exception: pass` only; `return None` / `return {}` / `return []` after `except Exception:` escapes it | Replace each with `logger.debug(..., exc_info=True)` minimum; tighten the gate regex |
| **Broad `except Exception` where specific known** | error_handling | **30+** | `pitch/extractor.py` set the pattern (8 consecutive field extractors all blanket-catch); copied elsewhere | Narrow to `AttributeError`/`KeyError`/`httpx.HTTPError`/`json.JSONDecodeError`; enable ruff `BLE001` project-wide |
| **MCP error-wrapping bypassing `common.py` decorator** | duplication | **11** in `tool_handlers.py` + 1 in `handlers/e2e.py` | `tool_handlers.py` predates `wrap_handler_errors`; never migrated | Apply `@wrap_handler_errors`; ban `json.dumps({"error": str(e)})` outside `common.py` |
| **Monolithic route/rendering functions** | complexity | **13** | Each DSL feature accumulates in single functions | Extract phases (scope, auth, response) into ≤50-line helpers; pre-commit `radon cc -n C` |
| **`@lru_cache(maxsize=1)` process-wide singletons** | mutable_globals | **6** | Quick amortisation shorthand; violates ADR-0005 | Move into `RuntimeServices`/`ServerState`; semgrep ban outside `core/utils.py` |
| **Cross-layer imports** (`core`/`mcp` → `back`/`ui`) | coupling | **6** | No stable cross-layer interface; ADR-0002 bypassed | Introduce protocol classes / DI; add `tach` or import-linter rule |
| **Deep conditional nesting** | complexity | **6** (worst: `workspace_route_builder.py:362` at 13 levels) | Each runtime file inlines its own auth/scope branching | Guard-clause flattening; ruff `C901` and `PLR0912` |
| **Handler factory boilerplate (route_generator)** | duplication | **6** | No `HandlerConfig` dataclass; 5-param tuple repeated | Introduce `HandlerConfig` dataclass; pass as single arg |
| **`cast(Any, redis.get(key))`** | type_safety | **6** in `celery_state.py` | redis-py's `bytes | None` mismatch suppressed with `cast(Any, …)` | Extract `_redis_get(key) -> str | None` helper |
| **Callback-param `Any`** (`on_progress`, `on_step`, `mcp_session`) | type_safety | **5** | No `ProgressCallback` alias propagated | Define `ProgressCallback = Callable[[str], None]` in `handlers/common.py` |
| **Backward-compat shim modules never cleaned up** | coupling | **5 modules** | Clean-break ADR-0003 applied to callers, not to the shims themselves | Update callers, delete the 5 shim modules; add `test_no_shim_modules.py` |
| **Workspace renderer `Any` annotations** | type_safety | **4** | `workspace_renderer.py` predates clean IR exports | `if TYPE_CHECKING:` import `WorkspaceSpec`/`AppSpec` from `dazzle.core.ir` |
| **Duplicated `_SEVERITY_ORDER` constant** | duplication / mutable_globals | **4** | Each consumer copied the dict; one diverged (`journey_analyser.py` adds `critical`) | Single canonical `SEVERITY_ORDER` in `dazzle/core/constants.py` |
| **`TestDesignSpec: Any` in serializers** | type_safety | **2** | Missing `TYPE_CHECKING` import | Add concrete annotation |
| **`_state = ServerState()` MCP module-level singleton** | mutable_globals | 1 file, **all handlers** consume | Predates ADR-0005 | Pass through FastMCP `lifespan` context |

---

## Recommended Next Actions (priority order)

1. **Tighten the silent-exception gate.** Today's `test_no_bare_except_pass.py` only catches `except Exception: pass`. Extend it to also catch `except Exception:` followed by a `return None|{}|[]` on the next line. ~85 sites in scope; many will shrink to `logger.debug(..., exc_info=True)` lines. Single biggest correctness lever.

2. **Audit and delete the 5 ADR-0003 shim modules.** `mcp.semantics`, `pptx_gen` re-exports, `pptx_slides` re-exports, `LayoutArchetype` alias, `ui_init.py`. Each has 2-5 callers; clean break, no compat shim. Add `test_no_shim_modules.py` to lock it.

3. **Eliminate the 6 ADR-0005 `@lru_cache(maxsize=1)` singletons.** `tigerbeetle_client` and `realtime_client` are the highest-risk (I/O clients survive project switches). Move into `RuntimeServices` with explicit `invalidate()`.

4. **Migrate `tool_handlers.py` to `@wrap_handler_errors`** (11 sites) — single-file mechanical fix.

5. **Define `HandlerConfig` dataclass** in `route_generator.py` to collapse the 6-factory parameter sprawl.

---

## Comparison with Previous Round (2026-05-01)

| Item | 2026-05-01 | 2026-05-04 |
|---|---|---|
| 1.1 bare-except-pass | 28 (FAIL) | **0 (PASS)** ✅ |
| 1.5b getattr count | 916 | 1,027 (+111) |
| 1.6 fns > 150 ln | 115 | 119 (+4) |
| 1.7 classes > 800 ln | 9 | 9 (=) |
| Shim modules | 5 (flagged) | **5 (still present)** |
| Mutable globals | 3 (flagged) | **6 lru_cache + 1 _state (worse)** |
| New patterns | 17 | 15 (consolidated) |

**Resolved since last round:**
- 1.1 went from 28 → 0 (the strict `except Exception: pass` regex). The 85-site silent-swallow population is the *expanded-scope* count — different gate, different number.
- 1.5a was 0 last round and remains 0.

**Net direction:** the hard gates are tighter than ever; the structural debt (shims, singletons, god functions) is unchanged. Aspirational metrics are drifting up because new feature work continues to land in the existing monolithic files.
