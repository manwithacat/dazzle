# ADR-0025: Authorization is Entity-Level; Field Sensitivity is Classification

**Status:** Accepted
**Date:** 2026-05-21

## Context

`examples/invoice_ops` (the SP1 keystone app) needed to restrict access to
sensitive supplier bank details. Two mechanisms can express this requirement:

1. **Field-level column security** — keep the bank-detail fields on the
   `Supplier` entity, and gate individual columns per role. A `visible_to:
   [finance_manager]` annotation (or equivalent) would suppress those
   columns from the API response and form for any other persona.

2. **Entity split** — move the bank-detail fields into a dedicated entity
   (e.g. `SupplierBankAccount`) with its own `permit:` / `scope:` rules.
   The sensitive data carries its own entity-level authorization
   independent of the parent entity.

During SP2 design the question was raised explicitly: should Dazzle offer
*both* mechanisms and let agents choose per domain? One argument for
field-level security is ergonomics — the split produces a second entity and
a second FK join that the original domain model did not have. One argument
for the entity split is that it is the only path today, so both mechanisms
overlap entirely on the set of expressible policies.

The decision is not about what is *possible* in the IR. A per-field
`visible_to` list would be a trivial IR change. The cost is the entire
**downstream analysis surface** that depends on the current invariant:
the authorization surface is the set of (entity, operation, persona)
triples, fully enumerable with no sub-entity dimension.

## Decision

**Dazzle keeps a single authorization mechanism — entity-level `permit:`
and `scope:` rules — and will NOT add field-level authorization.**

A field that requires authorization different from its sibling fields has,
by definition, a different security lifecycle: different retention policy,
different encryption at rest, different audit requirement, different access
population. A different lifecycle is a different entity. Such a field is
modelled by splitting it into its own entity and applying ordinary
entity-level RBAC to that entity.

Field *sensitivity* — "this is PII", "this is financial data" — is metadata,
not authorization. It is carried by the existing `classify` / `pii()`
constructs and is orthogonal to `permit:` / `scope:`. Classifying a field
does not gate access; it annotates the field for compliance evidence
extraction, data-product catalogues, and audit tooling.

The entity-level enforcement seam is `AccessContext.bypasses_tenant_filter`
in `src/dazzle/core/access.py`. This remains the single boundary. No
parallel per-field access check is introduced.

## Consequences

### Why field-level authorization breaks the analysis surface

The static `dazzle rbac matrix` command today produces a clean
role × entity × operation grid. Field-level authorization would add a
sub-entity dimension to every row: the same role might have `read` on
`Supplier` but not on `Supplier.iban`. That is not a 2-D grid — it is
a 3-D tensor, and the "entire security surface is enumerable" invariant
(from the ROADMAP) holds only for 2-D.

The same breakage propagates downstream:

- **`dazzle rbac verify`** — the HTTP probe checks entity-level routes.
  Field-level authorization would require probing individual response
  fields per role, multiplying the probe surface by the number of sensitive
  columns across all entities.
- **Compliance evidence mapper** — the ISO 27001 / SOC 2 pipeline extracts
  evidence rows as `(control, entity, operation, persona)` tuples. A
  field-level gate would require `(control, entity, field, operation,
  persona)` — five-dimensional evidence with no existing control-mapping
  vocabulary.
- **OpenAPI response schemas** — today one schema per entity per operation.
  Field-level authorization would require role-conditional schemas: the
  `GET /supplier/{id}` response schema is different for `finance_manager`
  vs `procurement_officer`. OpenAPI 3.x has no standard way to express
  this; it degrades to runtime documentation drift.

### Why offering two mechanisms violates the convergence hypothesis

Giving agents two DSL idioms for one intent — field-level `visible_to`
versus entity split — means two apps with identical security requirements
can diverge structurally. Every agent that reads an existing app must now
recognise both patterns and reason about their equivalence. Every agent
that generates a new app must choose between them. That is a hidden
decision the DSL should not expose: convergence across agent sessions
requires one canonical form.

### The rule agents follow

> **Does this field have its own lifecycle?**
> — its own retention, encryption, audit requirement, or access population?

