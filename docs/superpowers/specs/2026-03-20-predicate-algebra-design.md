# Predicate Algebra for Scope Rules

**Date**: 2026-03-20
**Status**: Proposed
**Issue**: Foundational — addresses gaps surfaced by #556 and informed by RDBMS theory audit

## Problem

Dazzle's scope rule system grew organically from simple owner-based filtering toward arbitrary data access policies. The current implementation uses ad-hoc filter dictionaries (`field__in_subquery`, `field__ne`, etc.) with pattern-specific code paths (`_extract_condition_filters`, `_build_via_subquery`, `_build_fk_path_subquery`). Each new access pattern requires a new special case.

This creates two problems:
1. **Expressiveness gaps**: depth-2+ FK traversal, OR conditions in SQL, NOT EXISTS, and aggregate conditions cannot be expressed or execute suboptimally.
2. **No formal correctness guarantee**: a scope rule that references a non-existent FK path silently produces a broken filter rather than failing at validation time.

## Design Principles

- **DSL consumers are AI agents**, not humans reading cold. Precision and formal correctness matter more than ergonomics.
- **Explicit paths**: the DSL author (or agent) spells out FK traversals. No implicit resolution magic.
- **If it validates, it produces correct SQL.** The algebra is the formal contract between the DSL and the query layer.
- **Backward compatibility is not a constraint.** Existing apps will revalidate against the new system. No shims or dual paths.

## Positioning

Dazzle is not a policy engine (Cedar, OPA, Zanzibar) — those evaluate allow/deny decisions but don't generate apps. Dazzle is not a query engine (Hasura, PostgREST) — those expose databases but don't model domains. Dazzle compiles domain specifications into running applications, and the scope system compiles access rules into SQL predicates that enforce row-level security.

The predicate algebra is the formal foundation that makes this compilation trustworthy: "If you can represent your domain access rules as a predicate tree, Dazzle can model it and build a secure app."

## Type System Relationship

`ScopePredicate` is a new IR type that **replaces** `ConditionExpr` for scope rules. The existing `ConditionExpr` (with its `.comparison`, `.via_condition`, `.role_check`, `.grant_check` fields) remains for permit/forbid rules where Cedar-style evaluation applies.

The pipeline:
1. **Parser** emits `ConditionExpr` (unchanged parse output)
2. **Linker** converts scope-context `ConditionExpr` nodes to `ScopePredicate` trees, validating against the FK graph
3. **Validator** verifies predicate trees (path resolution, field existence)
4. **Predicate compiler** (runtime) compiles `ScopePredicate` → parameterised SQL

Role checks and grant checks are **forbidden in scope rules**. They belong in `permit:`/`forbid:` blocks (Cedar operation gates). If a scope rule contains a role check, the linker emits a validation error: "Role checks belong in permit: blocks, not scope: blocks. Use 'for:' to bind scope rules to personas."

## Section 1: Predicate Algebra — Core Types

A closed set of predicate types. Every DSL scope expression compiles to a tree of these types. Both static validation and SQL compilation operate on the tree.

```
ScopePredicate (union type — one of):

  ColumnCheck(field, operator, value)
    Direct column comparison against a literal value.
    Example: status = "active"
    SQL: "status" = $1

  UserAttrCheck(field, operator, user_attr)
    Column comparison against a value resolved from the authenticated user's
    context (built-in fields or preferences).
    Example: school_id = current_user.school
    SQL: "school_id" = $1  (user_attr resolved at request time)

  PathCheck(path, operator, value)
    Column comparison where the left side traverses one or more FK relationships.
    path is a list of segments, each validated against the FK graph.
    Example: manuscript.assessment_event.school_id = current_user.school
    SQL: nested IN subqueries, one per hop.

  ExistsCheck(target_entity, bindings, negated=False)
    Tests for the existence (or non-existence) of related rows in a junction
    or related entity. Subsumes the existing ViaCondition IR type — ViaCondition
    is removed and its functionality is absorbed into ExistsCheck.
    Example: via AgentAssignment(agent = current_user, contact = id)
    Example: not via BlockList(user = current_user, resource = id)
    SQL: EXISTS / NOT EXISTS subquery.

  BoolComposite(operator, children)
    Boolean composition of child predicates. AND, OR, and NOT.
    All boolean logic compiles to SQL — no post-fetch filtering.
    Example: realm = current_user.realm or creator = current_user
    SQL: ("realm" = $1) OR ("creator" = $2)

  Tautology
    Matches all rows. Used for "scope: all" (no filtering).
    SQL: omit WHERE clause (or WHERE TRUE).

  Contradiction
    Matches no rows. Used for default-deny when no scope rule matches.
    SQL: WHERE FALSE.
```

