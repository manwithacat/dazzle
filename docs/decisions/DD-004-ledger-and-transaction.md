# DD-004: `ledger` / `transaction` / `atomic` — parked until a money consumer

```yaml
id: DD-004
status: PARKED
issues: []
adrs: [0057, 0003]
decided: 2026-10-12
decided_at_sha: 48cef12f0
parent: flense-programme
```

## One-line intent

No consumer app declares a `ledger` or `transaction` today. Flense ship E
(ADR-0057, Phase 3) retires `examples/fieldtest_hub`, the only carrier of
these constructs; flense ship F removes the constructs themselves. This DD
keeps the DSL shape so a money consumer restores it instead of re-deriving it.

## Plan (what we already concluded)

Restore the `ledger`, `transaction` and `atomic` constructs (grammar, IR,
parser mixin, validation, TigerBeetle-backed execution path) and
`examples/fieldtest_hub` from the pre-removal commit
`48cef12f06252c098a3f77bf5f6e92da3c6cc8b8` (the commit this DD was parked
at), then trim the restored example to the shape the forcing consumer needs.

The DSL surface that existed, verbatim from
`examples/fieldtest_hub/dsl/app.dsl` at that commit:

```dsl
ledger DeviceCost "Device Cost Account":
  intent: "Accrue repair and replacement expenses against the fleet of field devices"
  account_code: 5100
  ledger_id: 1
  account_type: expense
  currency: GBP

ledger OperationsBudget "Operations Budget":
  intent: "Draw down the field-test programme's allocated operations budget"
  account_code: 1100
  ledger_id: 1
  account_type: asset
  currency: GBP

# =============================================================================
# TRANSACTION — record a repair cost against the budget
# =============================================================================

transaction RecordRepair "Record Repair Cost":
  intent: "Charge a device repair to the cost account and draw it from operations budget"
  transfer repair_expense:
    debit: DeviceCost
    credit: OperationsBudget
    amount: event.amount
    code: 1

  idempotency_key: event.id
```

Design points to keep:

- Double-entry only: every `transfer` names one `debit` and one `credit`
  ledger; validation rejects a movement without an equal and opposite entry.
- `idempotency_key` is mandatory on a transaction (replay safety).
- Money stays integer minor units with a declared `currency` per ledger.
- Counter-prior: do not model balances as mutable float columns on an
  ordinary entity, and do not let app code post movements outside a declared
  `transaction`.

## Reopen when (consumer force)

1. **Named consumer** — pennydreadful royalty calculation needs a royalty
   ledger, **or** cyfuture client-money discipline needs a client-money
   ledger, declared in that app's DSL.
2. **Evidence of host workaround** — a consumer computing balances in
   `app/` code or a hand-rolled ledger entity.
3. **Acceptance that unblocks** — the consumer's ledger and transaction
   validate and post balanced transfers with idempotency in its CI.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- The constructs, their IR and the TigerBeetle-backed execution engine
  (alpha, never independently verified) exist in history at the commit above.

## Explicitly out of scope until force

- Multi-currency conversion, FX ledgers, reporting/statement generation.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); `examples/fieldtest_hub` retired in flense ship E |
