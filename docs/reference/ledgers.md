# Ledgers & Transactions

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Ledgers and transactions provide TigerBeetle-backed double-entry accounting. Ledger accounts define account codes, types, and constraints, while transactions declare transfers between accounts with linked operations and idempotency support.

---

## Ledger

TigerBeetle-backed double-entry ledger account. Defines account codes, types, and constraints for financial transactions. Supports sync_to for caching balances in entity fields.

### Syntax

```dsl
ledger <LedgerName> "<Title>":
  account_code: <int>
  ledger_id: <int>
  account_type: <asset|liability|equity|revenue|expense>
  currency: <ISO_code>
  [flags: <debits_must_not_exceed_credits|credits_must_not_exceed_debits>]
  [sync_to: <Entity.field>]
```

### Example

```dsl
ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache
```

**Related:** [Transaction](ledgers.md#transaction), [Entity](entities.md#entity)

---

## Transaction

TigerBeetle-backed financial transaction with one or more transfers between ledger accounts. Supports linked transfers, idempotency, and async execution.

### Syntax

```dsl
transaction <TransactionName> "<Title>":
  execution: <sync|async>
  [priority: <normal|high>]

  transfer <name>:
    debit: <LedgerName>
    credit: <LedgerName>
    amount: <expression>
    code: <int>
    [flags: linked]

  [idempotency_key: <expression>]
```

### Example

```dsl
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

**Related:** [Ledger](ledgers.md#ledger)

---
