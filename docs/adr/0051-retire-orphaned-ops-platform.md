# ADR-0051: Retire the orphaned ops platform

**Status:** Accepted (2026-07-02) — #1525

## Context

The "ops platform" — 12 modules (~5,000 LOC) under `src/dazzle/http/runtime/`
(`ops_integration`, `analytics_collector`, `ops_database`, `health_aggregator`,
`api_tracker`, `api_middleware`, `email_templates`, `spec_versioning`,
`system_entity_store`, `admin_api_routes`, `deploy_history`, `rollback_manager`)
plus the Control Plane UI assets (`page/runtime/static/ops/`) — was born 2025-12-23
(`d6cd48a34`, pre-Dazzle DNR era) as a **single-founder SaaS operator cockpit**:
separate ops database, health dashboard, event explorer, external-API cost
tracking, tenant usage analytics, email open/click tracking, and GDPR retention
config, served at `/_ops/ui/`. Its only real consumer was the Founder Console
(`/_console/`); `mount_ops_platform()` was never wired into `server.py` /
`app_factory.py` at any point in the platform's history.

It was stranded on 2026-03-26 by #703, when the DSL-native admin workspace
(#686) replaced the console and deleted the routes that reached it. The ADR-0041
`back/`→`http/` rename then carried the corpse forward. The v0.92.69 vitality
connectedness report (#1521) resurfaced it as the largest orphan cluster in the
tree, and the #1525 capability archaeology (posted on the issue) produced a
per-module verdict table.

## Decision

**Delete the platform** (ADR-0003 clean break): the 12 modules, the static ops
UI, the three dedicated PG test files, the `ArtifactClass.OPS_DB` registry row +
enum member (ADR-0047), the four ops entries in the DDL-sweep allowlist, and the
super-admin **Trigger Deploy / Rollback** buttons in `core/admin_builder.py`
whose `/_admin/api/deploys/*` endpoints lived in the never-mounted
`admin_api_routes` (they always 404'd).

Kept, explicitly out of scope: `sse_stream.py` / `sse_wiring.py` (live at
`/_ops/sse/events` via `server.py`) and `device_registry.py` (live boot DDL +
registry entry).

## Rationale

1. **The design centre already lost.** A bespoke founder cockpit with its own
   parallel database lost architecturally to the DSL-native admin workspace in
   March 2026. There is no "spec and reimplement the platform" — the spec *was*
   the founder console, and #703 was its verdict.
2. **The thesis-relevant capability was already salvaged by design.** ADR-0050
   examined this exact code and deliberately rebuilt end-user usage capture
   *narrow* (`_dazzle_usage_events`, `usage_routes.py`, shipped v0.92.57–66),
   explicitly declining to adopt the platform.
3. **Everything else has a modern substitute**: latency → `dazzle perf` + OTLP;
   health → `/health` + `http/metrics/` + Prometheus `/_dazzle/metrics`;
   operator UI → admin workspace; email send → `http/email/` + channels; spec
   history → git + drift-gated api-surface baselines; virtual-entity reads →
   the #1004 repository provider path.
4. **Reviving would cost more than rebuilding.** It means registering five
   framework tables (ADR-0047/0044) and hardening unauthenticated ops routes to
   serve dashboards that duplicate Prometheus/Grafana.

## Salvage

One capability has **no substitute**: outbound **LLM cost tracking**
(`api_tracker.py`'s provider cost calculators), newly relevant with AIJob
(ADR-0043) and the `llm` subsystem. A narrow reimplementation on the ADR-0050
pattern (capture at the `llm/driver.py` seam → one registered
`_dazzle_llm_calls` table → `dazzle perf` cost view + MCP `costs` op) is filed
as a follow-up issue rather than blocking this retirement.

## Consequences

- The `deploys` admin region (`DeployHistory` framework admin entity) remains
  declared but now has **no writer at all** (the deleted `deploy_history` store
  was the only one). Removing the entity touches the admin-entity suite, RBAC
  matrix, and compliance `expected/` references fleet-wide — deferred as an
  explicit follow-up rather than bundled here.
- `dev_docs/observability_platform.md` remains as the historical intent
  document; its content no longer describes shipping code.
- Fitness baselines (clone / deferred-imports / IR-reader) regenerated to lock
  in the deletion, per the #1526 precedent.

## Rejected

- **Revive opt-in** (dazzle.toml flag): pays the registration + auth-hardening
  cost for capabilities with substitutes; resolves the analytics double-capture
  by construction only by duplicating ADR-0050's decision.
- **Partial retire, keep health_aggregator**: `/health` + Prometheus cover the
  need; history/alerting belongs in the metrics stack, not a bespoke store.
- **Defer with tombstone**: ADR-0050's "Rejected: leave it implicit" applies
  verbatim — an unmarked orphan is how this got lost the first time.
