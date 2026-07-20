# Smells Log

## Smells Run — 2026-05-15
- Regressions: 8/10 hard gates PASS; 3 drifted upward (1.5b getattr 1,027→1,624; 1.6 fns>150ln 119→135; 1.7 classes>800ln 9→11)
- New patterns: 15 (P1–P15) — 6 HIGH, 6 MEDIUM, 3 LOW
- Top concern: P3 — 207 `except Exception → logger.debug` on load-bearing paths (auth/job/grant). Same bug class as 1.1 escaping at DEBUG level.
- Resolved since last: lru_cache singleton cluster collapsed; ADR-0003 shims 5→3 clusters
- Worsened: getattr +597; complexity (fns>150 +16, classes>800 +2, parse_workspace_region depth-53 newly quantified)
- Recommended next 3: (1) reclassify DEBUG→WARNING+exc_info on auth/job/grant + semgrep gate; (2) move `default_renderer_names` into core + rewrite `_TOOL_DISPATCH` as factory (P2+P13); (3) `dazzle.core.ir.protocols` facade unblocking `back↔ui` cycle (P1+P5)
- Commit: d1706bd3

## Smells Run — 2026-05-04
- Regressions: 6/9 hard gates PASS; 3 TRACK (1.5b getattr 1,027; 1.6 fns >150ln 119; 1.7 classes >800ln 9)
- New patterns: 15 (consolidated from prior 17 — silent-swallow merged with broad-except)
- Top concern: ~85 silent-swallow sites (`except Exception: return None|{}|[]`) escape today's gate
- Resolved since last: 1.1 strict bare-except-pass 28 → 0 ✅
- Worsened: 1.5b getattr +111; mutable_globals 3 → 7 (6 lru_cache singletons + _state hub now both surfaced)
- Recommended next 3: (1) tighten silent-exception gate to catch `return None|{}|[]` variants; (2) delete 5 ADR-0003 shim modules + lock with test; (3) replace 6 lru_cache(maxsize=1) singletons with RuntimeServices/ServerState
- Commit: 0c625b73

## Fix Cycle — 2026-04-16 (post-baseline)
- Patterns addressed: 14/18
- Correctness fixes: 3 (DB silent failures, foreach errors, email handler)
- Thread safety: 7 singletons made safe
- Duplication removed: ~1,500 lines (Celery module + HTTP utils)
- Type safety: ~30 Any→concrete, type-ignore codes added
- Coupling: MCP→CLI cycle broken, UI→testing layer fixed
- Complexity: 1,477-line function split, 55-method god class extracted, 48 constants frozen
- Filed: #787 (TaskStoreBackend protocol design)
- Deferred: parser god classes (in progress), oversized parser functions (in progress)
- Commit range: 0ef16779..9d973802

## Smells Run — 2026-04-16
- Regressions: 7/9 checks passed (1.1 FAIL: 44 swallowed exceptions, 1.5a FAIL: 1 silent email handler)
- New patterns: 18 found (3 critical, 6 high, 6 medium, 3 low)
- Top concern: DB-connection silent failure in process executors (correctness risk — failed steps reported as success)
- Commit: e91d9066

## Smells Run — 2026-05-01
- Regressions: 8/10 checks passed (1.1 FAIL: 28 swallowed exceptions, ↓16 vs last; 1.5b TRACK: getattr count 916)
- New patterns: 17 (4 HIGH, 7 MEDIUM, 6 LOW)
- Top concern: 28 bare `except Exception: pass` sites — improved but still failing the gate
- Resolved since last: 1.5a silent event handlers (was 1, now 0); 1.1 sites reduced 44 → 28
- New visibility: 1.6/1.7 size metrics now numerically tracked (115 fns >150 ln, 9 classes >800 ln)
- Recommended next 3: (1) finish bare-except-pass cleanup, (2) audit ADR-0003 shims (5), (3) audit ADR-0005 globals (3)
- Commit: 83b34645

## Fix Cycle — 2026-05-01 (post-baseline)
- Action 1 (1.1 bare-except-pass): 28 → 0 prod sites. Pattern: `with suppress(Exception):` for cleanup; `except Exception: logger.debug(..., exc_info=True)` for logged sites.
- Action 2 (P6 shims): removed 2/3 named live shims:
  - `state.py` `_StateModule` proxy + `_LEGACY_ATTR_MAP` deleted; tests updated to use `get_state()` accessor
  - `runtime_tools/__init__.py` 5 delegating wrappers moved into `state.py` as proper public setters/getters
  - `testing/agent_e2e.py` deferred (504-line module, 3 production callers — needs focused refactor cycle)