### Properties

- **Closed**: every DSL scope expression maps to exactly one predicate type. No ad-hoc filter dictionaries.
- **Composable**: BoolComposite nests arbitrarily. AND of ORs, OR of PathChecks, NOT of ExistsChecks — all valid.
- **Depth-N paths**: PathCheck takes a list of segments. Supports any traversal depth.
- **OR compiles to SQL**: no more post-fetch filtering. Pagination, counts, and ordering work correctly with OR conditions.
- **Negation is first-class**: ExistsCheck(negated=True) and BoolComposite(NOT, [...]) both supported.

### What this replaces

The `filters: dict[str, Any]` convention with magic string keys (`field__in_subquery`, `field__ne`, `field__gt`, etc.). That dictionary is the informal, untyped predecessor of this algebra.

## Section 2: Static Validation — the FK Graph

### Entity FK Graph

Built at link time from the parsed IR. A directed graph:
- **Nodes** = entities
- **Edges** = FK relationships (ref, belongs_to fields), labeled with the field name

```
ManuscriptFeedback --manuscript_id--> Manuscript
Manuscript --student_id--> Student
Manuscript --assessment_event_id--> AssessmentEvent
AssessmentEvent --school_id--> School
```

### Validation Rules

| Predicate | Validation | Error on failure |
|-----------|-----------|------------------|
| ColumnCheck | `field` exists on the entity | "Entity 'X' has no field 'Y'" |
| UserAttrCheck | `field` exists; `user_attr` is resolvable (User entity field or known preference) | "Cannot resolve current_user.Z" |
| PathCheck | Walk FK graph: each segment resolves to a valid FK edge, terminal field exists on final entity | "Invalid path: X has no FK 'Y'" or "Entity Z has no field 'W'" |
| ExistsCheck | Target entity exists; each binding field exists on the junction entity; at least one binding connects back to the scoped entity | "Junction 'X' has no field 'Y'" |
| BoolComposite | Each child validates recursively | Errors propagated from children |

### Path Resolution Algorithm

Paths accept both relation names (`manuscript`) and FK field names (`manuscript_id`). The linker normalises to FK field names internally. `dazzle lint` suggests the canonical form.

Resolution for each path segment:
1. If segment matches an FK field name exactly (e.g., `manuscript_id`), use it directly.
2. If segment matches a relation name (e.g., `manuscript`), look for `{segment}_id` in the entity's fields. If found and it's a ref/belongs_to field, use that FK field.
3. If neither matches, emit validation error.

### FK Graph Edge Cases

- **Circular FK relationships** (A → B, B → A): valid in the graph. PathCheck paths are validated segment-by-segment, not for cycles. A path like `a.b.a.b` is technically valid (though absurd) — the lint layer can warn about paths longer than a configurable depth (default: 5).
- **Self-referential FKs** (e.g., `manager_id: ref Employee`): valid. `manager.manager.department_id = current_user.department` produces depth-2 nested subquery. Works naturally with the segment-by-segment resolution.
- **No depth limit enforced by the algebra.** The compiler generates nested subqueries to any depth. Lint warns at depth > 3.

### Entities Without FKs

