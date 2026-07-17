# Data representation: defaults and escape hatches

**Related:** [#1617](https://github.com/manwithacat/dazzle/issues/1617) (RFC),
[#1240](https://github.com/manwithacat/dazzle/issues/1240) (poly association),
`subtype_of:` / ADR-0026 (TPT inheritance).

## Pattern IDs (agent vocabulary)

Agents and tools **must** reason in these IDs (not free-text “polymorphism”):

| ID | Layer | One-liner |
|----|-------|-----------|
| `rel.explicit_ref` | default | Single parent `ref Entity` |
| `rel.exclusive_fks` | hatch | Sparse exclusive nullable FKs + `first_non_null` open |
| `rel.tpt_subtype` | hatch | True ISA via `subtype_of:` |
| `rel.poly_ref` | hatch | Typed `poly_ref [T…]` shared child → many parents |
| `rel.json_extension` | hatch | Core columns + `json` bag |
| `rel.sti` | discouraged | Single table + type — prefer TPT / exclusive FKs |
| `rel.eav` | last resort | Prefer JSONB projections |
| `rel.host_extension` | dual-lock | Host owns extension schema |

### Control plane (decide → classify → prove)

```bash
dazzle representation patterns
dazzle representation decide --text "company or sole trader client overview"
dazzle representation classify -p .
dazzle prove representation -p .
# MCP: representation(operation=patterns|decide|classify|prove)
```

- **decide** — ladder → `pattern_id` + DSL sketch + reject list
- **classify** — project AppSpec evidence (hand-rolled poly, exclusive sets, open-via gaps)
- **prove** — static integrity gate (complements `dazzle db verify` for DB row counts)

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
| **`json` / JSONB payload** | Tenant/feature-variable bags; keep core columns normalized | **#1619** convention + GIN recipe + compact list display |
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
out-of-band SQL / legacy data.

#### Soft vs hard integrity (#1620)

| Layer | Mechanism | When |
|-------|-----------|------|
| **Soft** | `dazzle db verify` → `unanchored` / `exclusive_conflict` | Always available; audits legacy/manual SQL |
| **Hard** | Named `CHECK` on the table: exactly one of the exclusive FKs is non-null | Emitted by `build_metadata` / migration engine from the same invariant shape |

CHECK name: `ck_<Entity>_excl_<fields>` (or shortened hash). Expression uses
portable `CASE WHEN col IS NOT NULL THEN 1 ELSE 0 END` summed to `= 1`.

Soft verify remains useful after CHECK exists (reports counts; CHECK blocks
writes). Prefer soft-only until you need storage-layer defence against out-of-band
writes.

## JSONB extension pattern (#1619)

**Pattern ID:** `rel.json_extension`

### Convention

| Put in typed columns | Put in `json` bag |
|----------------------|-------------------|
| Primary key, email, name, money | Tenant-specific flags |
| Foreign keys / exclusive FKs | Feature payloads |
| Status enums that drive RBAC/surfaces | UI preferences, sparse metadata |

```dsl
entity Client "Client":
  id: uuid pk
  name: text required
  email: email required
  # identity stays queryable + scoped
  extensions: json   # tenant/feature bag only
```

### Display

List/detail **must not** dump raw JSON. Cells with type `json` use a compact
`key: val · …` summary (`format_cell` / list cell core). Prefer **omitting**
json columns from list projections; show on detail when needed.

### GIN index (Postgres)

DSL `index` is btree-oriented. For containment queries into a bag:

```bash
dazzle representation gin-sql Client --column extensions
```

Emits:

```sql
CREATE INDEX IF NOT EXISTS ix_Client_extensions_gin
ON "Client" USING gin ("extensions" jsonb_path_ops);
```

Apply via hand migration / ops SQL. Dazzle maps `json` fields to **JSONB**.

### Agent / prove

```bash
dazzle representation decide --tenant-json
dazzle representation classify -p .   # json_field info; json_identity_smell warning
dazzle prove representation -p .
```

`json_identity_smell`: entity has only json bags beside system columns — promote
identity/FKs to typed columns.

## Display is not storage

Locale and money rules ([#1597](https://github.com/manwithacat/dazzle/issues/1597)):

- Storage: UTC datetimes, calendar **date** fields, money minor units + code
- Presentation: `DisplayLocaleProfile` (product default **en-GB** + London + GBP)
- `money(CODE)` never converts; locale only groups/symbolises

## Guidance for agents

1. Call `representation decide` (or structured signals) **before** modeling poly-shaped domains.
2. Model with explicit `ref`s first (`rel.explicit_ref`).
3. Alternative parents on one row (CyFuture client types) → `rel.exclusive_fks`, **not** `poly_ref` and **not** host open patches.
4. Shared child of many parents (Comment/Attachment) → four-question interrogation; only then `rel.poly_ref`.
5. “Kinds of X with shared lifecycle” → state machine or separate entities before `subtype_of:`.
6. Tenant-variable shape → `rel.json_extension` (core FKs stay columns).
7. Never dual-lock row drill / open-via — use framework `open:` hops.
8. Close the loop: `representation classify` + `prove representation` + `db verify`.
