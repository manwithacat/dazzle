# ADR-0027 — No `polymorphic_ref:` Keyword, Now or Planned

**Status:** Accepted (v0.72.14) — **superseded in part by [ADR-0042](0042-poly-ref-scoping.md) (#1448)**: the pre-committed escape hatch below has now fired (the four-question interrogation failed against AegisMark's `AIJob`) and is realized as the validated, scope-composable typed `poly_ref` construct. The blanket "now or planned" closure becomes "closed except via `poly_ref` + the `field[Type]` scope selector."
**Issue:** #1240 (closed wontfix-by-design); part of the #1217 3NF coverage audit
**Pair:** [inference KB `polymorphic_association_antipattern`](https://github.com/manwithacat/dazzle/blob/main/src/dazzle/mcp/inference_kb.toml)

## Decision

Dazzle will **not** ship a `polymorphic_ref:` keyword, a `ref X | Y | Z`
union-type sugar, or any other DSL construct expressing the Rails
`belongs_to :subject, polymorphic: true` shape. The Phase 1 audit table in
#1217 originally listed "polymorphic association" as a coverage gap; this
ADR reframes it as **deliberately unsupported, by design**.

If a future use case appears that genuinely requires polymorphic association
*after surviving the four-question interrogation below*, the implementation
shape is pre-committed to an explicit-discriminator `polymorphic_ref:` block
with a visible `discriminator:` field and an exhaustive `targets:` list.
**The `ref X | Y | Z` union sugar is rejected now, with the reasoning fresh,
to short-circuit any future "let's just make `ref` polymorphic" proposal.**
Hiding the discriminator is the wrong default for any real query pattern,
and overloading `ref` adds parser cost and agent-instruction cost for no
real semantic gain.

## Framing

Polymorphic association as a first-class modelling primitive is a Rails-era
artefact, not a relational-modelling result. It exists in the ORM literature
because ActiveRecord made `belongs_to :commentable, polymorphic: true`
trivial to write, not because Codd or anyone working in proper schema design
ever argued schemas should express it. Database-textbook documentation of
the pattern is descriptive of frameworks, not prescriptive for schemas.

### Two framing principles

**Runtime-dispatched polymorphism creates more problems than it solves in
the vast majority of cases. Compile-time parametric and bounded polymorphism
do not.** This is the underlying reason the contracts below get broken.
`subtype_of:` (ADR-0026) is bounded — the framework knows the full child
set at link time and can validate, plan queries, and compose scope rules
against it. A `(type, id)` discriminator is runtime-dispatched — every
read has to branch on the row value, every cross-target query has to be
composed in application code, and no static analyser can reason about
which targets are reachable. The first kind earns its complexity. The
second kind defers it onto every consumer.

**Defer decisions to runtime only when the dynamism is essential to the
domain, not merely convenient for the author.** This is the decision
heuristic. "I want one Comment entity attached to anything" is author
convenience; the domain knows whether it's an article comment or an
invoice comment at the moment the comment is created. The polymorphic
discriminator is preserving an *authoring* shape that the *domain* never
actually has — and paying for that preservation at every read, every JOIN,
every scope check, for the lifetime of the schema. Runtime dispatch is the
right tool when the domain genuinely doesn't know the target until runtime
(user-driven workflows, dynamic taxonomies, federated tenants); it is the
wrong tool when the domain knows but the author wanted a shortcut.

### The three contracts

The pattern breaks three contracts the rest of Dazzle relies on:

- **Referential integrity:** no FK constraint can target multiple tables.
  The `(type, id)` pair can dangle, point at the wrong table, or never
  point anywhere at all. None of the framework's existing FK-graph
  validation, cascade-delete logic, or query-builder JOIN composition can
  reason about a discriminator-driven target.
- **Scope composition:** RBAC scope rules can't traverse a `(type, id)`
  pair because the target depends on a row value. The predicate algebra
  (ADR-0009) is built on typed traversal; polymorphic FKs are an opaque
  hole in it.
- **JOIN-based queries:** the planner can't see through the discriminator.
  Every cross-target query needs application-side dispatch — which is
  exactly the kind of "fall back to Python routes" friction the rest of
  the DSL exists to eliminate.

## Every classic example fails the interrogation

Every "polymorphic association needed!" case, when interrogated, turns out
to be one of four shapes the framework already supports:

1. **Is this UI-driven?** If the only reason "Comment" / "Attachment" /
   "Like" is one entity is that the UI renders them similarly, refactor
   per-target. `ArticleComment` and `InvoiceComment` have different
   retention, audit, visibility, and notification rules — collapsing them
   was UI convenience masquerading as domain modelling. Use one entity
   per business-distinct use of the verb.

2. **Is this an event, not a reference?** Audit logs, notifications, and
   activity feeds usually want an append-only event-stream entity with a
   typed `aggregate_type` + JSON `payload`, not a polymorphic FK. You're
   recording an event *about* the entity, not *referencing* it — different
   semantics, different lifecycle, different scope rules. The `(type, id)`
   pair is acceptable in an event-stream entity because events don't need
   referential integrity into mutable tables (HLESS-shaped — see
   ADR-0015).

3. **Is this a junction table in disguise?** Tags-across-entities is the
   classic. `entity_tags(tag_id, entity_type, entity_id)` is a bad
   junction. Per-pair junctions (`ArticleTag`, `ProductTag`) are trivial
   to write, give per-target indexing, per-target retention, per-target
   rate-limiting — all things you'll want eventually.

4. **Is this actually TPT?** If the N target entities share substantial
   fields and "the union" is a meaningful concept (you query across all
   of them), use `subtype_of:` (ADR-0026) with a real base entity. The
   feature shipped exactly for this case.

The remaining residue — genuinely small-N (≤3), mutually-exclusive targets,
no shared semantics — is the legitimate exception. Express it as per-target
nullable refs + a CHECK constraint that exactly one is non-null. Works
today with vanilla refs; if the pattern becomes common we may ship a tiny
`mutex_refs:` modifier to express the CHECK declaratively. That's a small
ergonomic win, not polymorphism.

**Prior on "this is a legitimate polymorphic association use case": ~5%.**
The default outcome of the interrogation is: not-polymorphic, refactor.
Only if the use case survives all four questions does an implementation
issue get filed — and even then, the shape is the explicit
`polymorphic_ref:` block above, never the union-type sugar.

## Rejected alternatives

- **`polymorphic_ref:` block, ship now.** Speculatively building the
  feature without a real consumer risks over-fitting to a hypothetical
  case. The four-question interrogation has not yet failed against any
  Dazzle consumer (AegisMark, Penny Dreadful, hr_records, asset_registry
  all model around it). Build it when the interrogation fails, not before.
- **`ref X | Y | Z` union-type sugar.** Rejected outright. Hides the
  discriminator (authors can't query by `subject_type` directly), makes
  partial FK constraints impossible to express in DDL, and overloads
  `ref` with two semantic meanings (typed FK vs. discriminated union).
  Even if we ever build the feature, this shape is off the table.
- **"List the pattern but warn against it."** The validator already
  emits `W_LOOKS_POLYMORPHIC` when an entity declares a `*_type` enum
  + `*_id` uuid pair. That's strong enough — agents see the warning
  and either refactor (the desired outcome) or override (which they
  must justify in review).

## Consequences

- The Phase 1 coverage table in #1217 reads **⚠️ intentionally unsupported**
  for "polymorphic association", not ❌. The framing matters: this is an
  architectural stance, not a missing feature.
- The inference KB carries `polymorphic_association_antipattern` as a
  `[[modeling_guidance]]` entry with explicit triggers (`polymorphic
  association`, `subject_type and subject_id`, `commentable_type`,
  Rails-derived spellings) so the MCP `knowledge` tool serves the
  refusal automatically when an agent searches for the pattern.
- The validator's existing `W_LOOKS_POLYMORPHIC` warning is now load-bearing
  and must keep firing on any `*_type + *_id` pair. The warning's message
  steers toward per-target refs first, `subtype_of:` second.
- Agents using `bootstrap` or `dsl.analyze` on a spec describing
  comments-on-any-entity, attachments-across-types, etc. should hit the
  modeling guidance entry and propose one of the four alternatives. If
  bootstrap doesn't yet expose the guidance directly, that's covered by
  #1249 (the cross-pattern bootstrap-recognition follow-up).
- No DSL parser changes. No IR changes. No future-proofing reserved
  keywords. The decision is structural, not deferred.

## Revisiting

If a use case ever appears that survives the four-question interrogation,
the trigger is: a Dazzle consumer files a concrete issue (not a hypothetical)
naming the entity, the targets, and the queries that don't compose under
any of the four alternatives. At that point the issue brainstorms the
`polymorphic_ref:` block shape — not the union sugar. Until then this ADR
stands.

## References

- #1240 — Phase 3(d) polymorphic association (closed wontfix-by-design)
- #1217 — 3NF coverage audit (umbrella)
- ADR-0026 — subtype polymorphism via TPT (the closest legitimate feature)
- ADR-0009 — predicate algebra (the contract polymorphic FKs would break)
- ADR-0015 — HLESS event semantics (the right home for "events about an
  entity", which is what most polymorphic-association proposals actually
  want)
- `src/dazzle/mcp/inference_kb.toml` `polymorphic_association_antipattern`
  — the agent-facing version of this decision
- `~/Desktop/issue-1240-analysis.md` — the underlying interrogation that
  produced this ADR