Entities with no ref/belongs_to fields can only use ColumnCheck, UserAttrCheck, ExistsCheck (as junction target), BoolComposite, Tautology, and Contradiction. PathCheck is invalid on such entities (validation error: "PathCheck requires FK fields").

### Default Behavior When No Scope Rules Exist

If an entity has no `scope:` block, no row filtering is applied (equivalent to Tautology). This preserves backward compatibility for entities that rely solely on `permit:` for access control. Entities with a `scope:` block but no matching rule for the user's persona get Contradiction (default-deny at scope layer).

### What this catches that today's system does not

- Scope rule referencing a non-existent FK path — currently silently produces a broken filter.
- Depth-2+ paths validated end-to-end across the entity graph.
- Via clause binding typos — currently silently produce wrong results.

### Codebase location

The FK graph is built during linking (`src/dazzle/core/linker.py`), stored on the `AppSpec`, and consumed by the validator. `dazzle validate` surfaces errors.

## Section 3: SQL Compilation

Each predicate type has one deterministic SQL translation. The compiler walks the tree and emits parameterised SQL fragments.

### Compilation Rules

```
ColumnCheck("status", EQ, Literal("active"))
  → WHERE "status" = $1
  → params: ["active"]

UserAttrCheck("school_id", EQ, "school")
  → WHERE "school_id" = $1
  → params: [resolved_value]

PathCheck(["manuscript", "student_id"], EQ, CurrentUser)
  → WHERE "manuscript_id" IN (
      SELECT "id" FROM "Manuscript" WHERE "student_id" = $1
    )
  → params: [user_entity_id]

PathCheck(["manuscript", "assessment_event", "school_id"], EQ, UserAttr("school"))
  → WHERE "manuscript_id" IN (
      SELECT "id" FROM "Manuscript" WHERE "assessment_event_id" IN (
        SELECT "id" FROM "AssessmentEvent" WHERE "school_id" = $1
      )
    )
  → params: [resolved_school]

ExistsCheck("AgentAssignment", bindings, negated=False)
  → WHERE EXISTS (
      SELECT 1 FROM "AgentAssignment"
      WHERE "agent" = $1 AND "contact" = "outer_table"."id"
    )

ExistsCheck("BlockList", bindings, negated=True)
  → WHERE NOT EXISTS (
      SELECT 1 FROM "BlockList"
      WHERE "user_id" = $1 AND "resource_id" = "outer_table"."id"
    )

BoolComposite(AND, [child1, child2])
  → (child1_sql) AND (child2_sql)

BoolComposite(OR, [child1, child2])
  → (child1_sql) OR (child2_sql)

BoolComposite(NOT, [child])
  → NOT (child_sql)

Tautology  → omit WHERE clause
Contradiction  → WHERE FALSE
```

### PathCheck Compilation Algorithm

Input: `PathCheck(path=["manuscript", "assessment_event", "school_id"], op=EQ, value=UserAttr("school"))` on entity `ManuscriptFeedback`.

Algorithm (inside-out):
1. Take terminal segment `school_id` — this is the comparison field on the innermost entity.
2. Take next segment `assessment_event` — resolve to FK `assessment_event_id` on `Manuscript`, target entity `AssessmentEvent`. Emit: `SELECT "id" FROM "AssessmentEvent" WHERE "school_id" = $1`
3. Take next segment `manuscript` — resolve to FK `manuscript_id` on `ManuscriptFeedback`, target entity `Manuscript`. Emit: `SELECT "id" FROM "Manuscript" WHERE "assessment_event_id" IN (inner)`
4. Outermost: `WHERE "manuscript_id" IN (outer)`

Result:
```sql
WHERE "manuscript_id" IN (
  SELECT "id" FROM "Manuscript" WHERE "assessment_event_id" IN (
    SELECT "id" FROM "AssessmentEvent" WHERE "school_id" = $1
  )
)
```

The scoped entity (`ManuscriptFeedback`) is implicit from context — the compiler receives it as the `entity_name` parameter.

### Complex Composition Examples

