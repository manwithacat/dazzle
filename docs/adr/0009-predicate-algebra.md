# ADR-0009: Scope Predicate Algebra

**Status:** Accepted
**Date:** 2026-03-20

## Context

Dazzle DSL `scope:` blocks define row-level access rules that compile to SQL WHERE clauses at runtime. The original implementation used ad-hoc filter dictionaries that grew organically as new rule forms were added. By v0.45 the filter dictionary approach had:

- No formal grammar — valid expressions were defined implicitly by parser behaviour
- No FK graph validation — rules referencing non-existent paths silently produced wrong SQL
- Expressiveness gaps — junction table checks and negation required workarounds
- No path to future compilation targets such as Postgres RLS or Cedar policies

The scope block design (see related design note) introduced a formal `scope:` keyword. This ADR captures the algebra that `scope:` rules compile to.

## Decision

Scope rules compile to a **closed formal predicate algebra** with six types:

| Type | Represents |
|------|-----------|
| `ColumnCheck` | Direct column equality: `status = archived` |
| `UserAttrCheck` | User attribute equality: `school_id = current_user.school` |
| `PathCheck` | Depth-N FK traversal: `manuscript.assessment_event.school_id = current_user.school` |
| `ExistsCheck` | EXISTS / NOT EXISTS via junction table |
| `BoolComposite` | AND / OR / NOT over sub-predicates |
| `Tautology` / `Contradiction` | Constant truth values for default-deny and open access |

All predicates are validated against the FK graph at **link time** (`dazzle validate`). A scope rule that references a non-existent column or an invalid FK path is a hard error, not a runtime warning.

SQL generation is a pure function over the algebra: `predicate → SQL fragment`. No string interpolation outside that function.

## Consequences

### Positive

- **Correctness guarantee:** if a scope rule passes `dazzle validate`, it produces correct SQL
- FK graph validation catches typos and broken paths before deployment
- Future compilation targets (Postgres RLS, Cedar) are straightforward — translate the algebra, not raw strings
- Replaces ad-hoc filter dictionaries with a type-safe IR
- Enables static analysis tools: conflict detection, coverage reporting, simulation

### Negative

- Expressiveness is bounded by the six predicate types — novel rule forms require extending the algebra
- Link-time validation adds a mandatory parse+validate step before serving
- Existing DSL files with informal scope rules require migration

### Neutral

- The algebra is internal IR — DSL syntax is unchanged
- `dazzle lint` reports predicate complexity warnings but does not block serving

## Alternatives Considered

### 1. Ad-Hoc Filter Dictionaries

Continue extending the existing filter dictionary approach.

**Rejected:** No correctness guarantees, expressiveness gaps, and no path to future compilation targets. The debt was already significant at v0.45.

### 2. String-Based SQL Generation

Parse scope rules directly to SQL strings at validate time.

**Rejected:** SQL strings cannot be statically analysed, rewritten, or compiled to alternative targets. Injection risk if scope rule inputs are ever user-controlled.

### 3. ORM-Level Filtering Without Static Validation

Use SQLAlchemy expressions built dynamically at request time.

**Rejected:** No FK graph validation, no static correctness guarantee, and ties scope semantics to a specific ORM. Incompatible with the asyncpg-only stack (ADR-0008).

## Implementation

- Predicate IR types: `src/dazzle/core/ir/predicates.py`
- FK graph validator: `src/dazzle/core/linker/scope_validator.py`
- SQL compiler: `src/dazzle/core/compiler/scope_compiler.py`
- DSL parser mixin: `src/dazzle/core/dsl_parser_impl/scope_mixin.py`
- Tests: `tests/unit/test_scope_predicates.py`
