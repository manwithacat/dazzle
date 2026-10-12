# Parser Reference App (PRA)

A **framework-validation fixture**, not a tutorial or production example.

`fixtures/pra` is the parser-conformance corpus: a kitchen-sink of DSL forms
(entities, relationships, computed fields, state machines, access control,
surfaces, workspaces, processes, services, LLM declarations, personas and edge
cases) that the parser and linker tests exercise. Its validate baseline lives
in `tests/unit/fixtures/dazzle_validate_baseline.json`; the deliberate errors
are route collisions kept for parser coverage.

The corpus used to carry an HLESS stream topology (INTENT / FACT /
OBSERVATION / DERIVATION streams) plus `events.dsl` and `messaging.dsl`
modules. Those went with the event and messaging DSL in flense ship F
(ADR-0057); their design is parked in
`docs/decisions/DD-006-events-dsl.md` and `docs/decisions/DD-007-messaging-dsl.md`.

## Domain carriers

| Entity | Purpose |
|--------|---------|
| Actor | Issues requests |
| Account | Holds a balance |
| TradeOrder | Irreversible once placed |
| PaymentAttempt | May succeed or fail |
| LedgerEntry | Append-only financial entries |

## Running

```bash
dazzle validate -p fixtures/pra
```
