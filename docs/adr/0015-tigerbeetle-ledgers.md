# ADR-0015: TigerBeetle for Double-Entry Ledgers

**Status:** Accepted
**Date:** 2026-02-15

## Context

Applications handling financial transactions (payments, wallets, credits, revenue tracking) need ACID-compliant double-entry accounting. Traditional approaches use PostgreSQL tables with application-level transaction logic, which is error-prone and slow at scale.

TigerBeetle is a purpose-built financial transactions database designed for exactly this: double-entry bookkeeping with ACID guarantees, sub-millisecond latency, and built-in balance constraints.

## Decision

Use TigerBeetle as the ledger engine for applications that declare `ledger` and `transaction` DSL constructs. The DSL provides a declarative interface; the runtime connects to TigerBeetle via its client library (optional dependency).

### DSL Syntax

```dsl
ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache

transaction RecordPayment "Record Payment":
  execution: async
  priority: high

  transfer revenue:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1
    flags: linked

  idempotency_key: payment.id
```

**Account types**: `asset`, `liability`, `equity`, `revenue`, `expense`

### Runtime

- TigerBeetle client is an optional dependency (`pip install dazzle-dsl[tigerbeetle]`)
- Lazy import via `pra/tigerbeetle_client.py` — no import cost if not used
- `sync_to` field enables one-way cache sync from TigerBeetle balance to a PostgreSQL entity field

## Consequences

### Positive

- Sub-millisecond financial transaction processing
- Built-in double-entry invariants (debits = credits)
- Balance constraints enforced at the database level (`debits_must_not_exceed_credits`)
- Idempotency keys prevent duplicate transactions

### Negative

- Additional infrastructure dependency for financial apps
- TigerBeetle requires its own deployment and monitoring
- Limited query capabilities compared to PostgreSQL (designed for writes, not ad-hoc queries)

### Neutral

- Apps without `ledger` constructs never touch TigerBeetle
- Balance caches in PostgreSQL provide queryable read path

## Alternatives Considered

### 1. PostgreSQL-Only Double-Entry

Implement ledgers as PostgreSQL tables with triggers and constraints.

**Rejected:** Application-level double-entry is error-prone. PostgreSQL lacks built-in balance constraint enforcement. Performance degrades under high transaction volumes.

### 2. Stripe/Payment Provider Only

Delegate all financial logic to payment providers.

**Rejected:** Not all ledger use cases are payments (credits, loyalty points, internal transfers). Provider lock-in. Latency for internal operations.
