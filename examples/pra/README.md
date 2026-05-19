# Performance Reference App (PRA)

**Dazzle Event-First Architecture - Stress Reference**

This is **NOT** a tutorial, production example, or "hello world".

It is a **stress reference** whose purpose is to surface:
- Latency contributors
- Throughput ceilings
- Tail-latency behaviour
- Backpressure propagation
- Replay and recovery costs
- Semantic-driven performance pathologies

## Domain Overview

The PRA uses a minimal transactional domain as a carrier for stress patterns:

| Entity | Purpose |
|--------|---------|
| Actor | Issues INTENT records |
| Account | Holds balance (derived from ledger) |
| Order | Irreversible once placed |
| PaymentAttempt | May succeed or fail |
| LedgerEntry | Append-only financial facts |

## Stream Topology

### INTENT Streams (requests, may be rejected)
- `orders_intent` - Order placement requests
- `payments_intent` - Payment attempt requests

### FACT Streams (irreversible truths)
- `orders_fact` - Order placed/rejected/fulfilled
- `payments_fact` - Payment succeeded/failed/timed out
- `ledger_fact` - Append-only financial ledger

### OBSERVATION Streams (may be duplicated, late, out-of-order)
- `gateway_observation` - External payment gateway webhooks
- `http_observation` - HTTP request tracing

### DERIVATION Streams (fully rebuildable)
- `account_balance_derived` - Computed from ledger_fact
- `daily_revenue_derived` - Aggregated from orders_fact

## Stress Patterns Exercised

1. **Hot Partition Skew** - Small % of accounts generate large % of traffic
2. **Fan-Out** - One FACT triggers multiple projections
3. **Rejection Paths** - Non-trivial % of INTENTs rejected
4. **Idempotent Replays** - Duplicate INTENTs must not create duplicate FACTs
5. **Schema Evolution** - V1 + V2 schemas processed concurrently
6. **Backpressure Propagation** - Slow consumer bounded backlog
7. **DLQ Activation** - Invalid records route to DLQ
8. **Full Replay** - DERIVATION streams rebuildable from scratch

## HLESS Compliance

This project uses **HLESS strict mode**. The word "event" is forbidden.

All streams are classified into exactly one RecordKind:
- `INTENT` - requests that may succeed or fail
- `FACT` - irreversible domain truths
- `OBSERVATION` - measurements that may be imprecise
- `DERIVATION` - computed values with lineage

## Running

```bash
cd examples/pra
dazzle validate    # Validate DSL
dazzle dnr serve   # Run the app
```

## Metrics (to be implemented)

The PRA will produce:
- p50/p95/p99 latency (INTENT → derived view update)
- Sustained throughput (INTENTs/sec, FACTs/sec)
- Consumer lag per stream
- Rebuild time for DERIVATION streams
- Rejection rate, DLQ rate, retry rate

## Reference

See: `dev_docs/architecture/event_first/performance_reference_app.md`
