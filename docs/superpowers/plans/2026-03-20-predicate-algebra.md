# Predicate Algebra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc filter dictionaries with a formal predicate algebra for scope rules, providing static FK path validation and deterministic SQL compilation.

**Architecture:** New `ScopePredicate` Pydantic union type (6 node types) in the IR layer. FK graph built at link time validates all paths. Predicate compiler in the runtime layer translates trees to parameterised SQL. The existing `_extract_condition_filters` / filter-dict pipeline is removed.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, mypy. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-20-predicate-algebra-design.md`

---

### Task 1: ScopePredicate IR Types

Define the closed predicate algebra as Pydantic models.

**Files:**
- Create: `src/dazzle/core/ir/predicates.py`
- Modify: `src/dazzle/core/ir/__init__.py` (add re-exports)
- Test: `tests/unit/test_predicate_algebra.py`

- [ ] **Step 1: Write tests for predicate type construction**

```python
# tests/unit/test_predicate_algebra.py
"""Tests for ScopePredicate type construction and simplification."""
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    ExistsBinding,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)


class TestPredicateConstruction:
    def test_column_check(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        assert p.field == "status"

    def test_user_attr_check(self) -> None:
        p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
        assert p.user_attr == "school"

    def test_path_check_depth_1(self) -> None:
        p = PathCheck(path=["manuscript", "student_id"], op=CompOp.EQ, value=ValueRef(current_user=True))
        assert len(p.path) == 2

    def test_path_check_depth_3(self) -> None:
        p = PathCheck(
            path=["manuscript", "assessment_event", "school_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="school"),
        )
        assert len(p.path) == 3

    def test_exists_check(self) -> None:
        p = ExistsCheck(
            target_entity="AgentAssignment",
            bindings=[
                ExistsBinding(junction_field="agent", target="current_user"),
                ExistsBinding(junction_field="contact", target="id"),
            ],
        )
        assert not p.negated

    def test_exists_check_negated(self) -> None:
        p = ExistsCheck(
            target_entity="BlockList",
            bindings=[
                ExistsBinding(junction_field="user", target="current_user"),
                ExistsBinding(junction_field="resource", target="id"),
            ],
            negated=True,
        )
        assert p.negated

    def test_bool_composite_and(self) -> None:
        left = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        right = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
        p = BoolComposite(op=BoolOp.AND, children=[left, right])
        assert len(p.children) == 2

    def test_tautology_and_contradiction(self) -> None:
        assert Tautology() != Contradiction()


class TestSimplification:
    def test_and_with_tautology(self) -> None:
        check = ColumnCheck(field="x", op=CompOp.EQ, value=ValueRef(literal="y"))
        result = BoolComposite.make(BoolOp.AND, [check, Tautology()])
        assert isinstance(result, ColumnCheck)

    def test_or_with_tautology(self) -> None:
        check = ColumnCheck(field="x", op=CompOp.EQ, value=ValueRef(literal="y"))
        result = BoolComposite.make(BoolOp.OR, [check, Tautology()])
        assert isinstance(result, Tautology)

    def test_and_with_contradiction(self) -> None:
        check = ColumnCheck(field="x", op=CompOp.EQ, value=ValueRef(literal="y"))
        result = BoolComposite.make(BoolOp.AND, [check, Contradiction()])
        assert isinstance(result, Contradiction)

    def test_or_with_contradiction(self) -> None:
        check = ColumnCheck(field="x", op=CompOp.EQ, value=ValueRef(literal="y"))
        result = BoolComposite.make(BoolOp.OR, [check, Contradiction()])
        assert isinstance(result, ColumnCheck)

    def test_not_tautology(self) -> None:
        result = BoolComposite.make(BoolOp.NOT, [Tautology()])
        assert isinstance(result, Contradiction)

    def test_not_contradiction(self) -> None:
        result = BoolComposite.make(BoolOp.NOT, [Contradiction()])
        assert isinstance(result, Tautology)

    def test_double_negation(self) -> None:
        inner = ColumnCheck(field="x", op=CompOp.EQ, value=ValueRef(literal="y"))
        not_inner = BoolComposite(op=BoolOp.NOT, children=[inner])
        result = BoolComposite.make(BoolOp.NOT, [not_inner])
        assert isinstance(result, ColumnCheck)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_predicate_algebra.py -v`
Expected: ImportError — `predicates` module doesn't exist yet.

- [ ] **Step 3: Implement ScopePredicate types**

```python
# src/dazzle/core/ir/predicates.py
"""
Predicate algebra for scope rules.

A closed set of predicate types that every DSL scope expression compiles to.
Both static validation and SQL compilation operate on the predicate tree.

Types:
    ColumnCheck — direct column comparison against a literal
    UserAttrCheck — column comparison against current_user attribute
    PathCheck — FK-traversal comparison (depth-N nested subqueries)
    ExistsCheck — EXISTS/NOT EXISTS subquery (subsumes ViaCondition)
    BoolComposite — AND/OR/NOT boolean composition
    Tautology — matches all rows (scope: all)
    Contradiction — matches no rows (default-deny)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class CompOp(StrEnum):
    """Comparison operators for predicates."""

    EQ = "="
    NE = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"


class BoolOp(StrEnum):
    """Boolean operators for composite predicates."""

    AND = "and"
    OR = "or"
    NOT = "not"


class ValueRef(BaseModel):
    """A value in a predicate — literal, current_user, or user attribute."""

    literal: str | int | float | bool | None = None
    current_user: bool = False  # True means "the current user's entity ID"
    user_attr: str | None = None  # e.g., "school" → resolved from auth context
    literal_null: bool = False  # True means SQL NULL

    model_config = ConfigDict(frozen=True)


class ExistsBinding(BaseModel):
    """A single binding in an ExistsCheck."""

    junction_field: str
    target: str  # "id", "current_user", "current_user.attr", "null"
    operator: str = "="

    model_config = ConfigDict(frozen=True)


class ColumnCheck(BaseModel):
    """Direct column comparison against a literal value."""

    kind: Literal["column_check"] = "column_check"
    field: str
    op: CompOp
    value: ValueRef

    model_config = ConfigDict(frozen=True)


class UserAttrCheck(BaseModel):
    """Column comparison against a current_user attribute."""

    kind: Literal["user_attr_check"] = "user_attr_check"
    field: str
    op: CompOp
    user_attr: str  # "school", "department", "entity_id", etc.

    model_config = ConfigDict(frozen=True)


class PathCheck(BaseModel):
    """FK-traversal comparison. Each segment is validated against the FK graph."""

    kind: Literal["path_check"] = "path_check"
    path: list[str]  # e.g., ["manuscript", "assessment_event", "school_id"]
    op: CompOp
    value: ValueRef

    model_config = ConfigDict(frozen=True)


class ExistsCheck(BaseModel):
    """EXISTS/NOT EXISTS subquery. Subsumes ViaCondition."""

    kind: Literal["exists_check"] = "exists_check"
    target_entity: str
    bindings: list[ExistsBinding]
    negated: bool = False

    model_config = ConfigDict(frozen=True)


class Tautology(BaseModel):
    """Matches all rows. scope: all."""

    kind: Literal["tautology"] = "tautology"
    model_config = ConfigDict(frozen=True)


class Contradiction(BaseModel):
    """Matches no rows. Default-deny."""

    kind: Literal["contradiction"] = "contradiction"
    model_config = ConfigDict(frozen=True)


class BoolComposite(BaseModel):
    """Boolean composition of child predicates."""

    kind: Literal["bool_composite"] = "bool_composite"
    op: BoolOp
    children: list[ScopePredicate]

    model_config = ConfigDict(frozen=True)

    @staticmethod
    def make(op: BoolOp, children: list[ScopePredicate]) -> ScopePredicate:
        """Construct with simplification rules applied."""
        if op == BoolOp.NOT:
            assert len(children) == 1
            child = children[0]
            if isinstance(child, Tautology):
                return Contradiction()
            if isinstance(child, Contradiction):
                return Tautology()
            # Double negation elimination
            if isinstance(child, BoolComposite) and child.op == BoolOp.NOT:
                return child.children[0]
            return BoolComposite(op=op, children=children)

        # Filter out identities
        if op == BoolOp.AND:
            filtered = [c for c in children if not isinstance(c, Tautology)]
            if any(isinstance(c, Contradiction) for c in children):
                return Contradiction()
            if not filtered:
                return Tautology()
            if len(filtered) == 1:
                return filtered[0]
            return BoolComposite(op=op, children=filtered)

        if op == BoolOp.OR:
            filtered = [c for c in children if not isinstance(c, Contradiction)]
            if any(isinstance(c, Tautology) for c in children):
                return Tautology()
            if not filtered:
                return Contradiction()
            if len(filtered) == 1:
                return filtered[0]
            return BoolComposite(op=op, children=filtered)

        return BoolComposite(op=op, children=children)


# Discriminated union type
ScopePredicate = Annotated[
    Union[
        ColumnCheck,
        UserAttrCheck,
        PathCheck,
        ExistsCheck,
        BoolComposite,
        Tautology,
        Contradiction,
    ],
    Field(discriminator="kind"),
]
```

- [ ] **Step 4: Add re-exports to ir/__init__.py**

Add to `src/dazzle/core/ir/__init__.py`:
```python
from .predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_predicate_algebra.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite to confirm no regressions**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/predicates.py src/dazzle/core/ir/__init__.py tests/unit/test_predicate_algebra.py
git commit -m "feat(ir): add ScopePredicate algebra types (#556)"
```

---

### Task 2: FK Graph

Build and validate the entity foreign key graph at link time.

**Files:**
- Create: `src/dazzle/core/ir/fk_graph.py`
- Test: `tests/unit/test_fk_graph.py`

- [ ] **Step 1: Write tests for FK graph construction and path validation**

```python
# tests/unit/test_fk_graph.py
"""Tests for FK graph construction and path validation."""
from dazzle.core import ir
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.fk_graph import FKGraph


def _entity(name: str, fields: list[FieldSpec]) -> ir.EntitySpec:
    return ir.EntitySpec(name=name, title=name, fields=fields)


def _field(name: str, kind: FieldTypeKind = FieldTypeKind.STR, ref: str | None = None) -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=kind, ref_entity=ref))


def _pk() -> FieldSpec:
    from dazzle.core.ir.fields import FieldModifier
    return FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID), modifiers=[FieldModifier.PK])


class TestFKGraphConstruction:
    def test_build_from_entities(self) -> None:
        entities = [
            _entity("School", [_pk(), _field("name")]),
            _entity("Teacher", [_pk(), _field("school_id", FieldTypeKind.REF, ref="School")]),
        ]
        graph = FKGraph.from_entities(entities)
        assert graph.has_edge("Teacher", "school_id")

    def test_empty_entities(self) -> None:
        graph = FKGraph.from_entities([])
        assert graph.entity_names() == set()

    def test_self_referential(self) -> None:
        entities = [
            _entity("Employee", [_pk(), _field("manager_id", FieldTypeKind.REF, ref="Employee")]),
        ]
        graph = FKGraph.from_entities(entities)
        assert graph.resolve_target("Employee", "manager_id") == "Employee"


class TestPathResolution:
    def _build_graph(self) -> FKGraph:
        entities = [
            _entity("School", [_pk(), _field("name")]),
            _entity("Department", [_pk(), _field("school_id", FieldTypeKind.REF, ref="School")]),
            _entity("Teacher", [_pk(), _field("department_id", FieldTypeKind.REF, ref="Department")]),
            _entity("Manuscript", [_pk(), _field("teacher_id", FieldTypeKind.REF, ref="Teacher")]),
        ]
        return FKGraph.from_entities(entities)

    def test_resolve_depth_1(self) -> None:
        graph = self._build_graph()
        fk_field, target = graph.resolve_segment("Manuscript", "teacher")
        assert fk_field == "teacher_id"
        assert target == "Teacher"

    def test_resolve_depth_1_explicit_fk(self) -> None:
        graph = self._build_graph()
        fk_field, target = graph.resolve_segment("Manuscript", "teacher_id")
        assert fk_field == "teacher_id"
        assert target == "Teacher"

    def test_resolve_full_path(self) -> None:
        graph = self._build_graph()
        steps = graph.resolve_path("Manuscript", ["teacher", "department", "school_id"])
        assert len(steps) == 3
        # Final step targets the terminal field
        assert steps[-1].terminal_field == "school_id"
        assert steps[-1].target_entity == "School"

    def test_invalid_segment_raises(self) -> None:
        graph = self._build_graph()
        import pytest
        with pytest.raises(ValueError, match="has no FK"):
            graph.resolve_segment("Manuscript", "nonexistent")

    def test_field_exists_on_entity(self) -> None:
        graph = self._build_graph()
        assert graph.field_exists("School", "name")
        assert not graph.field_exists("School", "nonexistent")

    def test_belongs_to_field_resolved(self) -> None:
        entities = [
            _entity("Order", [_pk(), _field("name")]),
            _entity("LineItem", [_pk(), _field("order_id", FieldTypeKind.BELONGS_TO, ref="Order")]),
        ]
        graph = FKGraph.from_entities(entities)
        fk_field, target = graph.resolve_segment("LineItem", "order")
        assert fk_field == "order_id"
        assert target == "Order"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_fk_graph.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement FKGraph**

```python
# src/dazzle/core/ir/fk_graph.py
"""
Entity FK graph for scope rule validation.

Built at link time from entity specifications. Provides path resolution
and validation for PathCheck predicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.domain import EntitySpec


@dataclass(frozen=True)
class FKEdge:
    """A foreign key edge in the entity graph."""

    from_entity: str
    fk_field: str  # e.g., "school_id"
    to_entity: str  # e.g., "School"


@dataclass(frozen=True)
class PathStep:
    """One resolved step in a FK path traversal."""

    from_entity: str
    fk_field: str
    target_entity: str
    terminal_field: str | None = None  # Set on the last step


@dataclass
class FKGraph:
    """Directed graph of FK relationships between entities."""

    _edges: dict[str, list[FKEdge]] = field(default_factory=dict)
    _fields: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_entities(cls, entities: list[EntitySpec]) -> FKGraph:
        graph = cls()
        for entity in entities:
            entity_fields: set[str] = set()
            for f in entity.fields:
                entity_fields.add(f.name)
                kind = f.type.kind
                kind_val = kind.value if hasattr(kind, "value") else str(kind)
                if kind_val in ("ref", "belongs_to") and f.type.ref_entity:
                    edge = FKEdge(
                        from_entity=entity.name,
                        fk_field=f.name,
                        to_entity=f.type.ref_entity,
                    )
                    graph._edges.setdefault(entity.name, []).append(edge)
            graph._fields[entity.name] = entity_fields
        return graph

    def entity_names(self) -> set[str]:
        return set(self._fields.keys())

    def has_edge(self, entity: str, fk_field: str) -> bool:
        for edge in self._edges.get(entity, []):
            if edge.fk_field == fk_field:
                return True
        return False

    def resolve_target(self, entity: str, fk_field: str) -> str | None:
        for edge in self._edges.get(entity, []):
            if edge.fk_field == fk_field:
                return edge.to_entity
        return None

    def field_exists(self, entity: str, field_name: str) -> bool:
        return field_name in self._fields.get(entity, set())

    def resolve_segment(self, entity: str, segment: str) -> tuple[str, str]:
        """Resolve a single path segment to (fk_field, target_entity).

        Accepts both FK field names (school_id) and relation names (school).
        Raises ValueError if segment cannot be resolved.
        """
        # Try exact FK field match
        target = self.resolve_target(entity, segment)
        if target:
            return segment, target

        # Try relation name → FK field (append _id)
        fk_candidate = f"{segment}_id"
        target = self.resolve_target(entity, fk_candidate)
        if target:
            return fk_candidate, target

        raise ValueError(
            f"Invalid path: entity '{entity}' has no FK '{segment}' "
            f"(tried '{segment}' and '{fk_candidate}')"
        )

    def resolve_path(self, entity: str, path: list[str]) -> list[PathStep]:
        """Resolve a full dotted path to a list of PathSteps.

        The last segment is the terminal comparison field on the final entity.
        All preceding segments must be FK relationships.
        """
        if len(path) < 2:
            raise ValueError("Path must have at least 2 segments (relation + field)")

        steps: list[PathStep] = []
        current_entity = entity

        # All segments except the last are FK traversals
        for segment in path[:-1]:
            fk_field, target = self.resolve_segment(current_entity, segment)
            steps.append(PathStep(
                from_entity=current_entity,
                fk_field=fk_field,
                target_entity=target,
            ))
            current_entity = target

        # Last segment is the terminal field on the final entity
        terminal = path[-1]
        if not self.field_exists(current_entity, terminal):
            # Try with _id suffix for relation-style naming
            if self.field_exists(current_entity, f"{terminal}_id"):
                terminal = f"{terminal}_id"
            else:
                raise ValueError(
                    f"Invalid path: entity '{current_entity}' has no field '{terminal}'"
                )

        # Annotate the last step with the terminal field
        if steps:
            last = steps[-1]
            steps[-1] = PathStep(
                from_entity=last.from_entity,
                fk_field=last.fk_field,
                target_entity=last.target_entity,
                terminal_field=terminal,
            )
        else:
            raise ValueError("Path resolution produced no steps")

        return steps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_fk_graph.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/fk_graph.py tests/unit/test_fk_graph.py
git commit -m "feat(ir): add FK graph for scope path validation (#556)"
```

---

### Task 3: Predicate Compiler

Compile predicate trees to parameterised SQL WHERE fragments.

**Files:**
- Create: `src/dazzle_back/runtime/predicate_compiler.py`
- Test: `tests/unit/test_predicate_compiler.py`

- [ ] **Step 1: Write tests for SQL compilation of each predicate type**

```python
# tests/unit/test_predicate_compiler.py
"""Tests for predicate tree → SQL compilation."""
import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

pytest.importorskip("fastapi")

from dazzle.core.ir.fk_graph import FKGraph, FKEdge
from dazzle_back.runtime.predicate_compiler import compile_predicate


def _simple_graph() -> FKGraph:
    """Graph: Feedback -manuscript_id-> Manuscript -student_id-> Student."""
    graph = FKGraph()
    graph._edges = {
        "Feedback": [FKEdge("Feedback", "manuscript_id", "Manuscript")],
        "Manuscript": [
            FKEdge("Manuscript", "student_id", "Student"),
            FKEdge("Manuscript", "assessment_event_id", "AssessmentEvent"),
        ],
        "AssessmentEvent": [FKEdge("AssessmentEvent", "school_id", "School")],
    }
    graph._fields = {
        "Feedback": {"id", "manuscript_id", "content"},
        "Manuscript": {"id", "student_id", "assessment_event_id", "title"},
        "AssessmentEvent": {"id", "school_id", "name"},
        "Student": {"id", "name"},
        "School": {"id", "name"},
    }
    return graph


class TestColumnCheck:
    def test_eq(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"status" = %s' in sql
        assert params == ["active"]

    def test_ne(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.NE, value=ValueRef(literal="archived"))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"status" != %s' in sql

    def test_null(self) -> None:
        p = ColumnCheck(field="deleted_at", op=CompOp.IS, value=ValueRef(literal_null=True))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"deleted_at" IS NULL' in sql
        assert params == []


class TestUserAttrCheck:
    def test_simple(self) -> None:
        p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
        sql, params = compile_predicate(p, "Teacher", _simple_graph())
        assert '"school_id" = %s' in sql
        # Params contain a UserAttrRef marker that the route handler resolves
        # at request time via _resolve_user_attribute(attr_name, auth_context).
        assert len(params) == 1
        from dazzle_back.runtime.predicate_compiler import UserAttrRef
        assert isinstance(params[0], UserAttrRef)
        assert params[0].attr_name == "school"


class TestPathCheck:
    def test_depth_1(self) -> None:
        p = PathCheck(
            path=["manuscript", "student_id"],
            op=CompOp.EQ,
            value=ValueRef(current_user=True),
        )
        sql, params = compile_predicate(p, "Feedback", _simple_graph())
        assert '"manuscript_id" IN' in sql
        assert '"Manuscript"' in sql
        assert '"student_id"' in sql

    def test_depth_2(self) -> None:
        p = PathCheck(
            path=["manuscript", "assessment_event", "school_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="school"),
        )
        sql, params = compile_predicate(p, "Feedback", _simple_graph())
        assert '"manuscript_id" IN' in sql
        assert '"assessment_event_id" IN' in sql
        assert '"AssessmentEvent"' in sql
        assert '"school_id"' in sql


class TestExistsCheck:
    def test_exists(self) -> None:
        p = ExistsCheck(
            target_entity="AgentAssignment",
            bindings=[
                ExistsBinding(junction_field="agent", target="current_user"),
                ExistsBinding(junction_field="contact", target="id"),
            ],
        )
        sql, params = compile_predicate(p, "Contact", _simple_graph())
        assert "EXISTS" in sql
        assert "NOT" not in sql

    def test_not_exists(self) -> None:
        p = ExistsCheck(
            target_entity="BlockList",
            bindings=[
                ExistsBinding(junction_field="user", target="current_user"),
                ExistsBinding(junction_field="resource", target="id"),
            ],
            negated=True,
        )
        sql, params = compile_predicate(p, "Resource", _simple_graph())
        assert "NOT EXISTS" in sql


class TestBoolComposite:
    def test_and(self) -> None:
        left = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        right = ColumnCheck(field="archived", op=CompOp.EQ, value=ValueRef(literal=False))
        p = BoolComposite(op=BoolOp.AND, children=[left, right])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "AND" in sql
        assert len(params) == 2

    def test_or(self) -> None:
        left = UserAttrCheck(field="owner", op=CompOp.EQ, user_attr="entity_id")
        right = UserAttrCheck(field="creator", op=CompOp.EQ, user_attr="entity_id")
        p = BoolComposite(op=BoolOp.OR, children=[left, right])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "OR" in sql

    def test_not(self) -> None:
        inner = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived"))
        p = BoolComposite(op=BoolOp.NOT, children=[inner])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "NOT" in sql


class TestTerminals:
    def test_tautology(self) -> None:
        sql, params = compile_predicate(Tautology(), "Task", _simple_graph())
        assert sql == ""
        assert params == []

    def test_contradiction(self) -> None:
        sql, params = compile_predicate(Contradiction(), "Task", _simple_graph())
        assert "FALSE" in sql
        assert params == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_predicate_compiler.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement predicate compiler**

Create `src/dazzle_back/runtime/predicate_compiler.py` with `compile_predicate()` function that pattern-matches on predicate kind and emits parameterised SQL. Use `quote_identifier` from `query_builder.py` for safe identifier quoting.

Key implementation points:
- `ColumnCheck` → `"field" op %s` with NULL handling for IS/IS_NOT
- `UserAttrCheck` → `"field" op %s` (value resolved at call site from auth context)
- `PathCheck` → nested `IN (SELECT "id" FROM ...)` subqueries, inside-out algorithm per spec
- `ExistsCheck` → `[NOT] EXISTS (SELECT 1 FROM ... WHERE ...)` with binding resolution
- `BoolComposite` → `(child) AND/OR (child)` or `NOT (child)`
- `Tautology` → empty string (no WHERE clause)
- `Contradiction` → `FALSE`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_predicate_compiler.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/predicate_compiler.py tests/unit/test_predicate_compiler.py
git commit -m "feat(runtime): predicate compiler — ScopePredicate to SQL (#556)"
```

---

### Task 4: ConditionExpr → ScopePredicate Converter

Convert existing scope-context `ConditionExpr` trees (parser output) to `ScopePredicate` trees (validated algebra), using the FK graph.

**Files:**
- Create: `src/dazzle/core/ir/predicate_builder.py`
- Test: `tests/unit/test_predicate_builder.py`

- [ ] **Step 1: Write tests for ConditionExpr → ScopePredicate conversion**

Test cases should cover:
- Simple comparison `field = "value"` → `ColumnCheck`
- `field = current_user` → `UserAttrCheck(user_attr="entity_id")`
- `field = current_user.school` → `UserAttrCheck(user_attr="school")`
- Dotted left side `manuscript.student_id = current_user` → `PathCheck`
- `via JunctionEntity(...)` → `ExistsCheck`
- `via JunctionEntity(...) with negated=True` → `ExistsCheck(negated=True)`
- AND compound → `BoolComposite(AND, [...])`
- OR compound → `BoolComposite(OR, [...])`
- `condition=None` (scope: all) → `Tautology`
- Role check in scope → raises `ValueError`
- Grant check in scope → raises `ValueError`

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_predicate_builder.py -v`

- [ ] **Step 3: Implement converter**

Create `src/dazzle/core/ir/predicate_builder.py` with:
```python
def build_scope_predicate(
    condition: ConditionExpr | None,
    entity_name: str,
    fk_graph: FKGraph,
) -> ScopePredicate:
```

Walk the `ConditionExpr` tree and emit the corresponding `ScopePredicate`. Detect dotted fields (containing `.`) and route to `PathCheck`. Detect `current_user` values and route to `UserAttrCheck`. Reject role checks and grant checks with clear error messages.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_predicate_builder.py -v`

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/predicate_builder.py tests/unit/test_predicate_builder.py
git commit -m "feat(ir): ConditionExpr → ScopePredicate converter (#556)"
```

---

### Task 5: Wire FK Graph into Linker and ScopeRule

Build the FK graph during linking and attach compiled `ScopePredicate` trees to scope rules.

**Files:**
- Modify: `src/dazzle/core/linker.py`
- Modify: `src/dazzle/core/ir/domain.py` (add `predicate` field to `ScopeRule`)
- Modify: `src/dazzle/core/ir/appspec.py` (add `fk_graph` field to `AppSpec`)
- Test: `tests/unit/test_scope_rules.py` (extend existing)

- [ ] **Step 1: Write failing tests that verify linking populates predicates**

Test that after parsing and linking a DSL with scope rules, the `ScopeRule.predicate` field is populated with the correct predicate type and the `AppSpec.fk_graph` is present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_rules.py -v -k predicate`
Expected: FAIL — `predicate` field doesn't exist yet on `ScopeRule`.

- [ ] **Step 3: Add `predicate` to `ScopeRule` and `fk_graph` to `AppSpec`**

In `domain.py`, add to `ScopeRule`:
```python
predicate: ScopePredicate | None = None  # Compiled at link time
```

In `appspec.py`, add to `AppSpec`:
```python
fk_graph: FKGraph | None = None  # Built at link time
```

Both with appropriate imports.

- [ ] **Step 4: Wire FK graph building into linker**

In `src/dazzle/core/linker.py` `build_appspec()`, after merging fragments:
1. Build `FKGraph.from_entities(appspec.domain.entities)`
2. For each entity's scope rules, call `build_scope_predicate(rule.condition, entity.name, fk_graph)` and attach to `rule.predicate`
3. Store `fk_graph` on the `AppSpec`

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: All pass. Existing scope tests should continue to work since `predicate` is additive.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(linker): build FK graph and compile scope predicates at link time (#556)"
```

---

### Task 6: Replace Filter Pipeline with Predicate Compiler

Replace `_extract_condition_filters` and filter-dict pipeline in the route generator with `compile_predicate`.

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py`
- Modify: `tests/unit/test_scope_via.py`
- Modify: `tests/unit/test_dotted_scope_path.py`
- Modify: `tests/unit/test_cedar_row_filters.py`

- [ ] **Step 1: Update `_resolve_scope_filters` to use predicate compiler**

Replace the current `_resolve_scope_filters` body. Instead of calling `_extract_condition_filters` to build a filter dict, use the pre-compiled `ScopeRule.predicate` and call `compile_predicate()` to get SQL + params. Return the SQL fragment and params in a form the repository can consume.

Define a new return type or convention for passing compiled SQL predicates to the repository layer (e.g., a `__scope_sql` key in the filters dict as a transitional step, or modify `repository.list()` to accept a `scope_sql` parameter).

- [ ] **Step 2: Update existing tests**

Update `test_scope_via.py`, `test_dotted_scope_path.py`, and `test_cedar_row_filters.py` to work with the new predicate-based pipeline. Parser-level tests (DSL → IR) should be largely unchanged. Runtime tests that asserted filter-dict contents should assert SQL output instead.

- [ ] **Step 3: Remove deprecated functions**

Remove from `route_generator.py`:
- `_extract_condition_filters()`
- `_build_fk_path_subquery()`
- `_build_via_subquery()`
- `_extract_cedar_row_filters()` (the legacy path)
- Post-fetch OR filtering in `_list_handler_body`

Also remove `ref_targets` parameter added in #556 — the FK graph supersedes it.

- [ ] **Step 4: Clean up query_builder.py**

Remove or simplify filter-dict magic key parsing in `query_builder.py` — the `__in_subquery`, `__ne`, `__gt` dispatch logic is no longer needed for scope filters. Keep only what's needed for user-facing query parameter filtering (e.g., `?filter[status]=active` from URL params).

- [ ] **Step 5: Add runtime startup assertion**

In the route generator or server startup, add a check that compiles all scope predicates to SQL and verifies the output is non-empty and parameter counts are consistent. This is the belt-and-suspenders layer from the spec (Section 3, "Runtime assertions at startup").

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: All pass with updated tests.

- [ ] **Step 7: Run mypy**

Run: `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'`
Expected: No new errors.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/query_builder.py tests/unit/test_scope_via.py tests/unit/test_dotted_scope_path.py tests/unit/test_cedar_row_filters.py
git commit -m "refactor: replace filter-dict pipeline with predicate compiler (#556)"
```

---

### Task 7: Parser Extensions — `not via` and `not (...)`

Add `not via` (negated EXISTS) and `not (expr)` (general negation) to the scope condition parser.

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py`
- Modify: `src/dazzle/core/ir/conditions.py` (add `negated` to `ViaCondition`)
- Modify: `docs/reference/grammar.md` (document new syntax)
- Test: `tests/unit/test_scope_via.py` (extend)

- [ ] **Step 0: Update grammar reference**

Update `docs/reference/grammar.md` to document:
- `not via <Entity>(...)` syntax for negated EXISTS
- `not (...)` parenthesised negation in scope conditions
- depth-N path segments in scope conditions (e.g., `manuscript.assessment_event.school_id`)

- [ ] **Step 1: Write parser tests for `not via` and `not (...)`**

```python
def test_not_via_parsed() -> None:
    """not via BlockList(...) parses to ViaCondition with negated=True."""
    dsl = """
    module test
    app test_app "Test"
    entity Resource "Resource":
      id: uuid pk
      name: str(200)
      scope:
        list: not via BlockList(user = current_user, resource = id)
          for: user
    """
    # Parse and verify ViaCondition.negated == True
    ...

def test_not_parenthesised() -> None:
    """not (status = archived) parses as negated condition."""
    ...
```

- [ ] **Step 2: Add `negated` field to `ViaCondition`**

In `conditions.py`:
```python
class ViaCondition(BaseModel):
    junction_entity: str
    bindings: list[ViaBinding]
    negated: bool = False  # True for "not via"
```

- [ ] **Step 3: Update parser to handle `not via` and `not (...)`**

In `entity.py` scope condition parsing, check for `TokenType.NOT` before `TokenType.VIA` and before `TokenType.LPAREN`. Set `negated=True` on the resulting `ViaCondition`, or wrap the parsed condition in a negation `ConditionExpr`.

- [ ] **Step 4: Update predicate builder to handle negated via**

In `predicate_builder.py`, when converting a `ViaCondition` with `negated=True`, emit `ExistsCheck(negated=True)`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_scope_via.py tests/unit/test_predicate_builder.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(parser): add not via and not (...) scope syntax (#556)"
```

---

### Task 8: Validator Integration

Add predicate validation to `dazzle validate` — verify all scope predicate paths resolve against the FK graph.

**Files:**
- Modify: `src/dazzle/core/validator.py`
- Test: extend existing validator tests

- [ ] **Step 1: Add validation that reports invalid scope paths**

In the validator, after the linker builds predicates, walk each `ScopePredicate` tree and verify:
- `ColumnCheck.field` exists on the entity
- `PathCheck.path` resolves through the FK graph (already validated at build time, but double-check here)
- `ExistsCheck.target_entity` exists
- No `RoleCheck` or `GrantCheck` in scope rules

- [ ] **Step 2: Write test for invalid scope path detection**

```python
def test_validate_detects_invalid_scope_path() -> None:
    """Scope rule referencing non-existent FK should produce validation error."""
    dsl = """
    module test
    app test_app "Test"
    entity Task "Task":
      id: uuid pk
      title: str(200)
      scope:
        list: nonexistent.field = current_user
          for: user
    """
    # Should produce a validation error, not silently pass
    ...
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(validator): validate scope predicates against FK graph (#556)"
```

---

### Task 9: Revalidate Example Apps and Clean Up

Run all example apps through the new validation, update any that need changes, and clean up deprecated code.

**Files:**
- Modify: example apps if needed
- Remove: deprecated filter-dict code paths (if not already removed in Task 6)

- [ ] **Step 1: Run `dazzle validate` on all example apps**

```bash
for dir in examples/*/; do
  echo "=== $dir ==="
  (cd "$dir" && dazzle validate 2>&1) || echo "FAILED: $dir"
done
```

Fix any validation errors in example DSL files.

- [ ] **Step 2: Run full test suite including integration tests**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: All pass.

- [ ] **Step 3: Run mypy on all modified packages**

Run: `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject' && mypy src/dazzle_back/ --ignore-missing-imports`
Expected: No errors.

- [ ] **Step 4: Run lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

- [ ] **Step 5: Update CHANGELOG.md**

Add entries under `### Changed` and `### Removed`:
- Changed: Scope rules compile to formal ScopePredicate algebra with FK graph validation
- Changed: OR conditions in scope rules now compile to SQL OR (previously post-fetch filtered)
- Added: `not via` syntax for NOT EXISTS scope rules
- Added: `not (...)` parenthesised negation in scope rules
- Added: depth-N FK path traversal in scope rules (previously depth-1 only)
- Removed: `_extract_condition_filters`, `_build_via_subquery`, `_build_fk_path_subquery`
- Removed: filter-dict magic key conventions (`__in_subquery`, `__ne`, etc.)
- Removed: post-fetch OR filtering

- [ ] **Step 6: Final commit**

```bash
git commit -m "chore: revalidate example apps, update CHANGELOG, clean up deprecated scope code (#556)"
```

---

### Task Dependency Order

```
Task 1 (IR types) → Task 2 (FK graph) → Task 3 (compiler)
                                              ↓
Task 7 (parser: not via, not (...)) → Task 4 (converter — needs ViaCondition.negated)
                                              ↓
                                        Task 5 (linker wiring)
                                              ↓
                                        Task 6 (replace pipeline)
                                              ↓
                                        Task 8 (validator)
                                              ↓
                                        Task 9 (cleanup + CHANGELOG + grammar docs)
```

Tasks 1-3 can be implemented independently. Task 7 (parser) must precede Task 4 because the converter needs `ViaCondition.negated` to build `ExistsCheck(negated=True)`. Task 5 integrates everything. Task 6 is the big switchover. Tasks 8-9 are finalization.
