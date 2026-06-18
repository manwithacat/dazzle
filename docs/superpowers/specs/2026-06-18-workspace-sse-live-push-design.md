# Workspace SSE live push — #1399 slice 1

**Status:** design approved (brainstorming), pending implementation plan
**Issue:** #1399 (live-refresh follow-ups), slice 1 of 1 remaining (slices 2 + 3 shipped v0.83.5 / v0.82.80)
**Date:** 2026-06-18

## Goal

A workspace declaring `live: on` pushes "something changed" signals to connected
browsers over Server-Sent Events, so its cards refresh **instantly** on entity
mutations instead of waiting for the next `refresh: every Ns` poll tick. The poll
is retained as a fallback heartbeat.

## Locked decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| **Signal shape** | **Nudge-only** — event carries entity-type + id, *no row data* | The card re-fetches via its existing scope-gated `hx-get`; SSE can never leak a row the user can't see. The fetch path stays the single source of truth. |
| **Opt-in** | Explicit `live: on` workspace keyword | SSE holds an open connection per client; opt-in keeps connection cost under author control. |
| **Poll relationship** | SSE **supersedes** poll, but `every Ns` is retained as a fallback heartbeat | Instant push when connected; graceful degradation if the SSE connection drops. Slice 2's terminal-state stop still applies to the poll. |
| **Event source** | Reuse the existing **HLESS framework EventBus** (postgres tier) + existing `/_ops/sse/events` endpoint | No DB-poll bridge, no new transport. The bus is already wired and started by `EventsSubsystem`. |
| **Bus consolidation** | Out of scope | Two parallel realtime buses exist (`EntityEventBus`→WebSocket vs framework bus→SSE). This slice uses the framework→SSE path only; consolidation is a future cleanup. |

## Current state (verified 2026-06-18)

What already exists:
- **Framework EventBus is live by default.** `subsystems/events.py:EventsSubsystem.startup`
  builds `EventFramework(database_url=ctx.config.database_url)` (postgres tier per
  ADR-0008) and starts it via a registered lifespan hook in every `dazzle serve`.
  Reachable at `ctx.app.state.services.event_framework`.
- **SSE transport is built but unmounted.** `runtime/sse_stream.py` has a full
  `SSEStreamManager` + `create_sse_routes()` exposing `/_ops/sse/events?entity=&tenant_id=`
  (text/event-stream, Last-Event-ID reconnection, heartbeats).
- **Client half is wired.** When `WorkspaceContext.sse_enabled` is true,
  `render/fragment/renderer/_render_dashboard.py` emits `hx-ext="sse"`,
  `sse-connect="{sse_url}"`, and appends `sse:entity.created, sse:entity.updated,
  sse:entity.deleted` to each card's `hx-trigger`.
- **A transactional emit mixin exists** (`events/service_mixin.py:EventEmittingMixin`)
  that emits via the outbox for transactional safety.

What is missing or disconnected (the actual work):
1. **`WorkspaceSpec` has no `live`/`sse_url`.** `ui/runtime/workspace_renderer.py:928`
   reads `workspace.sse_url`, but the field doesn't exist on the IR, so `sse_enabled`
   is never true and the client half never activates.
2. **The SSE platform is never mounted.** `mount_ops_platform` is referenced *only in
   its own docstring* — `/_ops/sse/events` does not exist in a running app.
3. **`CRUDService` emits nothing.** It does not inherit `EventEmittingMixin`, and that
   mixin is inherited by **nobody** — it is dead/aspirational infra today. No entity
   mutation publishes any event.
4. **Three-way topic-namespace mismatch.** The mixin emits `app.<Entity>.created`;
   `SSEStreamManager.STREAM_TOPICS` subscribes to literal `entity.created`; the client
   listens for `sse:entity.created`. None line up.

## Architecture — the chain to connect

```
CRUDService.create/update/delete
  └─(publish, transactional via outbox)→ framework EventBus  [GAP 3]
        topic: per-entity  app.<Entity>                       [GAP 4: namespace]
  └→ SSEStreamManager subscribes to the app entity topics     [GAP 2 + 4]
        re-labels SSE `event:` field → entity.<action>
  └→ GET /_ops/sse/events?entity=&tenant_id=  (mounted)        [GAP 2: mount]
  └→ browser EventSource (sse-connect), card hx-trigger fires  [exists]
  └→ card hx-get → scope-gated region/surface fetch            [exists, slices 2/3]
```

## Components (each small, single-purpose)

### 1. IR — `WorkspaceSpec.live` (`core/ir/workspaces.py`)
Add `live: bool = False` to the frozen `WorkspaceSpec` model. `sse_url` remains a
**runtime-computed** value (not IR) — derived in the renderer from `live` + request
tenant. Regenerate the `ir-types` API-surface baseline + DSL→IR golden master; add a
CHANGELOG entry under Added.

