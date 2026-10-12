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

No consumer app declares a `ledger`, `transaction` or `atomic` flow today.
Flense ship E (ADR-0057, Phase 3) retired `examples/fieldtest_hub`, the only
carrier of the ledger constructs; flense ship F removed the constructs
themselves, `atomic` flows with them. This DD keeps the DSL shape so a
money consumer restores it instead of re-deriving it.

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

`atomic` flows (ADR-0028/0029/0031/0032) were removed in the same ship and
restore from `2de583aa741ecc4dfad1f369f6c773fa12f99966`: the parser mixin
`dsl_parser_impl/atomic_flow.py`, IR `core/ir/atomic_flows.py`, linker
step-order and invariant-anchor derivation, `validate_atomic_flows`, the
transition `invoke <flow>(...)` effect, the executor / invariants / routes
(`POST /api/atomic/<flow>`), the `_dazzle_atomic_audit` table (dropped from consumer
databases by revision 0022 after operator sign-off on 2026-10-13) and `dazzle db audit-atomic`.
Atomic flows fed the proof surface, so restoring them also restores:

- the `AtomicFlowProjection` section of `rbac matrix` (JSON key
  `atomic_flows`, markdown "Atomic flows" table with invariants);
- the `rbac verify` permit-gate probes of `POST /api/atomic/<flow>`
  (`VerifiedFlow`, `compare_flow`, report key `flows`);
- `fixtures/transition_atomic` and the `flows.dsl` module of
  `fixtures/scope_runtime` with their Postgres tests.

Removing them left `rbac prove` output for every consumer byte-identical and
`rbac matrix` identical except that its always-empty `atomic_flows` key is
gone (the `rbac verify` report loses its always-empty `flows` key).

## Reopen when (consumer force)

1. **Named consumer** — pennydreadful royalty calculation needs a royalty
   ledger (author statements posted per sale), **or** cyfuture's
   client-money discipline needs a client-money ledger (client funds held
   apart from office money, CASS-style reconciliation), declared in that
   app's DSL. A consumer needing several entities written in one
   scope-checked transaction forces `atomic` on its own.
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
| 2026-10-12 | Constructs, `atomic` flows and TigerBeetle extra removed in flense ship F; restore SHA `2de583aa7` |