- If **yes** → split it into its own entity. Apply `permit:` / `scope:` on
  that entity in the normal way.
- If **no** → keep it on the entity. If it is sensitive, annotate it with
  `classify` or `pii()` for compliance evidence. No access gate is needed
  beyond the entity-level one.

One question is explicitly **deferred** and tracked as a future issue (not
built): whether `classify` should one day *derive* runtime field masking —
a computed, statically-analysable behaviour that would remain in the
enumerable-surface invariant. This is meaningfully distinct from a declared
parallel `permit:` system, and is out of scope for this ADR.

### Positive

- **Single security surface.** The role × entity × operation grid stays
  2-D and fully enumerable. Static analysis, compliance evidence, and API
  schema generation all operate on the same flat space.
- **No dark corners.** Every access decision is visible in the entity-level
  `permit:` / `scope:` block. There is no secondary gate that a reviewer
  can miss by reading only the entity definition.
- **Canonical agent output.** One DSL idiom for one intent. Two agents
  working independently on the same requirements produce structurally
  equivalent apps.
- **`classify` / `pii()` remain the sensitivity annotation layer.** Their
  semantics (compliance metadata, not access control) are unambiguous.

### Negative

- **Entity split has schema cost.** A `SupplierBankAccount` entity means a
  second table, a second FK join, and a second `dazzle db revision`. For
  very small apps this is arguably over-engineering. The design choice is
  that correctness and analysability outweigh the join.
- **Ergonomic friction at the margin.** Restricting three fields on a
  20-field entity requires an entity split rather than three annotations.
  Agents should apply the lifecycle test honestly: if the three fields
  genuinely differ in retention, encryption, or access policy, the split
  is architecturally correct, not overhead.

### Neutral

- The IR could trivially carry a per-field `visible_to`. The cost is not
  the IR change — it is the downstream analysis surface that depends on the
  current invariant. This ADR records that the cost is accepted as
  prohibitive.

## Alternatives Considered

### 1. Add field-level `visible_to:` as an opt-in annotation

Keep entity-level auth as default; allow individual fields to carry a
`visible_to: [role, ...]` override.

**Rejected:** Even as opt-in, any field carrying `visible_to` breaks the
2-D matrix invariant for that entity. Tooling either handles the general
case (costly) or silently ignores the annotation (dangerous). An optional
feature that silently degrades is worse than no feature.

### 2. Offer both, require explicit opt-in per app via `dazzle.toml`

A feature flag `[security] field_level_auth = true` enables the
field-level mechanism for apps that need it.

**Rejected:** This forks the analysis surface on a per-app basis. The
compliance evidence mapper and RBAC matrix would need two code paths.
Cross-app aggregation (security posture across a fleet of Dazzle apps)
would be impossible without knowing each app's flag value. The convergence
hypothesis fails at the fleet level.

### 3. Derive field masking from `classify` today

Treat `classify`-annotated fields as automatically masked for roles without
`read` on the parent entity (no change) and visible only to roles that also
have a new `classify_access: [tag]` grant on the parent entity.

**Rejected for now:** This is closer to the deferred option described above
than to a parallel `permit:` system, and it is worth evaluating properly.
It requires a clear spec for how `classify_access` composes with `scope:`,
how it appears in the RBAC matrix, and how it is probed by `rbac verify`.
Deferring keeps the surface clean until the design is complete.

## Related

- [ADR-0007](0007-rbac-three-layers.md) — RBAC: static matrix + dynamic
  conformance + audit trail. This ADR keeps all three layers operating on
  entity-level granularity.
- [ADR-0010](0010-permit-scope-separation.md) — `permit:` is the role gate;
  `scope:` is the row filter. Field-level gating would be a third
  orthogonal axis — rejected here.
- [ADR-0019](0019-surface-triple-as-atomic-unit.md) — (Entity, Surface,
  Persona) triple as the atomic unit of verifiable behaviour. Field-level
  authorization would expand that triple to a quad.
- `src/dazzle/core/access.py` — `AccessContext.bypasses_tenant_filter` is
  the enforcement seam. Remains entity-level.
