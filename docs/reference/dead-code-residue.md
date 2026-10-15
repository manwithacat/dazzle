# Dead-Code Residue

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The reviewed inventory behind the dead-definition ratchet: which unreferenced definitions are accepted residue, which family each belongs to, and what would retire it.

The gate is `tests/unit/test_dead_definition_ratchet.py`: it refuses growth of
unreferenced module-level definitions in `src/`, and refuses shrinkage of the
accepted list. Every accepted entry must also carry a family classification
(`tests/unit/fixtures/dead_definitions_families.json`), enforced by
`test_every_baselined_orphan_is_classified` — an inventory nobody has read is not
a review, so a new dead definition cannot be baselined silently.

**The accepted list is empty** (flense ship AI, 2026-10-15). Its last entry,
`compliance/slicer.load_document_spec`, went in ship AI; the nine families before
it were retired by deletion in ships J, K and AI: `superseded-runtime-path`,
`optional-extra-plumbing`, `domain-brief-and-llm-legacy`, `agent-and-loop-legacy`,
`qa-and-testing-helpers`, `semantics-and-kb-residue`, `doc-generation-residue`,
`cli-parity-helpers` and `error-and-report-helpers`. A new orphan is deleted, not
baselined; baseline one only for a dynamic entry point resolved at runtime, with
a family and a retire-when condition added here.

Before deleting what the gate names, check the finding is real (an import alias
once read as unused; mypy is the backstop) and not in `docs/api-surface/`.

## Below the gate: methods and properties (vulture ≥ 60 %)

The ratchet sees module-level definitions only. Ship AI reviewed every vulture
candidate at 60 % confidence (functions, methods, properties, classes; dataclass
and pydantic fields are data shape and were not candidates) against `src`,
`tests`, `scripts`, `packages`, `docs`, skills, hooks, CI and the AegisMark,
cyfuture and pennydreadful checkouts. These were reviewed and **kept**, by reason:

| reason | what |
|---|---|
| registered by decorator or dispatch table | CLI commands, FastAPI routes, pydantic validators, `@heuristic` sentinel checks, Temporal `@workflow.signal` |
| interface member with several implementations | `ProcessAdapter.suspend_process`/`resume_process`, the state stores' `get_schedule_spec`/`list_schedule_specs`, `channel_kind`, `EventBus.get_consumer_status`/`clear_dlq`, `FileStorage.get_url`, OpenTelemetry `force_flush` |
| `http/events/` in full | DD-006 names the event core |
| retention paths, unwired rather than superseded | channel `OutboxRepository` (its `email_outbox` table is still created at boot; dropping it needs a revision), `TokenStore.cleanup_expired`, `GrantStore.expire_stale_grants` |
| test and QA infrastructure | `qa_sign`, `qa_provision`, `vendor_mock`, `perf.tracer.reset_tracer`, `testing.session_manager` helpers, `tenant/metrics` counters, the ratchet helpers in `fitness/` (`compare_complexity`, `stale_baseline_clusters`, `count_swallows`) and `db/artifact_registry` (`framework_boot_entries`, `concrete_creators`) the gates call |
| read by the tests of the owning feature as an assertion or setup helper | IR query properties (`is_pii`, `is_grant_check`, `action_names`, `get_computed_field` …), `KnowledgeGraph.query`, `get_activity_sessions`, `controls_by_id`, `ParamResolver.set_override`, `save_processes` and the copy/theme/workspace/page-spec accessors; deleting them rewrites tests, so they go when those tests are retargeted |
| consumer constructs it | `BarChart.label` (AegisMark's cohort and class-summary viewers pass it; the renderer does not draw it, and wiring it needs a HaTchi-MaXchi seam change) |
| named by a counter-prior | `route_overrides.scan_handler_for_raw_db` (`raw-db-in-custom-route`, #1420) |
| unused parameters in kept signatures | callers pass them; removal is a signature change, not a definition deletion |

A kept entry that loses its reason is deleted, not re-classified.