- Action 3 (P7 globals): not in this cycle. `_AUTH_STORE`, `_event_framework` need request-context plumbing through helpers. `_sa` is a legitimate lazy-import pattern, not application state.
- Drift gates added: `tests/unit/test_no_bare_except_pass.py`, `tests/unit/test_no_shims.py` (with ALLOWED_PATHS for the deferred agent_e2e wrapper + LayoutArchetype rename + RBAC PERMIT_UNPROTECTED text).
- Net: 28 sites quieted; 2 shims gone; 2 drift gates in place. ADR-0005 globals deferred to a focused cycle.

## Smells Run — 2026-05-28 (first Workflow-based run)
- Method: `/smells` Workflow (`.claude/workflows/smells.js`), 4 parallel finders, schema-validated. 217k tokens, ~4.5 min.
- Regressions: 1.2/1.4 clean; 1.1 + 1.5a are grep-count FAILs exonerated by their own details (test-only / all-intentional); 1.5b/1.6/1.7 TRACK. 2 genuine production FAILs: 1.3 (core→mcp function-local import in `core/docs_gen.py:389`), 1.8 (Alpine `@window` bindings in `ui/runtime/static/test-data-table.html` — **was hidden by the old stale `dazzle_page/templates/` scan path**).
- New patterns: 15 (top concern: silent IO/JSON-decode swallow, 119 instances). Notable systemic: `back/`→`dazzle.page.*` coupling (17), `_fastapi_compat` guard duplication (13), enum/state normalization idioms (53 combined), oversized funcs (582)/deep nesting (395)/god classes (56).
- Recommended next 3: (1) 1.3 core→mcp import, (2) `_fastapi_compat` consolidation + AST gate, (3) `load_json_or` util for the 119-instance silent-swallow class.
- Calibration note for `smells.js`: regression finder should set PASS when all grep hits are test-only/intentional (1.1, 1.5a over-reported FAIL).
- Commit: 0bcd50ce

## Smells Run — 2026-06-19 (first decay-harness-integrated run)
- Method: `/smells` Workflow, now 4 finders (regressions + 3 pattern cats + **decay-harness**), schema-validated. 5 agents, ~293k tokens, ~5.6 min.
- Regressions: **0 production FAIL** (down from 2 — 1.3 core→mcp import + 1.8 Alpine window bindings both RESOLVED). 1.1/1.5a now correctly PASS (calibration fix landed). TRACK: 1.5b getattr=2,141 (↑ from 1,855), 1.6/1.7 now radon-sourced (22 MI-C files), 1.9 NEW import-allowlist=9 KEPT.
- New patterns: 17 (top concern: debug-only broad exception swallows, 209 instances). Also: 485 deferred in-function imports (server.py=70), untyped ctx dict[str,Any] (33), inline 404-guard dup (13).
- Decay: ratchet **clean**, contracts **kept**, allow-list **9** (flat); top target **server.py** (#2 hotspot, MI-C, _setup_routes cc=115). linker_impl.py::validate_references cc=119 is highest single fn but low-churn (#12).
- Recommended next 3: (1) debug-only swallow audit via sentinel python_audit, (2) break back/runtime deferred-import cycles, (3) decompose server.py _setup_routes.
- Commit: a07c2a09b

## Smells Run — 2026-06-21
- Regressions: 9/9 checks passed (0 FAIL; 1.5b/1.6/1.7 standing TRACK)
- New patterns: 15 found
- Top concern: Logger acquired by string literal instead of __name__ (131 sites) — operability footgun, harness-blind
- Decay: ratchet clean, import contracts kept (5/5), allow-list 3 (no growth); top target dsl_parser_impl/workspace.py (#2 hotspot, MI-C — overlaps the unmigrated parse_block_with_dispatch ladder)
- Commit: 36d431cf8

## Smells Run — 2026-07-13
- Regressions: 4/4 checks passed (ratchet, import contracts, preflight, fitness code)
- New patterns: 0 elevated (2 TRACK notes: cli/db broad except, MCP dispatcher density)
- Top concern: standing MI-C hotspot `core/dsl_parser_impl/workspace.py` (owned by ratchet, not a new smell)
- Decay: ratchet clean, import contracts 6 kept / 0 broken; top target handlers_consolidated.py
- Commit: e20027608 (pre-stamp HEAD); cycle 484 improve stamp follows
- Mode: improve OWNED-IDLE first-exercise (no Workflow fan-out)

## Smells Run — 2026-07-20 (cycle 1191)
- Regressions: 4/4 checks passed
- New patterns: 0 elevated
- Top concern: none (TRACK standing debt only)
- Decay: ratchet clean, import contracts kept, allow-list stable; top target handlers_consolidated.py
- Commit: 0cf2de998
---
cycle 1232 2026-07-20: ratchet 6 pass; lint-imports 6 kept; xproject siblings scouted
