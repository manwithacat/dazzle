# DD-006: Events DSL (`hless`, `stream`, `event_model`, `subscribe`, `projection`, `ingest`), the Kafka bus and the event-transport residue — parked until a consumer needs an ordered or replayable stream, live push, or a Redis-free bus

```yaml
id: DD-006
status: PARKED
issues: [1069, 1189, 1676, 1399]
adrs: [0057, 0047, 0017, 0003]
decided: 2026-10-12
decided_at_sha: 2de583aa741ecc4dfad1f369f6c773fa12f99966
parent: flense-programme
```

## One-line intent

No consumer app declares an event construct. Flense ship F (ADR-0057) removes
the event *vocabulary* of the DSL and the Kafka bus adapter, and keeps the
event *core* every consumer already runs: `EventsSubsystem`, the
transactional outbox and publisher, the inbox, and the Redis bus. (Flense
ship O corrected this list: `EventEmittingMixin` was never mixed into a CRUD
service and was removed — see *Already shipped*. Flense ship AR parked the
transport nobody selects — the Postgres and in-memory buses, the event
explorer, SSE live push and the channel delivery outbox — see *Runtime
transport* below.)

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`2de583aa741ecc4dfad1f369f6c773fa12f99966`), trimmed to what the forcing
consumer needs:

- Parser mixins `dsl_parser_impl/{hless,eventing,ingest}.py`, IR
  `core/ir/{hless,hless_validator,eventing,ingest,llm_events}.py`, the
  `validate_event_payload_secrets` / `validate_ingests` validators, the
  stream half of `validate_money_fields`, the guide-concordance check of
  `topic.event` completion refs, the entity `publish` directive, and the
  lexer keywords they used (`event_model`, `publish`, `subscribe`,
  `projection`, `topic`, `hless`, `strict`, `partition_key`,
  `ordering_scope`, `idempotency`, `derives_from`, `t_event`, …).
- Runtime: `http/runtime/ingest_{engine,routes}.py` (`POST /api/ingest/{name}`,
  the `_dazzle_ingest_fingerprint` table — dropped by revision 0022 after
  operator sign-off on 2026-10-13; re-add it with a new Alembic revision),
  `http/events/topology_drift.py` and
  `multi_tenancy.py`, `http/events/kafka_bus.py` plus the `kafka` tier in
  `tier.py`, and the `semantics validate_events` MCP op.
