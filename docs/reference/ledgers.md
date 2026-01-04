# Ledgers and Transactions

TigerBeetle integration for double-entry accounting (v0.24.0).

## Overview

DAZZLE integrates with [TigerBeetle](https://tigerbeetle.com/), a high-performance distributed financial database, to provide ACID-compliant double-entry accounting. The DSL provides two constructs:

- **`ledger`**: Defines account templates for TigerBeetle accounts
- **`transaction`**: Defines multi-leg financial transactions

## Ledger Construct

A ledger defines a template for TigerBeetle accounts. Each entity instance linked to a ledger gets its own account.

### Basic Syntax

```dsl
ledger CustomerWallet "Customer Wallet":
  intent: "Track customer prepaid balances"
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `account_code` | `int` (1-65535) | TigerBeetle account code for categorization |
| `ledger_id` | `int` (1-65535) | TigerBeetle ledger ID (namespace) |
| `account_type` | `enum` | Double-entry account type |
| `currency` | `string` | ISO 4217 currency code (e.g., GBP, USD, EUR) |

### Account Types

| Type | Normal Balance | Description |
|------|----------------|-------------|
| `asset` | Debit | Resources owned (cash, inventory, receivables) |
| `liability` | Credit | Obligations owed (payables, loans) |
| `equity` | Credit | Owner's stake in the business |
| `revenue` | Credit | Income from operations |
| `expense` | Debit | Costs incurred |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent` | `string` | Business purpose documentation |
| `flags` | `list[flag]` | TigerBeetle account constraints |
| `sync_to` | `Entity.field` | PostgreSQL cache field for balance sync |
| `tenant_scoped` | `bool` | Per-tenant account isolation (default: true) |
| `metadata_mapping` | `block` | Map entity fields to TigerBeetle user_data |

### Account Flags

| Flag | Description |
|------|-------------|
| `debits_must_not_exceed_credits` | Prevent overdrafts (asset accounts) |
| `credits_must_not_exceed_debits` | Prevent negative balances (liability accounts) |
| `linked` | Account is linked to another for atomic creation |
| `history` | Maintain full transaction history |

### Balance Sync

Sync TigerBeetle account balances to PostgreSQL for fast queries:

```dsl
ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  sync_to: Customer.balance_cache
```

Sync triggers:
- `after_transfer` (default): Sync immediately after each transfer
- `scheduled "*/5 * * * *"`: Sync on cron schedule
- `on_demand`: Manual sync only

## Transaction Construct

A transaction groups multiple transfers that must succeed or fail atomically.

### Basic Syntax

```dsl
transaction RecordPayment "Record Subscription Payment":
  intent: "Charge customer for monthly subscription with VAT"
  execution: async
  priority: high

  transfer revenue_portion:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount * 0.80
    code: 1
    flags: linked

  transfer vat_portion:
    debit: CustomerWallet
    credit: VATLiability
    amount: payment.amount * 0.20
    code: 2

  idempotency_key: payment.id

  validation:
    - payment.amount > 0
    - payment.status == "authorized"
```

### Transaction Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent` | `string` | Business purpose documentation |
| `execution` | `sync\|async` | Execution mode (default: sync) |
| `priority` | `enum` | Queue priority for async execution |
| `timeout` | `int` | Timeout in milliseconds (default: 5000) |
| `idempotency_key` | `expression` | **Required** - Key for deduplication |
| `validation` | `block` | Precondition rules |

### Execution Modes

| Mode | Description |
|------|-------------|
| `sync` | Execute immediately in the request |
| `async` | Queue for background processing via Celery |

### Priority Levels

For async execution, priority determines queue routing:

| Priority | Queue | Use Case |
|----------|-------|----------|
| `critical` | `celery.ledger.critical` | Reversals, corrections |
| `high` | `celery.ledger.high` | Customer-initiated transfers |
| `normal` | `celery.ledger.normal` | Standard operations |
| `low` | `celery.ledger.low` | Batch operations, reports |

### Transfer Block

Each transfer moves value from a debit account to a credit account:

```dsl
transfer revenue_portion:
  debit: CustomerWallet
  credit: Revenue
  amount: payment.amount * 0.80
  code: 1
  flags: linked
```

| Field | Type | Description |
|-------|------|-------------|
| `debit` | `ledger_name` | Source account (debited) |
| `credit` | `ledger_name` | Destination account (credited) |
| `amount` | `expression` | Amount to transfer |
| `code` | `int` (1-65535) | Transfer code for categorization |
| `flags` | `list[flag]` | Transfer behavior flags |
| `pending_id` | `string` | Reference for two-phase transfers |
| `user_data` | `block` | Custom metadata |

### Transfer Flags

| Flag | Description |
|------|-------------|
| `linked` | Part of atomic chain (all succeed or fail) |
| `pending` | Two-phase: create pending transfer |
| `post_pending` | Complete a pending transfer |
| `void_pending` | Cancel a pending transfer |
| `balancing` | Auto-calculate amount to balance |

### Multi-Leg Transactions

For atomic multi-leg transactions, use the `linked` flag on all but the last transfer:

```dsl
transaction ThreeWaySplit:
  transfer portion_a:
    debit: Source
    credit: DestA
    amount: total * 0.50
    code: 1
    flags: linked    # First leg - linked

  transfer portion_b:
    debit: Source
    credit: DestB
    amount: total * 0.30
    code: 2
    flags: linked    # Second leg - linked

  transfer portion_c:
    debit: Source
    credit: DestC
    amount: total * 0.20
    code: 3
    # Last leg - no linked flag
```

### Amount Expressions

Amounts support field references and arithmetic:

```dsl
amount: 100                      # Literal
amount: payment.amount           # Field reference
amount: payment.amount * 0.80    # Arithmetic
amount: line_item.price + tax    # Addition
```

### Validation Rules

Preconditions that must be true before executing:

```dsl
validation:
  - payment.amount > 0
  - payment.status == "authorized"
  - customer.active == true
```

### Idempotency Key

TigerBeetle uses idempotency keys to prevent duplicate transfers:

```dsl
idempotency_key: payment.id              # Simple field
idempotency_key: order.id                # Entity ID
```

## Complete Example

```dsl
module billing.ledger
app billing "Billing System"

entity Customer "Customer":
  id: uuid pk
  email: str(255) required
  balance_cache: decimal(12,2) = 0
  active: bool = true

# Define ledgers

ledger CustomerWallet "Customer Wallet":
  intent: "Track customer prepaid balances"
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache

ledger Revenue "Revenue Account":
  intent: "Track subscription revenue"
  account_code: 2001
  ledger_id: 1
  account_type: revenue
  currency: GBP

ledger VATLiability "VAT Liability":
  intent: "Track VAT collected for HMRC"
  account_code: 3001
  ledger_id: 1
  account_type: liability
  currency: GBP

# Define transactions

transaction RecordPayment "Record Subscription Payment":
  intent: "Charge customer for monthly subscription with VAT"
  execution: async
  priority: high

  transfer revenue_portion:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount * 0.80
    code: 1
    flags: linked

  transfer vat_portion:
    debit: CustomerWallet
    credit: VATLiability
    amount: payment.amount * 0.20
    code: 2

  idempotency_key: payment.id

  validation:
    - payment.amount > 0

transaction RefundPayment "Process Refund":
  intent: "Reverse a payment back to customer wallet"
  execution: sync
  priority: critical

  transfer refund:
    debit: Revenue
    credit: CustomerWallet
    amount: refund.amount
    code: 10

  idempotency_key: refund.id
```

## Validation Rules

The linter enforces:

1. **Unique ledger names** - No duplicate ledger definitions
2. **Unique account codes per ledger_id** - Codes must be unique within a namespace
3. **Valid currency format** - Must be 3-letter ISO 4217 code
4. **Sync target exists** - Entity and field must exist
5. **Transaction idempotency_key required** - For TigerBeetle deduplication
6. **Transfer ledger references exist** - Debit/credit ledgers must be defined
7. **Same ledger_id for transfers** - TigerBeetle requirement
8. **Currency matching** - Debit and credit ledgers must use same currency
9. **Multi-leg linked flags** - Warning if linked flag missing

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Data Flow                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TigerBeetle                 Event Bus              PostgreSQL   │
│  (Source of Truth)           (Transit)              (Queryable)  │
│                                                                  │
│  ┌──────────────┐     ┌──────────────────┐    ┌──────────────┐  │
│  │ Transfers    │────▶│ TransferComplete │───▶│ balance_cache│  │
│  │ (immutable)  │     │ Event            │    │ (synced)     │  │
│  └──────────────┘     └──────────────────┘    └──────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## See Also

- [TigerBeetle Documentation](https://docs.tigerbeetle.com/)
- [Celery Event Architecture](/dev_docs/celery-event-architecture.md)
- [Founder-First Principles](/dev_docs/founder-first-architecture.md)
