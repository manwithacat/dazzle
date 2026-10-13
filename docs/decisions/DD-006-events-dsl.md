# DD-006: Events DSL (`hless`, `stream`, `event_model`, `subscribe`, `projection`, `ingest`) and the Kafka bus — parked until a consumer needs an ordered or replayable stream

```yaml
id: DD-006
status: PARKED
issues: [1069, 1189, 1676]
adrs: [0057, 0003]
decided: 2026-10-12
decided_at_sha: 2de583aa741ecc4dfad1f369f6c773fa12f99966
parent: flense-programme
```

## One-line intent

No consumer app declares an event construct. Flense ship F (ADR-0057) removes
the event *vocabulary* of the DSL and the Kafka bus adapter, and keeps the
event *core* every consumer already runs: `EventsSubsystem`, the
transactional outbox and publisher, the inbox, and the Postgres, Redis and
in-memory buses. (Flense ship O corrected this list: `EventEmittingMixin`
was never mixed into a CRUD service and was removed — see *Already shipped*.)

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
  groups) and `/_dazzle/events/*` inspection remains (the `dazzle events` /
  `dlq` / `outbox` CLI groups were retired in flense ship J — no consumer ran
  them). What actually travels on it today:
  - **CRUD lifecycle events do not use the bus or the outbox.** `CRUDService`
    lifecycle callbacks feed the in-process `EntityEventBus`
    (`SystemRoutesSubsystem._wire_entity_events_to_bus`), whose handlers are
    integration mappings, LLM triggers, SLA timers and app handlers (cyfuture
    registers `add_sync_handler` for lifecycle and HMRC work). For workspaces
    with `live: on`, `sse_wiring` also publishes a non-transactional nudge
    envelope straight to the bus for the SSE stream.
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

## Explicitly out of scope until force

- Kafka, EventBridge, schema registries, cross-tenant topic namespaces.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); events DSL and Kafka bus removed in flense ship F |
| 2026-10-13 | Flense ship O: *Already shipped* corrected — CRUD events never reached the outbox; unused `EventEmittingMixin` removed |
