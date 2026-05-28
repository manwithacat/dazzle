# Code Smells Report — 2026-05-28

Commit: 0bcd50ce (v0.80.22)
Scope: `src/dazzle/` — the merged tree (`back/`, `ui/`, `render/`). `tests/`, `examples/`, auto-generated excluded.
Method: `/smells` Workflow (`.claude/workflows/smells.js`) — 4 parallel finders, schema-validated.

## Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | No swallowed exceptions | **FAIL\*** | 3 hits, all `except Exception:`+bare `pass` in **test fixtures** (`back/tests/test_e2e.py:197`, `test_file_storage.py:67,85`); **0 in production code**. \*Effectively PASS for prod — grep-count FAIL only. |
| 1.2 | No redundant except tuples | **PASS** | 0 hits across all three variants |
| 1.3 | Core→MCP isolation | **FAIL** | 1 real hit: `core/docs_gen.py:389` function-local `from dazzle.mcp.server.tools_consolidated import …` |
| 1.4 | No `project_path: Any` in handlers | **PASS** | 0 hits |
| 1.5a | No silent event handlers | **FAIL\*** | 17 grep hits in `back/events`+`back/channels`, but all narrow/intentional (CancelledError, TimeoutError, URL-parse ValueError, ImportError+log). **Zero broad `except Exception` swallows.** \*Effectively PASS. |
| 1.5b | `getattr()` string-literal count | **TRACK** | 1,855 (↑231 vs 1,624 last round); ≥200 threshold — IR dynamic access |
| 1.6 | Functions >150 lines (aspirational) | **TRACK** | 148 (↑13 vs 135). Top: `get_workflow_guide`(777), `create_site_page_routes`(653), `_setup_routes`(552), `_discover_entities`(452), `init_workspace_routes`(449) |
| 1.7 | Classes >800 lines (aspirational) | **TRACK** | 12 (↑1 vs 11). Top: `WorkspaceParserMixin`(2612), `EntityParserMixin`(2592), `DazzleBackendApp`(1673), `TestRunner`(1618), `ProcessParserMixin`(1508) |
| 1.8 | Alpine `@<event>.window` lifecycle leaks | **FAIL** | 2 hits: `ui/runtime/static/test-data-table.html:174,175` (#795). **Previously hidden** — the old command scanned the deleted `src/dazzle_ui/templates/` path. |

**Genuine production regressions: 2** — 1.3 (core→mcp import) and 1.8 (Alpine window bindings, prev. masked by a stale scan path). 1.1/1.5a are grep-count FAILs their own details exonerate.

## New Patterns Found

| # | Pattern | Category | Inst. | Root cause (short) | Canonical fix (short) |
|---|---------|----------|-------|--------------------|------------------------|
| 1 | Silent swallow of IO/JSON-decode on persisted state | Error handling | 119 | `except (JSONDecodeError, OSError): return <empty>` conflates corrupt with missing | Split `FileNotFoundError` (silent) from corrupt (log WARNING) via one `load_json_or` util |
| 2 | Outbound I/O bypasses shared retry helper | Error handling | 7 | `core/http_client` retry is opt-in/undiscoverable; SMTP/aiohttp/SES/urllib call raw | Route all outbound prod I/O through retry wrappers; add non-httpx wrappers |
| 3 | `back/` imports `dazzle.ui.*` | Coupling | 17 | #1086 left the broad `back→ui` ban "aspirational"; no enforced alt location | Move shared helpers to `dazzle.render`; ratcheting import gate |
| 4 | Function-local imports as circular-dep workaround | Coupling | 22 | Bidirectional coupling; deferring import hides the cycle | Extract shared types to leaf modules; restore top-level imports |
| 5 | Per-module FastAPI import guard duplicating `_fastapi_compat` | Duplication | 13 | Consolidation never finished; new modules copy old headers | Import all FastAPI symbols from `_fastapi_compat`; AST gate |
| 6 | `x.value if hasattr(x,"value") else str(x)` | Duplication | 45 | IR fields typed `str \| Enum`; no shared helper | One `enum_str()` helper; normalize IR to `str` at parse time |
| 7 | `s if isinstance(s,str) else s.name` state norm | Duplication | 8 | `StateMachineSpec.states` is `list[str]` yet readers guard; CLAUDE.md endorses idiom | Normalize once at link time; delete guards; update the Gotcha |
| 8 | Mixin cross-calls `# type: ignore[attr-defined]` not `ParserProtocol` | Type safety | 8 | `ParserProtocol` exists but no mixin inherits it | Make mixins inherit `ParserProtocol`; add missing methods; drop ignores |
| 9 | `step: object` param forcing attr-defined ignores | Type safety | 12 | `cli/guide.py:_emit_step` typed `object` then suppresses fallout | Type with concrete IR step / Protocol; drop 12 ignores |
| 10 | Oversized functions (>80 lines) | Complexity | 582 | No length gate; route factories inline every route | Extract sub-builders; ~80-line ceiling; ratchet test |
| 11 | Deeply nested conditionals (≥5) | Complexity | 395 | Parser/renderer arrow-code; no dispatch tables | Guard clauses + dispatch dicts (continues the v0.70.x sweep) |
| 12 | God classes (>500 LOC / ≥20 methods) | Complexity | 56 | Mixin inheritance makes `self.helper` free; unbounded growth | Split into thin dispatcher + free helper functions; inject services |
| 13 | Thread-unsafe lazy-init singletons | Mutable globals | 3 | Unlocked `if _x is None: _x = build()`; race invisible single-threaded | Double-checked lock (template already in `retry_accumulator.py`) or `RuntimeServices` |
| 14 | Module-level mutable cache mutated after import | Mutable globals | 6 | Registry/cache as top-level dict slips past ADR-0005 | Own via `RuntimeServices`/`ServerState`; or `Final` populate-once |
| 15 | Backward-compat shims / dual-signature wrappers | (ADR-0003) | 8 | ADR-0003 says no shims; "migrate next slice" never happens | Delete shim + migrate callers same commit |

(Full root-cause / done-criteria / enforcement per pattern are in the workflow result; reproduce via `/smells`.)

## Recommended Next Actions

1. **1.3 core→mcp import** — move `get_all_consolidated_tools` access out of `core/docs_gen.py` (real layer violation; smallest fix).
2. **Pattern 5 (`_fastapi_compat` duplication, 13×)** — pure consolidation, AST-gateable; exactly the drift class this round is meant to catch.
3. **Pattern 1 (silent IO swallow, 119×)** — highest-instance correctness risk; the `load_json_or` util + drift gate addresses the whole class.
4. **1.8 Alpine window bindings** — port the two `test-data-table.html` listeners to `init()/destroy()` (#795 pattern).

## Comparison with Previous Round (2026-05-15, d1706bd3 v0.70.0)

- **Regressions:** 1.3 now failing (function-local core→mcp import — prior grep missed the function-local form); 1.8 now failing **because the scan path was fixed** (old command scanned the deleted `src/dazzle_ui/templates/`; v0.80.22 scans `src/dazzle/ui/` and found real bindings).
- **Calibration shift:** 1.1 and 1.5a flipped PASS→FAIL only because this round counts test-fixture / intentional-narrow hits; production posture is unchanged (0 prod swallows). The workflow's regression finder should mark PASS when all hits are test-only or intentional — a prompt-calibration note for `smells.js`.
- **Metrics drift:** getattr 1,624→1,855; fns>150 135→148; classes>800 11→12 — all slowly growing, no length/nesting gate yet (patterns 10–12).
- **New systemic patterns** vs last round: outbound-retry bypass (2), circular-import deferral (4), enum/state normalization duplication (6,7), parser-mixin type-ignore (8) — surfaced by the three judgment finders.
