# ADR-0019: The Surface Triple as Atomic Unit of Verifiable Behavior

**Status:** Accepted
**Date:** 2026-03-28
**Context:** UX contract verification revealed that entities alone are insufficient for reasoning about system behavior

## Background

During the implementation of UX contract verification (v0.49.14), the system repeatedly failed when treating entities as the primary unit of analysis. Contracts derived from entity definitions alone produced false positives and false negatives because:

- An entity with DELETE permission but no view surface has no delete button to verify
- A required field declared as `uuid` renders as a search-select widget (not a text input) when the surface treats it as a foreign key
- An `admin` persona with full entity permissions may see nothing if no surface grants them access
- An operation exists in the permission matrix but is invisible to the user unless a surface renders it

Every fix during contract convergence moved the system toward the same conclusion: **the testable unit of behavior is not the entity, not the surface, and not the persona — it is their intersection.**

## Thesis

### The Surface Triple

The atomic unit of verifiable system behavior is:

```
(Entity, Surface, Persona)
```

Where:
- **Entity** defines what data exists and what operations are possible
- **Surface** defines which operations are rendered and how fields are presented
- **Persona** defines who can see and act on those rendered operations

No single element is sufficient:
- Entity without Surface: the operation exists in the database but is invisible to users
- Surface without Persona: the page renders but access is uncontrolled
- Persona without Surface: the permission is granted but there is no UI to exercise it

### The Missing Leg Signal

When one leg of the triple is absent, it signals a missing assumption in the business model:

| Missing | Signal | Example |
|---------|--------|---------|
| No Surface for Entity | Entity exists in schema but users cannot interact with it. Is it internal-only? A background entity? Or was the UI simply forgotten? | `TaskComment` has no `view` surface — is this intentional (inline display only) or an oversight? |
| No Persona for Surface | Surface renders but no one is authorized to use it. Dead UI. | A `create` surface exists but no persona has `CREATE` permission |
| No Entity for Surface | Surface references data that doesn't exist in the domain model. | A workspace region references a metric that isn't backed by an entity |

These are not bugs in the traditional sense. They are **gaps in the business model** that manifest as verifiable inconsistencies between the three legs.

### Relationship to Existing Theory

In **traditional data modeling** (Chen, Codd), the entity is primary. Behavior is derived from the data structure. Presentation is a downstream concern.

In **use case driven design** (Jacobson), the actor-goal pair drives analysis, but the "surface" — how the system presents operations — is an implementation detail, not a modeling primitive.

In **domain-driven design** (Evans), bounded contexts and aggregates are primary. The UI is an adapter in the hexagonal architecture — explicitly separated from the domain.

The surface triple differs from all three: **it treats the presentation surface as a first-class modeling element, co-equal with the data model and the actor model.** This is closer to the HCI tradition (Norman, Hutchins) where the interface IS the system from the user's perspective — but formalized as a verifiable triple rather than a design heuristic.

The closest analogue may be **activity theory** (Engestrom), where the unit of analysis is the activity system: subject (persona), object (entity), and mediating artifact (surface). The triple maps directly:

```
Activity Theory     Dazzle Triple
Subject          →  Persona
Object           →  Entity
Mediating Tool   →  Surface
```

Activity theory already argues that you cannot analyze the subject or the object in isolation — they only make sense through the mediating tool. The surface triple formalizes this for DSL-driven systems: every verifiable assertion must reference all three legs.

## Decision

1. The UX contract verification system uses the surface triple as its atomic unit. Every contract is scoped to an (entity, surface, persona) combination.

2. The `dazzle ux verify --contracts` pipeline enforces triple-completeness: it detects missing legs and reports them as verification gaps rather than false positives.

3. The DSL grammar does not change. The triple is implicit in the existing constructs: `entity` defines data, `surface` defines presentation, `persona` + `permit`/`forbid` define access. Making it explicit in the grammar is deferred until a concrete syntax is proposed.

4. Future analysis tools (coherence checks, coverage reports) should use the triple as their unit of measurement rather than entity count or surface count alone.

## Consequences

- **Contract generation** derives one contract per triple, not per entity. This is why CRUD contracts deduplicated to entity-level but RBAC contracts remained per entity-per-persona.
- **Coverage metrics** should express coverage as "triples verified / triples possible" for accurate measurement.
- **Missing leg detection** becomes a first-class diagnostic: `dazzle validate` can flag entities without surfaces, surfaces without personas, and permissions without surfaces.
- **Compliance evidence** maps each SOC 2 / ISO 27001 control to a set of verified triples, not just a permission matrix.