- Design points to keep: HLESS record kinds (INTENT / FACT / OBSERVATION /
  DERIVATION) with mandatory partition key, ordering scope and idempotency
  strategy per stream; money in FACT/INTENT payloads must be the `money`
  type; no secret-named fields in payloads. The name `hless` is deliberate
  (#1069 API-003 rejected renaming it).
- Counter-priors: do not let app code publish ad-hoc topics outside a
  declared stream; do not reintroduce a broker tier before Postgres/Redis
  are shown insufficient for the consumer's volume.

## Reopen when (consumer force)

1. **Named consumer** — pennydreadful rights auctions need an ordered or
   replayable bid stream (bids ordered per lot, replay to rebuild the
   auction state).
2. **Evidence of host workaround** — a consumer hand-rolling a bid log
   table with sequence numbers, or replay scripts over the outbox.
3. **Acceptance that unblocks** — the consumer's stream validates, bids are
   delivered in order per partition key, and a projection rebuilds from
   replay in that consumer's CI.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- The event core stays and starts for every consumer: `EventsSubsystem`
  builds the `EventFramework` (bus tier, outbox publisher, inbox, consumer
  groups). The `dazzle events` / `dlq` / `outbox` CLI groups were retired in
  flense ship J and the `/_dazzle/events/*` explorer in flense ship AR — no
  consumer ran either. What actually travels on it today:
  - **CRUD lifecycle events do not use the bus or the outbox.** `CRUDService`
    lifecycle callbacks feed the in-process `EntityEventBus`
    (`SystemRoutesSubsystem._wire_entity_events_to_bus`), whose handlers are
    integration mappings, LLM triggers, SLA timers and app handlers (cyfuture
    registers `add_sync_handler` for lifecycle and HMRC work). (Until flense
    ship AR, `sse_wiring` also published a nudge envelope for `live: on`
    workspaces; see *Runtime transport*.)
  - **Auth events** (`auth.user.registered` and siblings) are published
    straight to the bus by `auth/events.py`; cyfuture consumes them through
    `EventFramework.register_handler`.
  - **The process event-bus adapter** publishes its own envelopes to the bus.
  - **The transactional outbox has no framework writer.** Its only writer
    was `EventEmittingMixin`, which no CRUD service ever inherited (the
    `set_event_framework` wiring in `EventsSubsystem` never matched a
    service); flense ship O removed the mixin and that wiring. The outbox
    table, `EventFramework.emit_event` (the public append API) and the
    publisher that drains it stay as event core. A forcing consumer that
    needs transactional CRUD events needs the append inside the repository
    write transaction — the `CRUDService` lifecycle callbacks fire after the
    write, and the removed mixin handed `emit_event` the repository's backend
    object rather than the open transaction, so neither was transactional
    (mixin restore point: `src/dazzle/http/events/service_mixin.py` at
    `7879465836d4c38ded550e9c564f1a7d7d29d9e8`).
- AegisMark's production boot log confirms the **Redis Streams** bus
  (`REDIS_URL` set), so the Redis tier is core, not parked.

## Runtime transport (parked 2026-10-16, flense ship AR)

Operator decision 2026-10-16 (flense plan §10.3/§10.4 item 1): park the
event-transport residue, keep the Redis path cyfuture runs in production.
**Restore from commit** `5bba9833f5eec7decf209059c8dbbbf0afeded73` (main
before ship AR); `git show 5bba9833f:<path>` returns every file below.

**Removed.**

- `src/dazzle/http/events/postgres_bus.py` (919 lines): `PostgresBus` /
  `PostgresConfig` (a LISTEN/NOTIFY bus with self-created `{prefix}events`,
  `{prefix}consumer_offsets` and `{prefix}dlq` tables), its `asyncpg`-gated
  export in `http/events/__init__.py`, the `postgres` tier in `tier.py` and the
  `event_bus_transport` class of the DB-artifact registry. No consumer
  deployment selected it: cyfuture and AegisMark run with `REDIS_URL`, and
  nothing sets `EVENT_BACKEND`. `EventFramework` picked it whenever
  `redis_url` was empty, so local runs without Redis used it.
- `src/dazzle/http/events/dev_memory.py` (373): `DevBusMemory`, the `memory`
  tier and the `EVENT_BACKEND` override. Tests use
  `tests/unit/helpers/event_bus.py::RecordingBus`.
- `src/dazzle/http/runtime/event_explorer.py` (552): the `/_dazzle/events/*`
  routes (`status`, `topics`, `topics/{topic}`, `event/{id}`, `consumers`,
  `outbox`, `dlq`, `POST dlq/{event_id}/replay`). They were mounted for every
  app with a database and **had no auth dependency** (the observability guide
  listed their gating as "None (all environments)"), so event payloads such as
  `auth.user.registered` (email, username, roles) were readable and DLQ replay
  was callable without signing in. Also gone: the
  `EventFramework` / `NullEventFramework` `get_outbox_stats` and
  `get_recent_outbox_entries` helpers only the explorer called.
- SSE live push (#1399 slice 1): `http/runtime/sse_stream.py` (339),
  `http/runtime/sse_wiring.py` (150), the `/_ops/sse/events` route,
  `DazzleBackendApp._wire_sse_live_push`, `WorkspaceSpec.live` and the
  parser's `live:` state, `WorkspaceContext.sse_url`, `DashboardGrid.sse_url`
  and `DashboardCard.sse_enabled` (the `hx-ext="sse" sse-connect` attributes
  and the `sse:entity.*` card triggers). No consumer DSL declares `live: on`.
  The browser never connected anyway: `htmx-ext-sse.js` is not vendored and
  the vendored htmx 4 core has no `EventSource` support, so cards refreshed
  only by poll. `live: <value>` still parses and warns `W_DECLARED_NOT_READ`.
- `http/channels/outbox.py` `OutboxRepository` and `ensure_outbox_table` (the
  channel delivery outbox, table `_dazzle_outbox`): never constructed (flense
  ship AI). `OutboxMessage`, `OutboxStatus` and `create_outbox_message` stay
  as the email adapters' message type.

**Schema.** Alembic revision `0025_flense_park_event_transport` drops
`_dazzle_outbox` (no writer existed, so it is empty on every consumer
database); `downgrade` recreates it with the removed DDL. The registry, the
framework schema orchestrator and `FRAMEWORK_SCHEMA_SNAPSHOT` follow (23 → 22
in-scope tables). **Operator sign-off for the drop: 2026-10-16.** The
`PostgresBus` transport tables (`_dazzle_events`, `_dazzle_consumer_offsets`,
`_dazzle_dlq` under the default prefix) were never migration-managed; a
database that booted without `REDIS_URL` may still hold them. They are not
dropped (no sign-off; Alembic autogenerate ignores the `_dazzle_` prefix).

**Kept (the consumer path).**

- `RedisBus` (`redis_bus.py`), `BaseEventBus`, `EventBus`, `EventEnvelope`,
  `NullBus` / `NullEventFramework`, `EventFramework`, `OutboxPublisher` with
  the `_dazzle_event_outbox` table, `IdempotentConsumer`, `EventsSubsystem`,
  `auth/events.py` (the `auth.user.*` envelopes), `EventBusProcessAdapter` and
  the in-process `EntityEventBus`.
- **The inbox stays.** The flense plan proposed dropping `inbox.py` and
  `_dazzle_event_inbox`. Tracing showed that `EventFramework._start_consumers`
  wraps every `register_handler` subscription in an `IdempotentConsumer`
  backed by `EventInbox`, and cyfuture registers `auth.user.registered` →
  `cyfuture-provision` (`services/auth_event_handlers.py`). Dropping it would
  break de-duplication on cyfuture's production path.
- Without `REDIS_URL` the bus is now the null tier (`EventTier.NULL`,
  `NullBus`): publishes are dropped and registered handlers never fire. Before
  ship AR the same setup ran the Postgres bus. Process execution without Redis
  is unchanged (`PostgresProcessAdapter`, not the bus).

**Reopen when (consumer force).**

1. A consumer declares `live: on` on a workspace and needs push rather than
   `refresh: every Ns`. Restore `sse_stream.py` / `sse_wiring.py`, the `live`
   IR field and the renderer attributes, **and vendor the htmx SSE extension**
   (or an HM controller using `EventSource`), keeping the `/_ops/sse/events`
   auth posture from flense ship AO (tenant from the session, never the query
   string).
2. A consumer must deploy without Redis (Postgres only) but needs event
   delivery (auth-event handlers, process events across workers). Restore
   `postgres_bus.py` and its tier; register its transport tables in the
   artifact registry (ADR-0047) and create them by migration (ADR-0017)
   instead of self-creation.
3. An operator needs HTTP event inspection. Restore the explorer behind an
   admin auth dependency, never unauthenticated.

**Out of scope until force (transport).** A durable delivery outbox for email
(the messaging DSL is DD-007), WebSockets, cross-tenant event inspection.

## Explicitly out of scope until force

- Kafka, EventBridge, schema registries, cross-tenant topic namespaces.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); events DSL and Kafka bus removed in flense ship F |
| 2026-10-13 | Flense ship O: *Already shipped* corrected — CRUD events never reached the outbox; unused `EventEmittingMixin` removed |
| 2026-10-16 | Flense ship AR: Postgres and in-memory buses, the `/_dazzle/events/*` explorer, SSE live push (`live:` now warns) and the channel `OutboxRepository` removed; `_dazzle_outbox` dropped by `0025_flense_park_event_transport`; the inbox kept (cyfuture's handler path) |
