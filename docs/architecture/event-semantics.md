# Event-First Architecture

Dazzle supports event-first patterns through the High-Level Event Semantics Specification (HLESS).

!!! info "Want the full story?"
    This page is a quick reference. For the philosophy, rationale, and detailed rules, see the [HLESS Deep Dive](hless-deep-dive.md).

## Overview

HLESS defines a **technology-agnostic semantic layer** that:

- Allows humans to specify events **casually and quickly**
- Enables LLM agents to **safely translate** specifications
- Produces **formal, machine-validated event definitions**
- Prevents **semantic drift** over time

## Core Principles

### 1. Append-Only Truth

All records written to an event log are **immutable facts**. They may describe:

- Outcomes
- Observations
- Facts about intent

They must not describe something that can later be "undone".

### 2. Logs Are Primary, State Is Derived

Current state, views, projections, and caches are **derived artifacts**. They may be deleted and rebuilt at any time from logs.

### 3. Ordering Is Explicit and Local

Total ordering exists **only within an explicitly declared ordering scope**. Any invariant that relies on order must declare the scope it depends on.

### 4. Semantics Must Be Declared, Not Inferred

No log, stream, or topic may exist without an explicit semantic contract.

## Record Kinds

Every record must be classified as exactly one of these:

### INTENT

A fact that an actor *requested* or *attempted* an action.

```dsl
# Valid
event OrderPlacementRequested
event UserRequestedPasswordReset

# Invalid (imperative, not intent)
event PlaceOrder
event CreateInvoice
```

### FACT

A fact about the domain that is now **permanently true**.

```dsl
# Valid
event OrderPlaced
event InvoiceIssued
event OrderPlacementRejected

# Invalid (uncertain/retractable)
event OrderPending
event ProvisionalInvoice
```

### OBSERVATION

A fact that something was observed, measured, or reported.

```dsl
# Valid
event TemperatureRecorded
event UserActivityLogged
event HealthCheckCompleted
```

### DERIVATION

A computed or derived fact based on other records.

```dsl
# Valid
event DailyRevenueCalculated
event RiskScoreUpdated
```

## Stream Definitions

Streams are declared with explicit semantics:

```dsl
stream orders:
  record_kind: FACT
  partition_key: order_id
  retention: 90d

stream order_requests:
  record_kind: INTENT
  partition_key: user_id
  retention: 7d
```

## Time Semantics

Every record has three timestamps:

| Timestamp | Meaning |
|-----------|---------|
| `t_event` | When the event occurred in the real world |
| `t_log` | When the event was written to the log |
| `t_process` | When a consumer processed the event |

## See Also

- [HLESS Deep Dive](hless-deep-dive.md) - Philosophy, rationale, and detailed rules
- [Architecture Overview](overview.md)
- [Messaging Reference](../reference/messaging.md)
