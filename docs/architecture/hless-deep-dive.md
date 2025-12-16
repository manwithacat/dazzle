# HLESS Deep Dive

**High-Level Event Semantics Specification**

This document explains why HLESS exists, the problems it solves, and its philosophical foundations.

## The Problem

Event-driven architectures fail in three predictable ways:

1. **Semantic drift** - Over time, "events" accumulate meanings that weren't intended
2. **Vocabulary lock-in** - Teams inherit Kafka's terminology and conflate abstraction layers
3. **Human imprecision** - Natural language descriptions become ambiguous record definitions

HLESS addresses all three by introducing a semantic layer between human intent and implementation.

---

## Why "Event" Is a Forbidden Word

The word "event" is banned in HLESS strict mode. This is deliberate.

### The Ambiguity Problem

When someone says "the OrderCreated event", they might mean:

- A **request** to create an order (which might be rejected)
- A **fact** that an order now exists (irreversible)
- An **observation** that something happened in an external system
- A **derivation** computed from other data

These are fundamentally different things with different semantics, ordering guarantees, and replay behaviours. Calling them all "events" creates bugs that manifest years later when someone replays the log and discovers their assumptions were wrong.

### Kafka's Vocabulary Is Not Neutral

Kafka documentation uses terms like "event", "message", "record", and "topic" interchangeably. This vocabulary has leaked into how teams think about event-driven systems.

But Kafka is an **implementation**. Its vocabulary describes:
- How data is stored (partitions, offsets)
- How data is transmitted (producers, consumers)
- How data is organised (topics, consumer groups)

None of this tells you what the data **means**.

HLESS exists precisely because implementation vocabulary ("Kafka topic", "event stream") tells you nothing about:
- Whether records represent completed facts or pending requests
- Whether replay should trigger side effects
- Whether ordering matters and at what scope

---

## The Four Record Kinds

HLESS requires every record to be classified as exactly one of four kinds. This is not optional.

### INTENT

A fact that someone **requested** or **attempted** something.

```
OrderPlacementRequested    (valid - describes attempt)
PlaceOrder                 (invalid - imperative, not intent)
```

**Key property**: Does NOT imply success. May lead to acceptance or rejection.

### FACT

A fact about the domain that is **permanently true**.

```
OrderPlaced                (valid - irreversible truth)
OrderPending               (invalid - temporary state, not fact)
```

**Key property**: Cannot be retracted. Must remain true forever.

### OBSERVATION

A fact that something was **observed, measured, or reported**.

```
TemperatureMeasured        (valid - observation was recorded)
TemperatureIs25Degrees     (invalid - asserts correctness)
```

**Key property**: Truth is "this was observed", not "this is correct". May be duplicated, late, or out of order.

### DERIVATION

A fact that a value was **computed** from other records.

```
DailyRevenueCalculated     (valid - computed from source records)
```

**Key property**: Always rebuildable from sources. Must not introduce new domain truth.

---

## Why This Classification Matters

### Replay Safety

When you replay a log, what happens?