**OR of two PathChecks:**
`(manuscript.student_id = current_user) or (manuscript.assessment_event.school_id = current_user.school)`

```sql
WHERE ("manuscript_id" IN (SELECT "id" FROM "Manuscript" WHERE "student_id" = $1))
   OR ("manuscript_id" IN (
         SELECT "id" FROM "Manuscript" WHERE "assessment_event_id" IN (
           SELECT "id" FROM "AssessmentEvent" WHERE "school_id" = $2
         )
       ))
```

**NOT EXISTS:**
`not via BlockList(user = current_user, resource = id)`

```sql
WHERE NOT EXISTS (
  SELECT 1 FROM "BlockList"
  WHERE "user" = $1 AND "resource" = "ManuscriptFeedback"."id"
)
```

### Simplification Rules

- `AND(x, Tautology)` → `x`
- `OR(x, Tautology)` → `Tautology`
- `AND(x, Contradiction)` → `Contradiction`
- `OR(x, Contradiction)` → `x`
- `NOT(Tautology)` → `Contradiction`
- `NOT(Contradiction)` → `Tautology`
- `NOT(NOT(x))` → `x`

These simplifications are applied during predicate construction, not during SQL compilation.

### Design Decisions

**Depth-N as nested subqueries, not JOINs.** Each PathCheck segment compiles to one nesting level of `IN (SELECT ...)`. Reasons:
- Subqueries compose cleanly — each segment is independent
- No table alias conflicts to manage
- Postgres optimises IN subqueries to semi-joins — the query planner chooses join strategy
- Simpler to validate: each nesting level maps to one FK edge

**All boolean logic in SQL.** Post-fetch OR filtering is eliminated. BoolComposite(OR) compiles to SQL OR. This fixes pagination and count accuracy for OR conditions.

**Runtime assertions at startup.** The compiler verifies all scope rules produce valid SQL at server startup — table names exist, column names exist, parameter counts match. Belt-and-suspenders over static validation.

### What gets replaced

`_extract_condition_filters()`, `_build_fk_path_subquery()`, `_build_via_subquery()`, the filter-dict → QueryBuilder pipeline, and the post-fetch OR filtering path. These all collapse into:

```python
def compile_predicate(
    predicate: ScopePredicate,
    entity_name: str,
    fk_graph: FKGraph,
) -> tuple[str, list[Any]]:
    """Compile a predicate tree to a parameterised SQL WHERE fragment."""
```

## Section 4: DSL Syntax Changes

Minimal surface changes. The grammar extends to fill expressiveness gaps.

### Unchanged

```dsl
scope:
  list: school_id = current_user.school          # → UserAttrCheck
    for: teacher
  list: owner = current_user                      # → UserAttrCheck
    for: user
  list: status = active                           # → ColumnCheck
    for: viewer
  list: via AgentAssignment(agent = current_user, contact = id)
    for: agent                                    # → ExistsCheck
```

### Extended — depth-N paths

```dsl
scope:
  list: manuscript.assessment_event.school_id = current_user.school
    for: teacher
```
Parser change: split path segments without depth limit. Each segment validated against FK graph.

### Extended — OR compiles to SQL

```dsl
scope:
  list: realm = current_user.realm or creator = current_user
    for: forgemaster
```
No syntax change. Compilation change: OR now emits SQL OR instead of post-fetch filter.

### New — NOT EXISTS

```dsl
scope:
  list: not via BlockList(user = current_user, resource = id)
    for: user
```
New syntax: `not via` prefix. Compiles to ExistsCheck(negated=True).

Parser implementation: the scope condition parser checks for `NOT` token before `VIA` token. Both `TokenType.NOT` and `TokenType.VIA` already exist in the lexer. The parser emits a `ViaCondition` with a `negated=True` flag (or directly emits a `ConditionExpr` with negation), which the linker converts to `ExistsCheck(negated=True)`.

### New — parenthesised NOT

```dsl
scope:
  list: not (status = archived)
    for: user
```
Compiles to BoolComposite(NOT, [ColumnCheck(...)]).

