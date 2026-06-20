# Code Smells Report — 2026-06-19

Commit: a07c2a09b (v0.83.28)
Scope: `src/dazzle/` — the merged tree (`back/`, `ui/`, `render/`). `tests/`, `examples/`, auto-generated excluded.
Method: `/smells` Workflow — 4 parallel finders (regressions + 3 pattern cats + **decay-harness**), schema-validated.

## Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | no-swallowed-exceptions | **PASS** | Zero `except Exception: pass` in src/. The only `except Exception:`+bare-pass hits are in src/dazzle/http/tests/ (test_e2e.py:197, test_file_storage.py:67/85) — test fixtures, not production code. |
| 1.2 | no-redundant-except-tuples | **PASS** | Zero hits across all three patterns: `except (ImportError, Exception)`, `except (json.JSONDecodeError, Exception)`, `except (JSONDecodeError, Exception)`. |
| 1.3 | core-mcp-isolation | **PASS** | Zero `from dazzle.mcp` imports in src/dazzle/core/. Consistent with the live import-linter `core stays backend- and UI-agnostic` contract (KEPT) which subsumes this. |
| 1.4 | no-project-path-Any | **PASS** | Zero `project_path: Any` in src/dazzle/mcp/server/handlers/. |
| 1.5a | no-silent-event-handlers | **PASS** | 17 raw `pass`/`return` matches but all are benign narrow handlers: asyncio.CancelledError on task-teardown (base_event_bus/postgres_bus/publisher/kafka_bus/manager), TimeoutError on poll loops (postgres_bus:695, queue adapters), ImportError optional-dep w/ logger.debug (ses_webhooks), FileNotFoundError Docker-absent (detection), ValueError/IndexError on int-parse (stream/queue providers, email:53), plus a class-body `pass` (bus.py:336 EventBusError). No silent generic event swallow. |
| 1.5b | getattr-string-literals | **TRACK** | 2141 `getattr(` occurrences in src/ — above the <200 PASS threshold, so TRACK with the count (standing-debt baseline). |
| 1.6 | complexity-creep | **TRACK** | From tests/unit/fixtures/complexity_baseline.json: 22 MI-rank-C files; highest-CC function = dazzle/core/linker_impl.py::validate_references at CC 119. Standing baseline (live ratchet gates new CC>15 / MI drops in CI). |
| 1.7 | god-files | **TRACK** | 22 files at MI rank C in the baseline: persona_journey.py, auth/store.py, site_section_builder.py, repository.py, server.py, workspace_aggregation.py, test_auth.py, cli/testing.py, parser entity/process/workspace.py, linker_impl.py, validation/extended.py, lsp/server.py, mcp dsl_test/rhythm handlers, pptx_slides.py, python_audit.py, dsl_test_generator.py, test_runner.py, template_compiler.py, page_routes.py. linker_impl.py is both MI-C and high-CC (validate_references=119) so it's the top god-module/hotspot cross-ref. |
| 1.8 | alpine-window-bindings | **PASS** | Zero `@(pointer\|mouse\|key\|resize\|scroll\|click\|touch)*.window` bindings in src/dazzle/page/ .html templates. |
| 1.9 | import-contract-allowlist | **PASS** | lint-imports exits 0: 3 contracts KEPT, 0 broken (1465 files / 9084 deps analyzed). TRACK: ignore_imports allowlist = 9 total (core->back: 2 [eventbus_adapter→envelope, eventbus_adapter→auth.events]; ui->back: 6 [all combined_server→back.*]; back->sqlite: 1 [test_relations→sqlite3]). Memory recorded '2 structural edges allow-listed' for core specifically — that core count is unchanged at 2; the 9 is the all-contract total. |

**Genuine production regressions (FAIL): 0.** TRACK rows (1.5b/1.6/1.7/1.9) are standing-debt counters, not breakage.

## New Patterns Found

Ordered by category severity × instance count.