- **INTENT** records: Should trigger processing again (they're requests)
- **FACT** records: Should NOT trigger side effects (the fact already happened)
- **OBSERVATION** records: May duplicate, requires idempotency handling
- **DERIVATION** records: Can be deleted and rebuilt from sources

Without explicit classification, replay is dangerous.

### Ordering Guarantees

HLESS requires explicit ordering scope:

```dsl
stream orders:
  record_kind: FACT
  partition_key: order_id
  ordering_scope: per_order
```

This declares that ordering is guaranteed **only** within a single order. Cross-order invariants must not assume ordering.

If you write an invariant that assumes global ordering, HLESS will reject it.

### Idempotency

Each record kind has default idempotency strategies:

| Kind | Default Strategy |
|------|------------------|
| INTENT | Deterministic ID from content |
| FACT | Hash of stream + key + payload |
| OBSERVATION | Time-windowed deduplication |
| DERIVATION | Hash of source records + function |

These can be overridden, but they must be explicit.

---

## The Human-LLM Translation Problem

HLESS was designed for a specific workflow:

1. A human says something imprecise: "when an order is placed"
2. An LLM translates this into a formal specification
3. The specification is validated against semantic rules
4. Only then is code or infrastructure generated

The risk is that an LLM will **guess** what the human meant. HLESS prevents this by:

1. **Banning ambiguous terminology** - Forces explicit RecordKind
2. **Requiring structural declarations** - StreamSpec must be complete
3. **Enforcing semantic rules** - Violations block generation

### Example: Imprecise Human Input

**Human says**: "I need an event for when orders are created"

**Without HLESS**, an LLM might generate:
```yaml
topic: order-events
schema: OrderCreated
```

This tells us nothing about semantics. Is it a request? A fact? Can it be replayed?

**With HLESS**, the LLM must first clarify:

- Is this describing a **request** to create an order? → INTENT
- Is this describing that an order **was** created? → FACT
- Is this an **observation** from an external system? → OBSERVATION

Then it generates:
```yaml
name: orders.fact.v1
record_kind: FACT
schemas:
  - name: OrderPlaced
    version: v1
partition_key: order_id
ordering_scope: per_order
time_semantics:
  t_event_field: placed_at
idempotency:
  strategy_type: deterministic_id
  field: record_id
invariants:
  - "OrderPlaced is irreversible"
  - "order_id is unique within this stream"
```

The specification is **complete** before any code is written.

---

## Technology Independence

HLESS deliberately avoids infrastructure-specific terminology.

### What HLESS Does NOT Define

- How records are stored (Kafka, Pulsar, Redpanda, files)
- How records are partitioned (implementation detail)
- How consumers are grouped (implementation detail)
- Wire format (Avro, Protobuf, JSON)

### What HLESS Does Define

- What kind of truth each record represents
- What ordering guarantees exist and at what scope
- How duplicates should be detected
- What the contract is between intent and outcome

This separation means you can:
1. Start with an in-memory log for development
2. Move to Kafka for production
3. Switch to Pulsar without changing semantics

The StreamSpec remains the same. Only the mapping changes.

---

## The Semantic Validation Rules

HLESS enforces six core rules. These are not advisory—violations block processing.

### Rule 1: FACT Streams Must Not Contain Imperatives

```
OrderPlaced         ✓ (describes completed truth)
CreateOrder         ✗ (imperative command)
PlaceOrder          ✗ (imperative command)
```

### Rule 2: INTENT Streams Must Not Imply Success

```
OrderPlacementRequested    ✓ (describes attempt)
OrderPlaced                ✗ (implies completion)
OrderCreated               ✗ (implies success)
```

### Rule 3: DERIVATION Streams Must Reference Sources

Every DERIVATION must declare what it derives from:
```yaml
lineage:
  source_streams: [order_facts, payment_facts]
  derivation_type: aggregate
  rebuild_strategy: full_replay
```

Without this, the derivation cannot be rebuilt.

### Rule 4: OBSERVATION Streams Must Not Assert Correctness

```
"TemperatureWasRecorded"              ✓ (observation)
"TemperatureIsAccurate"               ✗ (asserts truth)
"ValueIsGuaranteedCorrect"            ✗ (asserts truth)
```

Observations may be late, duplicated, or wrong. The only truth is that they were observed.

### Rule 5: Ordering Invariants Must Match Partition Key

If your invariant says "OrderShipped always follows OrderPlaced", this only holds within a single partition.

HLESS requires:
```yaml
partition_key: order_id
ordering_scope: per_order
invariants:
  - "Within each order: OrderShipped follows OrderPlaced"
```

Cross-partition ordering invariants are rejected unless you explicitly declare `cross_partition: true`.

### Rule 6: FACT Records Must Be True Forever

If you write a FACT, it cannot be retracted. This is fundamental to event-first architecture.

```
OrderPlaced          ✓ (permanent truth)
OrderPending         ✗ (temporary state)
ProvisionalInvoice   ✗ (may change)
```

---

## The Three Time Axes

HLESS requires distinguishing between three timestamps:

| Timestamp | Meaning |
|-----------|---------|
| `t_event` | When the thing happened in the real world |
| `t_log` | When the record was appended to the log |
| `t_process` | When the record was processed (derivations only) |

**Why this matters**:

- A sensor reading (`t_event: 14:00`) might be logged later (`t_log: 14:05`) due to network delay
- Replaying the log doesn't change `t_event` but does change `t_process`
- Windowed aggregations must know which time axis to use

HLESS bans the unqualified word "time" to prevent confusion.

---

## The Intent-Outcome Contract

INTENT streams must declare their expected outcomes:

```yaml
record_kind: INTENT
expected_outcomes:
  success:
    emits: [OrderPlaced]
    target_stream: orders.fact.v1
  failure:
    emits: [OrderPlacementRejected]
    target_stream: orders.fact.v1
```

This establishes the contract:
- "If you send OrderPlacementRequested, you will eventually get OrderPlaced or OrderPlacementRejected"
- The outcomes are FACT records (permanent truth)
- They go to a specific stream with known semantics

---

## Why Idempotency Is Mandatory

Every stream must declare how duplicates are detected:

```yaml
idempotency:
  strategy_type: deterministic_id
  field: record_id
  derivation: "hash(stream, natural_key, t_event, payload)"
```

This is not optional because:
1. Networks lose messages and retry
2. Producers crash and restart
3. Consumers fail and replay from checkpoints

Without explicit idempotency, you get duplicate processing or data loss.

---

## HLESS Modes

Three enforcement modes exist:

| Mode | Behaviour |
|------|-----------|
| `strict` | Violations are errors. Default for new projects. |
| `warn` | Violations are warnings. For migration. |
| `off` | No enforcement. Strongly discouraged. |

Strict mode is recommended. It prevents problems before they manifest.

---

## Summary

HLESS exists because:

1. **Human language is imprecise** - "event" means different things to different people
2. **Kafka's vocabulary is not semantic** - It describes implementation, not meaning
3. **Semantic errors compound over time** - Wrong assumptions at design time become production incidents years later

By requiring explicit classification (INTENT, FACT, OBSERVATION, DERIVATION), explicit time semantics, and explicit idempotency, HLESS ensures that event-first systems remain understandable, replayable, and safe.

---

## See Also

- [Event Semantics](event-semantics.md) - Quick reference for record kinds
- [Messaging Reference](../reference/messaging.md) - DSL syntax for channels
- [Architecture Overview](overview.md) - System architecture