### Deprecated and removed

- Filter-dict magic keys (`field__in_subquery`, `field__ne`) — replaced by predicate compiler.
- Post-fetch OR filtering path — replaced by SQL OR compilation.

## Section 5: Migration and Verification

### Migration — clean break

No backward compatibility layer. The old filter-dict pipeline is replaced entirely:

1. **Introduce**: new `ScopePredicate` types, FK graph, predicate compiler.
2. **Replace**: `_extract_condition_filters` → `compile_predicate`. Remove `_build_via_subquery`, `_build_fk_path_subquery`, filter-dict conventions, post-fetch OR path.
3. **Revalidate**: all example apps run through `dazzle validate` to confirm their scope rules compile correctly under the new system.

### Scope fidelity integration

The existing scope fidelity framework (#548) gains predicate introspection:

- **Auto-generated test scenarios**: a PathCheck tells the fidelity checker what FK chains need test data. A BoolComposite(OR) tells it to test each branch independently plus the combination.
- **Exhaustive persona coverage**: for each ScopeRule with a `for:` clause, auto-generate seed data that is visible to that persona and data that is not, then verify the boundary.
- **OR correctness**: auto-generate cases where rows match first branch only, second branch only, both, and neither.

### Performance lint (future work, enabled by this design)

The predicate algebra gives the linter full visibility into which columns appear in WHERE clauses and subqueries. Future lint rules can suggest:
- Index creation for columns used in scope filters
- Denormalization hints for deep path traversals on high-volume entities
- Query plan warnings for complex OR compositions

These are warnings, not errors. Not part of this implementation scope.

## Files Affected

### New files
- `src/dazzle/core/ir/predicates.py` — ScopePredicate union type and node classes
- `src/dazzle/core/ir/fk_graph.py` — FK graph construction and path validation
- `src/dazzle_back/runtime/predicate_compiler.py` — predicate tree → SQL compilation

### Modified files
- `src/dazzle/core/linker.py` — build FK graph, compile scope conditions to predicate trees
- `src/dazzle/core/validator.py` — validate predicate trees against FK graph
- `src/dazzle/core/dsl_parser_impl/entity.py` — parse `not via`, `not (...)`, depth-N paths
- `src/dazzle/core/ir/conditions.py` — may be superseded by predicates.py for scope rules
- `src/dazzle_back/runtime/route_generator.py` — replace filter extraction with compile_predicate
- `src/dazzle_back/runtime/query_builder.py` — simplify or remove filter-dict parsing

### Removed code
- `_extract_condition_filters()` — replaced by predicate compiler
- `_build_fk_path_subquery()` — subsumed by PathCheck compilation
- `_build_via_subquery()` — subsumed by ExistsCheck compilation
- Post-fetch OR filtering in `_list_handler_body` — replaced by SQL OR
- Filter-dict magic key conventions (`__in_subquery`, `__ne`, etc.)

### Test files
- New: `tests/unit/test_predicate_algebra.py` — predicate type construction and validation
- New: `tests/unit/test_predicate_compiler.py` — SQL compilation for each predicate type
- New: `tests/unit/test_fk_graph.py` — FK graph construction and path resolution
- Modified: `tests/unit/test_scope_rules.py` — updated for new predicate types
- Modified: `tests/unit/test_scope_via.py` — updated for ExistsCheck (ViaCondition → ExistsCheck)
- Modified: `tests/unit/test_cedar_row_filters.py` — updated for predicate compiler
- Modified: `tests/unit/test_dotted_scope_path.py` — updated for PathCheck (replaces _build_fk_path_subquery tests)

Existing test files (`test_scope_via.py`, `test_scope_rules.py`, `test_dotted_scope_path.py`) contain parser and compilation tests that validate current behavior. During implementation, these tests should be updated to assert against `ScopePredicate` types rather than `ConditionExpr` and filter dicts. Parser-level tests (DSL string → IR) remain valid since the DSL syntax is largely unchanged.