### 2. Parser — `live: on` keyword (`dsl_parser_impl/workspace.py`)
A workspace-body boolean keyword `live: on` / `live: off` (default off). No floor or
interval logic. Drift test in `test_docs_drift.py` already gates keyword lists — update
the grammar reference (`docs/reference/grammar.md`) if workspace keywords are enumerated.

### 3. CRUD emission (`runtime/service_generator.py:CRUDService`) — **GAP 3**
Make `CRUDService.create/update/delete` publish an entity-lifecycle event to the
framework bus when an event framework is present. **Recommended:** route through the
existing `EventEmittingMixin` (mix it into `CRUDService`, wire `set_event_framework`
in `EventsSubsystem`'s service loop) so we inherit transactional outbox safety rather
than a raw publish that could fire on a rolled-back txn. Payload is **minimal**
(entity name + id + tenant) per the nudge-only decision — no full row.

> Risk: the mixin/outbox→publisher→bus chain is currently unexercised end-to-end.
> The plan MUST include a runtime-path test (mutation → SSE frame), not just a unit
> test of the emit call — see "Verify the runtime path, not just the unit" lesson.

### 4. Topic reconciliation (`runtime/sse_stream.py`) — **GAP 4**
The EVENTS stream must subscribe to the topic(s) `CRUDService` actually publishes
(`app.<Entity>`), and re-label each delivered envelope's SSE `event:` field to
`entity.<action>` so the **existing** client triggers (`sse:entity.created/updated/
deleted`) fire unchanged. Subscription strategy (resolve in plan): enumerate per-entity
`app.<Entity>` topics from the AppSpec vs. a single shared topic vs. wildcard subscribe
(depends on the bus `subscribe()` capability). Keep the `entity=` query filter working
so a card can scope its stream to its own entity.

### 5. Mount the SSE platform independently of ops dashboard (`runtime/server.py` / a subsystem) — **GAP 2**
Mount the `SSEStreamManager` + `create_sse_routes()` wired to the `EventsSubsystem`
framework bus, gated on "any workspace declares `live`" (or always when a bus exists) —
**not** behind the (also-unmounted) ops dashboard. Prefer a small dedicated mount path
over invoking the whole `mount_ops_platform` (which drags in health/analytics/api-calls
collectors this slice doesn't need).

### 6. Renderer wiring (`ui/runtime/workspace_renderer.py`)
When `workspace.live`, set `WorkspaceContext.sse_url =
"/_ops/sse/events?entity=<...>&tenant_id=<resolved-tenant>"`. This flips the already-built
`sse_enabled` path on. Expect **zero** change to `_render_dashboard.py` — cards keep their
`every Ns` (fallback) and gain `sse:entity.*`.

## Scope / RBAC / tenancy

- **Nudge-only ⇒ no row data on the wire.** An event reveals only "an entity of type X
  changed". The re-fetch is the existing scope-gated endpoint, so no row leak is possible.
- **Tenant isolation:** populate `tenant_id` in the rendered `sse-connect` URL from the
  request's resolved tenant; the `/_ops/sse/events` endpoint already filters on it, so
  cross-tenant nudges never wake other tenants' clients.

## Testing

- **Parser/IR:** `live: on` → `WorkspaceSpec.live is True`; default off; ir-types +
  golden-master baselines regenerated.
- **Renderer:** `sse_url` populated and `sse_enabled` true only when `live`; cards emit
  both the poll trigger and `sse:entity.*`.
- **Emission (unit):** `CRUDService.create/update/delete` publish the correct envelope to
  a mock framework bus; nothing emitted when no framework configured; nothing on rolled-back
  txn (outbox property).
- **Topic mapping (unit):** an `app.<Entity>.created` envelope delivered to the EVENTS
  stream produces an SSE frame with `event: entity.created`.
- **Mount:** SSE routes mounted in a normal app (no ops dashboard) when a workspace is `live`.
- **Runtime path (postgres-marked integration):** mutate an entity → a subscribed SSE
  client receives an `entity.updated` frame. This is the load-bearing test; the unit tests
  alone do not prove the outbox→publisher→bus→SSE chain flows.

## Out of scope (explicit)

- Consolidating `EntityEventBus` (WebSocket) with the framework bus (SSE).
- Payload/data-on-the-wire SSE (we ship nudge-only).
- Surface-level (non-dashboard) SSE — slice 3 covers surface *polling*; surface SSE can
  be a follow-up if needed.
- Per-field change events (`_tracked_fields` in the mixin) — not needed for nudge.

## Primary risks

1. **Outbox chain unexercised.** Mitigated by the mandatory runtime-path integration test.
2. **Topic-subscription model** (enumerate vs wildcard) depends on the bus `subscribe()`
   API — resolve early in the plan; it gates component 4.
3. **Default bus tier in non-postgres/dev contexts.** `database_url` is always set in the
   app runtime (ADR-0008), so postgres tier is expected; confirm `dazzle serve --local`
   still yields a subscribable bus (the plan should assert this, not assume it).
