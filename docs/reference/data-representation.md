# Data representation: defaults and escape hatches

**Related:** [#1617](https://github.com/manwithacat/dazzle/issues/1617) (RFC),
[#1240](https://github.com/manwithacat/dazzle/issues/1240) (poly association),
`subtype_of:` / ADR-0026 (TPT inheritance).

## Default (opinionated)

Dazzle leads with **relational, explicit shapes**:

| Pattern | DSL / runtime |
|---------|----------------|
| Foreign keys | `ref Entity` / `belongs_to` |
| True ISA inheritance | `subtype_of:` (table-per-type) |
| List→context hop | `open: Entity via field` or `first_non_null(...)` |
| Flexible JSON blobs | `json` field type (schema-light) |

Prefer separate entities, state machines, and nullable FKs with CHECK-style
discipline before inventing polymorphism.

## Escape hatch ladder

When purity collides with multi-tenant SaaS velocity, use **documented** hatches
(not host dual-lock folklore):

| Hatch | When | Status |
|-------|------|--------|
| **Sparse exclusive FKs** | 2–4 alternative parents (`company` \| `sole_trader`) | Works today + `open: first_non_null(...)` + integrity (#1617 Phase 1) |
| **`subtype_of:` TPT** | True ISA with substantial per-kind columns | Shipped — prefer over STI for core domain |
| **`json` / JSONB payload** | Tenant/feature-variable bags; keep core columns normalized | Field type exists; GIN/index conventions evolving |
| **Typed polymorphic association** | Comment/attachment/audit → many parents | Designed in #1240; implement when a consumer forces |
| **STI (single table + type)** | Related subtypes with sparse columns | Prefer TPT; lint when overused |
| **EAV** | Extreme custom fields | Prefer JSONB projections, not classic EAV joins |
| **Core vs extension schema** | Dual-lock host owns extensions | Intentional boundary; framework owns core |

### Exclusive FKs integrity (#1617 Phase 1)

Author the at-least-one-anchor invariant on the exclusive set:

```dsl
entity Subscription "Subscription":
  id: uuid pk
  company: ref Company
  sole_trader: ref SoleTrader
  partnership: ref Partnership
  invariant: company != null or sole_trader != null or partnership != null
```

List drill:

```dsl
open: first_non_null(company, sole_trader, partnership)
```

`dazzle db verify` then reports two integrity classes for that invariant shape:

| Status | Meaning |
|--------|---------|
| `unanchored` | Every exclusive FK is NULL (row has no parent) |
| `exclusive_conflict` | Two or more exclusive FKs are non-null (row claims multiple parents) |

App write-time still enforces invariants on framework writes; `verify` catches
out-of-band SQL / legacy data. Hard DB `CHECK` codegen remains optional later.

## Display is not storage

Locale and money rules ([#1597](https://github.com/manwithacat/dazzle/issues/1597)):

- Storage: UTC datetimes, calendar **date** fields, money minor units + code
- Presentation: `DisplayLocaleProfile` (product default **en-GB** + London + GBP)
- `money(CODE)` never converts; locale only groups/symbolises

## Guidance for agents

1. Model with explicit `ref`s first.
2. If the domain is “kinds of X with shared lifecycle”, try **state machine** or **separate entities** before poly.
3. If the domain is “shared child of many parents”, use sparse FKs or file for typed poly (#1240).
4. Put tenant-variable shape in `json` + core FKs, not a new table per customer.
5. Never dual-lock row drill / open-via — use framework `open:` hops.
