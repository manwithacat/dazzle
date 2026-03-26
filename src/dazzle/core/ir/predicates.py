"""
Scope predicate algebra types for DAZZLE IR.

This module provides a formal predicate algebra to represent row-level security
(scope) rules as structured IR nodes, replacing ad-hoc filter dictionaries.

The algebra supports:
  - Column comparisons (ColumnCheck)
  - User attribute comparisons (UserAttrCheck)
  - Multi-hop path comparisons (PathCheck)
  - Subquery existence tests (ExistsCheck)
  - Boolean composites with AND / OR / NOT (BoolComposite)
  - Logical constants (Tautology, Contradiction)

BoolComposite.make() enforces algebraic identity and absorption laws at
construction time so callers never need to canonicalize manually.

ScopePredicate is a Pydantic discriminated union over all node types; use it
as the field type wherever a predicate tree is stored.
"""

from __future__ import annotations  # required: forward reference

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class CompOp(StrEnum):
    """Comparison operators for predicate expressions."""

    EQ = "="
    NEQ = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"


class BoolOp(StrEnum):
    """Boolean operators for combining predicates."""

    AND = "and"
    OR = "or"
    NOT = "not"


# ---------------------------------------------------------------------------
# Value reference
# ---------------------------------------------------------------------------


class ValueRef(BaseModel):
    """
    A value used on the right-hand side of a predicate comparison.

    Exactly one of the four fields should be set:
      - ``literal``      — a scalar Python value (str, int, float, bool)
      - ``current_user`` — True means "the authenticated user's PK"
      - ``user_attr``    — a named attribute on the current user (e.g. "org_id")
      - ``literal_null`` — True means the SQL NULL literal
    """

    literal: str | int | float | bool | None = None
    current_user: bool = False
    user_attr: str | None = None
    literal_null: bool = False

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# ExistsBinding
# ---------------------------------------------------------------------------


class ExistsBinding(BaseModel):
    """
    A single binding inside an EXISTS sub-query.

    Maps a field on the junction table to a target value:
      - ``junction_field`` — column name in the junction entity
      - ``target``         — "current_user", "current_user.<attr>", entity field
                             name, or "null"
      - ``operator``       — "=" or "!="
    """

    junction_field: str
    target: str
    operator: str = "="

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Predicate node types
# ---------------------------------------------------------------------------


class ColumnCheck(BaseModel):
    """
    Compare an entity column to a literal or reference value.

    Example DSL::

        status = "active"
        amount > 0
    """

    kind: Literal["column_check"] = "column_check"
    field: str
    op: CompOp
    value: ValueRef

    model_config = ConfigDict(frozen=True)


class UserAttrCheck(BaseModel):
    """
    Compare an entity column to an attribute on the current user.

    Example DSL::

        owner_id = current_user.id
        org_id = current_user.org_id
    """

    kind: Literal["user_attr_check"] = "user_attr_check"
    field: str
    op: CompOp
    user_attr: str

    model_config = ConfigDict(frozen=True)


class PathCheck(BaseModel):
    """
    Compare a multi-hop field path to a value (or user attribute).

    The ``path`` list encodes the traversal from the root entity to the target
    field, e.g. ``["project", "team", "org_id"]`` means
    ``entity.project.team.org_id``.

    A depth-1 path is equivalent to a ColumnCheck but typed as a path for
    uniform treatment in the compiler.
    """

    kind: Literal["path_check"] = "path_check"
    path: list[str]
    op: CompOp
    value: ValueRef

    model_config = ConfigDict(frozen=True)


class ExistsCheck(BaseModel):
    """
    An EXISTS (or NOT EXISTS) sub-query through a junction entity.

    Example DSL::

        via TeamMembership(user_id = current_user, team_id = id)

    When ``negated`` is True this becomes a NOT EXISTS check.
    """

    kind: Literal["exists_check"] = "exists_check"
    target_entity: str
    bindings: list[ExistsBinding]
    negated: bool = False

    model_config = ConfigDict(frozen=True)


class Tautology(BaseModel):
    """Logical constant TRUE — always matches every row."""

    kind: Literal["tautology"] = "tautology"

    model_config = ConfigDict(frozen=True)


class Contradiction(BaseModel):
    """Logical constant FALSE — never matches any row."""

    kind: Literal["contradiction"] = "contradiction"

    model_config = ConfigDict(frozen=True)


class BoolComposite(BaseModel):
    """
    A boolean combination of child predicates (AND, OR, or NOT).

    Use :meth:`make` instead of the constructor directly so that algebraic
    simplifications are applied at build time:

    - AND(x, Tautology)     → x
    - OR(x, Tautology)      → Tautology
    - AND(x, Contradiction) → Contradiction
    - OR(x, Contradiction)  → x
    - NOT(Tautology)        → Contradiction
    - NOT(Contradiction)    → Tautology
    - NOT(NOT(x))           → x  (double-negation elimination)
    """

    kind: Literal["bool_composite"] = "bool_composite"
    op: BoolOp
    children: list[ScopePredicate]

    model_config = ConfigDict(frozen=True)

    @staticmethod
    def make(op: BoolOp, children: list[ScopePredicate]) -> ScopePredicate:
        """
        Construct a BoolComposite with algebraic simplification.

        Returns the simplified predicate, which may be a leaf node rather than
        a BoolComposite when a simplification rule fires.
        """
        if op is BoolOp.NOT:
            assert len(children) == 1, "NOT takes exactly one child"
            child = children[0]
            # NOT(Tautology) → Contradiction
            if isinstance(child, Tautology):
                return Contradiction()
            # NOT(Contradiction) → Tautology
            if isinstance(child, Contradiction):
                return Tautology()
            # NOT(NOT(x)) → x
            if isinstance(child, BoolComposite) and child.op is BoolOp.NOT:
                return child.children[0]
            return BoolComposite(op=op, children=children)

        # AND / OR — scan children for identity/absorption elements
        result_children: list[ScopePredicate] = []
        for child in children:
            if op is BoolOp.AND:
                if isinstance(child, Contradiction):
                    return Contradiction()
                if isinstance(child, Tautology):
                    # Identity for AND — skip
                    continue
            elif op is BoolOp.OR:
                if isinstance(child, Tautology):
                    return Tautology()
                if isinstance(child, Contradiction):
                    # Identity for OR — skip
                    continue
            result_children.append(child)

        # All children were identities — return the identity constant
        if not result_children:
            return Tautology() if op is BoolOp.AND else Contradiction()

        # Exactly one meaningful child — unwrap
        if len(result_children) == 1:
            return result_children[0]

        return BoolComposite(op=op, children=result_children)


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

ScopePredicate = Annotated[
    ColumnCheck
    | UserAttrCheck
    | PathCheck
    | ExistsCheck
    | BoolComposite
    | Tautology
    | Contradiction,
    Field(discriminator="kind"),
]
"""
Pydantic discriminated union of all predicate node types.

Use this type for fields that store a predicate tree::

    class ScopeRule(BaseModel):
        predicate: ScopePredicate
"""

# Rebuild BoolComposite after ScopePredicate is defined so that the
# self-referential ``children: list[ScopePredicate]`` annotation resolves.
BoolComposite.model_rebuild()