| Pattern | Category | Inst. | Root cause | Canonical fix |
|---------|----------|-------|-----------|---------------|
| Debug-level-only exception swallows (except Exception -> logger.debug, no re-raise / no er | Error handling | 209 | A house style of 'catch everything, log at debug, carry on' has spread as the default defensive idiom for any code path the author was unsur… | Decide intent per site: (a) if the exception is expected and benign, catch the SPECIFIC type and document why it is safe; (b) if it is unexp… |
| Broad silent exception swallows (except Exception/ImportError -> pass\|continue with no log | Error handling | 36 | Optional-feature degradation (`except ImportError: pass`, 29 of 36) and best-effort side-paths are written as fire-and-forget. There is no s… | Never let a broad `except` body be only `pass`/`continue`. For optional imports, gate on the dependency explicitly (try/except ImportError a… |
| Intra-layer deferred (in-function) imports to dodge circular dependencies | Coupling | 485 | back/runtime modules have grown bidirectional dependencies (server.py <-> app_factory <-> subsystems <-> store, etc.). Rather than extractin… | Break the cycle structurally, not lexically: extract the shared types/protocols into a leaf module (e.g. a `*_protocols.py` or `*_types.py` … |
| Weakened typing (field/param annotated `Any`/`object` solely to avoid an import cycle) | Coupling | 14 | Core IR dataclasses (appspec.py, domain.py, fields.py, triples.py, conditions.py, access.py) cross-reference each other, forming cycles amon… | Use `if TYPE_CHECKING:` imports plus string/forward-ref annotations (PEP 563-style) so the real type is visible to mypy without a runtime im… |
| Backward-compat shims and dual-signature wrapper functions (violate ADR-0003 clean-break r | Coupling | 8 | Despite ADR-0003 ('no backward compat shims — clean breaks, update all callers in same commit'), the tree carries pure re-export modules (pp… | Per ADR-0003, delete the shim and migrate all callers in the same commit. For dual-signature wrappers, pick the config-object form, convert … |
| Mislocated cross-layer module: ui/runtime/combined_server.py imports dazzle.http (ui->back | Coupling | 6 | combined_server.py is the unified back+ui composition entrypoint but physically lives under dazzle.page, so it must reach down into dazzle.bac… | Relocate combined_server.py to its real layer — a composition root at or above back/runtime (e.g. back/runtime/combined_server.py, or a new … |
| Untyped `ctx: dict[str, Any]` threaded through every region builder | Type safety | 33 | The Fragment substrate (#1042, ADR-0023) was sold as a fully *typed* primitive tree, but the render-context the builders consume is still a … | Define a single `RegionContext` TypedDict (or frozen dataclass) capturing the keys the builders actually read (rows, columns, endpoint, regi… |
| `# type: ignore[arg-type]` masking str→Literal narrowing at Fragment-primitive boundaries | Type safety | 12 | Fragment primitives (FormStack.method/mode, Field.kind, SortHeader.current_direction, Dimension.truncate, ConsentDefaults override) declare … | At each boundary, narrow instead of ignore: type the lookup dict's values as the Literal (`widget_to_field_kind: dict[str, FieldKind]` then … |
| Inline `HTTPException(status_code=404, detail="Not found")` 404-guard copy-paste | Duplication | 13 | Every read/update/delete handler ends with the same `if result is None: raise HTTPException(status_code=404, detail="Not found")` guard, cop… | Add one helper in the handlers package, e.g. `def require_found(value: T \| None, detail: str = "Not found") -> T: if value is None: raise HT… |
| Repeated PersonaSpec / node identity fallback `getattr(x, "name", None) or getattr(x, "id" | Duplication | 7 | PersonaSpec identity is `.id`, not `.name` (documented as a Gotcha in CLAUDE.md), so callers defensively write `getattr(p, "name", None) or … | Add `def spec_display_id(spec: object, default: str = "unknown") -> str: return getattr(spec, "name", None) or getattr(spec, "id", default)`… |
| Repeated state-machine state normalisation `s if isinstance(s, str) else s.name` | Duplication | 6 | `StateMachineSpec.states` (and transition from_state/to_state) is a heterogeneous `list[str \| StateSpec]` with no normalising accessor, so e… | Add a method/property on StateMachineSpec, e.g. `def state_names(self) -> list[str]` and `def name_of(state: str \| StateSpec) -> str`, and h… |
| Long if/elif keyword chains and hand-rolled INDENT/while-DEDENT/`if key=="..."` scaffolds  | Complexity | 14 | Each DSL construct's parser mixin grew its own copy of the same block-scanner skeleton (consume INDENT, loop until DEDENT, read key token, e… | Introduce one reusable block-parser helper: parse_kv_block(spec) where spec maps key-name -> (value-parser, target-field), driving the INDEN… |
| Scattered parallel ScalarType-to-representation maps re-hand-rolled in every consumer (and | Complexity | 6 | There is no single owner of 'how a ScalarType maps to a representation'. Each subsystem that needs a projection of ScalarType (SQLAlchemy ty… | Define the mappings as data next to the ScalarType enum (or a small registry module) — one table per target representation, keyed by ScalarT… |
| God methods / god classes in the runtime: wide constructors and mega-orchestrator methods  | Complexity | 5 | DazzleBackendApp and Repository are the two seams where AppSpec is turned into a live FastAPI app and into SQL. Every new framework feature … | Extract each cohesive build phase into a named collaborator with a single public method that takes an explicit context and returns its artif… |
| Deeply nested control flow (4-8 levels) concentrated in parser sub-block bodies and the pa | Complexity | 4 | This is the downstream symptom of the copy-pasted KV-block scaffold plus inline validation: a method opens with the INDENT guard, loops unti… | Flatten with early-return/guard clauses and lift per-key validation into named predicate helpers (validate_tone, validate_mode) invoked afte… |
| Hidden process-wide configuration singletons mutated via global rebind (or a class-attr wr | Mutable globals | 6 | Several runtime flags and references (dark-mode toggle, haptic, RLS user-attr names, retry accumulator, task-store backend, the AuthStore re… | Route these through the sanctioned dependency carriers (RuntimeServices / ServerState / request.app.state) so the value is an explicit depen… |
| Compat shim: dual legacy string representation maintained alongside the typed predicate al | Mutable globals | 2 | aggregate_legacy.py keeps a string-based 'legacy where' format and condition_expr_to_legacy_where converters that exist purely to translate … | Per the no-backward-compat-shims rule (ADR-0003), delete aggregate_legacy.py and update the remaining workspace_aggregation.py call sites to… |

## Structural Decay (live harness)

The CI ratchet + import contracts gate *new* decay; this is the standing baseline.

- **Ratchet:** clean   **Import contracts:** kept, allow-list size 9
- **Priority refactor targets** (high-churn × MI-rank-C): `dazzle/http/runtime/server.py`, `dazzle/core/dsl_parser_impl/workspace.py`, `dazzle/core/dsl_parser_impl/entity.py`, `dazzle/testing/test_runner.py`, `dazzle/http/runtime/auth/store.py`, `dazzle/cli/testing.py`, `dazzle/core/linker_impl.py`

| Rank | Hotspot file | Score | Churn | MI |
|------|--------------|-------|-------|----|
| 1 | `dazzle/mcp/server/handlers_consolidated.py` | 8343.9 | 111 | A |
| 2 | `dazzle/http/runtime/server.py` | 6800 | 68 | C |
| 3 | `dazzle/core/dsl_parser_impl/workspace.py` | 6000 | 60 | C |
| 4 | `dazzle/core/lexer.py` | 5583.2 | 78 | A |
| 5 | `dazzle/core/ir/workspaces.py` | 5415.7 | 64 | B |
| 6 | `dazzle/core/dsl_parser_impl/entity.py` | 5200 | 52 | C |
| 7 | `dazzle/render/fragment/primitives/data.py` | 5107.2 | 60 | B |
| 8 | `dazzle/testing/test_runner.py` | 4900 | 49 | C |
| 9 | `dazzle/core/linker.py` | 4504.8 | 61 | A |
| 10 | `dazzle/http/runtime/auth/store.py` | 4200 | 42 | C |

Highest-CC functions: `linker_impl.py:validate_references` (cc 119); `server.py:DazzleBackendApp._setup_routes` (cc 115); `page_routes.py:_build_dispatch_ctx` (cc 108); `list_handlers.py:_list_handler_body` (cc 106); `template_compiler.py:compile_appspec_to_templates` (cc 101)

> Decay is holding flat: the complexity ratchet passes clean against the committed baseline, all 3 import contracts are KEPT, and the cross-layer allow-list is still at 9 (no growth). The single best refactor target this round is dazzle/http/runtime/server.py — it is the #2 churn hotspot, MI rank C, and houses the second-highest-CC function in the tree (DazzleBackendApp._setup_routes, cc 115), so a route-setup decomposition buys the most. (linker_impl.py:validate_references at cc 119 is the highest single function but its file ranks #12, lower churn.)

## Recommended Next Actions

1. **Debug-only broad exception swallows (209 instances)** — the dominant *semantic* finding the harness can't see. Decide intent per site: narrow the exception type, or raise it to `warning`/`exception` so prod isn't blind. Reserve `except Exception → logger.debug` for genuinely cosmetic best-effort, with an inline comment. Enforce via the sentinel `python_audit` agent.
2. **`back/runtime` god-modules via 485 deferred in-function imports** (server.py alone = 70) — the cycle-dodge that hides the tangle. Break it structurally: extract shared types/abstractions to leaf modules so top-level imports restore. Pairs with the harness's #1 priority target.
3. **Refactor `server.py` (the harness's top target)** — #2 churn hotspot, MI-rank-C, houses `DazzleBackendApp._setup_routes` (cc 115). Decompose route setup into per-area sub-builders; the complexity ratchet then locks the gain.

## Comparison with Previous Round (2026-05-28, v0.80.22)

- **Regressions: 2 → 0.** Both genuine production FAILs from last round are **RESOLVED**: 1.3 core→mcp function-local import (`core/docs_gen.py:389`) is gone (and now double-locked by the live import-linter `core` contract); 1.8 Alpine `@window` bindings (`test-data-table.html`) are gone.
- **Calibration fix landed.** 1.1 and 1.5a — previously over-reported as grep-count FAILs — now correctly read **PASS** (the finder applies the test-only/intentional calibration).
- **New patterns: 15 → 17.** New framings this round: debug-only swallow (209) split out from the silent-swallow class; untyped `ctx: dict[str,Any]` region-builder thread (33); inline 404-guard copy-paste (13). The deferred-import coupling count jumped 22 → 485 as the finder broadened from 'circular-dep workaround only' to all intra-layer deferred dazzle imports.
- **Decay delta:** ratchet **clean**, contracts **kept**, allow-list flat at **9** (no growth — the ratchet posture holds). `getattr()` count rose 1,855 → 2,141. No file climbed into a *new* C-rank vs the committed baseline (the ratchet guarantees this). Top hotspot/target unchanged: `server.py`.
