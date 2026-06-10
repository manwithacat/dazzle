"""Typed IR for aggregate expressions.

Replaces the legacy regex-parsed string aggregates (`count(Entity where ...)`,
`avg(field)`, …) with a structured IR that every aggregate consumer reads.

See ADR-0024 (no regex for DSL grammar) and
``dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md`` for the motivation
and migration sequencing.

Five legacy consumers migrate to ``AggregateRef``:

- ``WorkspaceRegion.aggregates``: ``dict[str, str]`` → ``dict[str, AggregateRef]``
- ``OverlaySeriesSpec.aggregate_expr``: ``str`` → ``aggregate: AggregateRef``
- ``PipelineStageSpec.value`` / ``.progress``: ``str`` → ``AggregateRef | str``
  (preserves the literal-string overlay for descriptive flow stages)
- ``ActionCardSpec.count_aggregate``: ``str`` → ``count: AggregateRef | None``
- ``LensAggregatePrimary.aggregate``: ``str`` → ``aggregate: AggregateRef``

The DSL surface syntax does not change. The parser desugars
``count(Entity)`` / ``avg(field)`` / ``avg(Entity.column)`` into typed IR.

L3 (#1152): nested expression form populates ``AggregateRef.expression``
instead of ``column``. Expressions support column refs, number literals,
casts, binary arithmetic, and a whitelist of safe SQL functions. The
column shape stays for the trivial case so simple aggregates remain
cheap to compile and reason about.
"""

from __future__ import annotations  # required: forward reference

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .conditions import ConditionExpr

AggregateFunc = Literal["count", "sum", "avg", "min", "max"]

# Whitelisted cast targets. The runtime compiler emits these verbatim into
# the SQL, so the set is closed (Postgres types only). Adding a new entry
# is a deliberate ADR-class decision — not a parser ergonomics tweak.
CastTarget = Literal["float", "int", "numeric", "text"]

# Whitelisted binary operators. Same closed-set rationale as CastTarget.
# Renamed from BinaryOp to avoid clashing with ``expressions.BinaryOp``
# (a StrEnum used by predicate compilation).
AggregateBinaryOp = Literal["+", "-", "*", "/"]

# Whitelisted aggregate-expression function calls. Each function must have
# a known SQL surface and arity validated by the IR. Keep this tight; the
# expression IR is for arithmetic on aggregated columns, not arbitrary
# SQL composition.
AggregateFunctionName = Literal["nullif", "coalesce", "abs"]

# Arity for each whitelisted function — checked in the IR validator so
# the runtime compiler can trust the shape.
_FUNCTION_ARITY: dict[str, tuple[int, int | None]] = {
    "nullif": (2, 2),
    "coalesce": (1, None),  # variadic — at least 1 arg
    "abs": (1, 1),
}


class AggregateExpr(BaseModel):
    """A nested expression inside an L3 aggregate.

    Tagged-union pattern: exactly one variant is populated per node, and
    the model validator enforces that. The five variants:

    1. **Column reference** — ``score`` or ``MarkingResult.score``.
       Populate ``column_name`` (required) and optionally ``column_entity``
       (cross-entity prefix). All column refs within a single
       :class:`AggregateRef.expression` must reference the same entity
       (validated at parse time, not at IR construction).

    2. **Number literal** — ``0``, ``0.5``, ``-1``. Populate
       ``number_literal``. Compiled to a parametrised bind, never
       interpolated into the SQL string.

    3. **Cast** — ``score::float``. Populate ``cast_target`` and
       ``cast_operand``. The target is a whitelisted Postgres type.

    4. **Binary op** — ``a / b``. Populate ``binary_op``, ``binary_left``,
       ``binary_right``. Operators are arithmetic only; comparisons live
       in :class:`ConditionExpr` and aren't valid inside an aggregate
       expression.

    5. **Function call** — ``nullif(a, b)``. Populate ``function_name``
       and ``function_args``. Functions are whitelisted with known
       arities; the validator enforces both.

    All field combinations not matching one of those variants raise
    :class:`pydantic.ValidationError` at construction.
    """

    column_entity: str | None = None
    column_name: str | None = None

    number_literal: int | float | None = None

    cast_target: CastTarget | None = None
    cast_operand: AggregateExpr | None = None

    binary_op: AggregateBinaryOp | None = None
    binary_left: AggregateExpr | None = None
    binary_right: AggregateExpr | None = None

    function_name: AggregateFunctionName | None = None
    function_args: tuple[AggregateExpr, ...] | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_variant(self) -> AggregateExpr:
        is_column = self.column_name is not None
        is_number = self.number_literal is not None
        is_cast = self.cast_target is not None
        is_binary = self.binary_op is not None
        is_function = self.function_name is not None

        populated = sum([is_column, is_number, is_cast, is_binary, is_function])
        if populated == 0:
            raise ValueError(
                "AggregateExpr must populate exactly one variant "
                "(column ref, number literal, cast, binary op, or function call)"
            )
        if populated > 1:
            raise ValueError(
                "AggregateExpr variants are mutually exclusive — got multiple populated at once"
            )

        if is_column:
            if self.column_name and "." in self.column_name:
                raise ValueError(
                    f"column_name must be a single identifier, not a dotted "
                    f"path: {self.column_name!r}. Use column_entity= for "
                    f"cross-entity refs."
                )
        elif is_cast:
            if self.cast_operand is None:
                raise ValueError("cast requires cast_operand")
        elif is_binary:
            if self.binary_left is None or self.binary_right is None:
                raise ValueError("binary op requires both binary_left and binary_right")
        elif is_function:
            if self.function_args is None or len(self.function_args) == 0:
                raise ValueError(f"function {self.function_name!r} requires at least one argument")
            # is_function == True implies self.function_name is set; narrow
            # for the dict lookup below.
            assert self.function_name is not None
            arity_min, arity_max = _FUNCTION_ARITY[self.function_name]
            n = len(self.function_args)
            if n < arity_min or (arity_max is not None and n > arity_max):
                expected = (
                    f"{arity_min}"
                    if arity_max == arity_min
                    else f"{arity_min}+"
                    if arity_max is None
                    else f"{arity_min}..{arity_max}"
                )
                raise ValueError(
                    f"function {self.function_name!r} expects {expected} arguments, got {n}"
                )
        return self

    @property
    def is_column_ref(self) -> bool:
        return self.column_name is not None

    @property
    def is_number_literal(self) -> bool:
        return self.number_literal is not None

    @property
    def is_cast(self) -> bool:
        return self.cast_target is not None

    @property
    def is_binary_op(self) -> bool:
        return self.binary_op is not None

    @property
    def is_function_call(self) -> bool:
        return self.function_name is not None


class AggregateRef(BaseModel):
    """A single aggregate computation.

    Four shapes covered by named fields rather than func-disambiguation:

    1. **Row count on an entity.** ``count(Entity)`` —
       ``func="count", entity="Entity", column=None``.
       Routes to ``Repository.list(filters=...).total``.

    2. **Source-relative scalar.** ``avg(column)`` —
       ``func="avg", entity=None, column="column"``.
       Routes to ``source_repo.aggregate(measures={"x": "avg:column"})``.
       The enclosing region's source entity supplies the repository.

    3. **Cross-entity scalar.** ``avg(Entity.column)`` —
       ``func="avg", entity="Entity", column="column"``.
       Routes to ``repositories["Entity"].aggregate(...)``. This shape was
       unrepresentable in the legacy regex grammar; cross-entity aggregates
       were the original driver for #1144 Gap 1 phase 2.

    4. **L3 expression.** ``avg(score::float / nullif(max_score, 0))`` —
       ``func="avg", expression=AggregateExpr(...)``. ``column`` is None;
       ``entity`` is optional (cross-entity expressions are valid when
       every column ref inside ``expression`` shares the same prefix).
       Compiled to safe SQL with parametrised literals — see
       :func:`dazzle.back.runtime.aggregate_expression.compile_aggregate_expression`.

    The ``where:`` clause is a structured :class:`ConditionExpr` — the same
    type scope rules and view filters compile to — not a string. The legacy
    ``parse_aggregate_where`` indirection retires once every consumer reads
    typed ``where``.

    Invariants enforced by Pydantic at construction:

    - ``count`` requires either ``entity`` or no positional argument
      (``count(Entity)`` or — once a parent context is available —
      a bare ``count`` over the source). ``count`` rejects both ``column``
      and ``expression``.
    - ``sum`` / ``avg`` / ``min`` / ``max`` require exactly one of
      ``column`` or ``expression``. ``entity`` is optional.
    - ``column`` must be a single field name (no dotted paths). Multi-hop
      FK traversals are deferred to a future ``path`` field.
    """

    func: AggregateFunc
    entity: str | None = None
    column: str | None = None
    expression: AggregateExpr | None = None
    where: ConditionExpr | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_func_shape(self) -> AggregateRef:
        if self.func == "count":
            if self.column is not None:
                raise ValueError(
                    f"count() does not take a column (got {self.column!r}); "
                    "use count(Entity) for row-count or count(Entity where ...)"
                )
            if self.expression is not None:
                raise ValueError(
                    "count() does not take an expression; "
                    "use count(Entity) for row-count or count(Entity where ...)"
                )
        else:
            has_column = self.column is not None
            has_expression = self.expression is not None
            if not has_column and not has_expression:
                raise ValueError(
                    f"{self.func}() requires a column or expression "
                    f"(e.g. avg(score), avg(Entity.score), "
                    f"avg(score / max_score))"
                )
            if has_column and has_expression:
                raise ValueError(f"{self.func}() takes a column OR an expression, not both")
        if self.column is not None and "." in self.column:
            raise ValueError(
                f"column must be a single field name, not a dotted path: "
                f"{self.column!r}. Use entity= for cross-entity aggregates."
            )
        return self

    @property
    def is_source_relative(self) -> bool:
        """True when the aggregate runs against the enclosing region's
        source entity (no explicit ``entity:`` declared). Used by the
        runtime dispatcher to pick the right repository.
        """
        return self.entity is None

    @property
    def is_expression(self) -> bool:
        """True when this aggregate uses the L3 nested-expression form."""
        return self.expression is not None


# ---------------------------------------------------------------------------
# Derived metrics (#1359)
# ---------------------------------------------------------------------------

# Whitelisted functions for derived-metric expressions. Evaluated in Python
# over already-aggregated scalars (NOT compiled to SQL), so the set is closed
# and arity-checked here exactly like AggregateExpr's functions.
DerivedFunctionName = Literal["round", "abs", "nullif", "coalesce"]

_DERIVED_FUNCTION_ARITY: dict[str, tuple[int, int | None]] = {
    "round": (1, 2),
    "abs": (1, 1),
    "nullif": (2, 2),
    "coalesce": (1, None),
}


class DerivedMetricExpr(BaseModel):
    """A node in a derived-metric expression tree (#1359).

    Tagged union, mirroring :class:`AggregateExpr`'s discipline. Variants:

    1. **Metric reference** — a name declared *earlier in the same
       ``aggregate:`` block* (``done``, ``total``). Populate ``metric_name``.
    2. **Number literal** — ``100``, ``0.5``. Populate ``number_literal``.
    3. **Binary op** — ``done / total``. Arithmetic only.
    4. **Function call** — ``round(x, 1)``. Whitelisted, arity-checked.

    Derived metrics are evaluated in Python over the aggregated scalar
    results AFTER the scope-filtered aggregate queries ran — they add zero
    queries and cannot touch rows, so the one-query-per-chart scope-safety
    contract (docs/reference/reports.md) is preserved by construction.
    """

    metric_name: str | None = None

    number_literal: int | float | None = None

    binary_op: AggregateBinaryOp | None = None
    binary_left: DerivedMetricExpr | None = None
    binary_right: DerivedMetricExpr | None = None

    function_name: DerivedFunctionName | None = None
    function_args: tuple[DerivedMetricExpr, ...] | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_variant(self) -> DerivedMetricExpr:
        is_metric = self.metric_name is not None
        is_number = self.number_literal is not None
        is_binary = self.binary_op is not None
        is_function = self.function_name is not None

        populated = sum([is_metric, is_number, is_binary, is_function])
        if populated == 0:
            raise ValueError(
                "DerivedMetricExpr must populate exactly one variant "
                "(metric ref, number literal, binary op, or function call)"
            )
        if populated > 1:
            raise ValueError(
                "DerivedMetricExpr variants are mutually exclusive — got multiple at once"
            )

        if is_binary:
            if self.binary_left is None or self.binary_right is None:
                raise ValueError("binary op requires both binary_left and binary_right")
        elif is_function:
            if not self.function_args:
                raise ValueError(f"function {self.function_name!r} requires arguments")
            assert self.function_name is not None
            arity_min, arity_max = _DERIVED_FUNCTION_ARITY[self.function_name]
            n = len(self.function_args)
            if n < arity_min or (arity_max is not None and n > arity_max):
                raise ValueError(
                    f"function {self.function_name!r} expects "
                    f"{arity_min}{'' if arity_max == arity_min else '+'} arguments, got {n}"
                )
        return self

    def referenced_metrics(self) -> tuple[str, ...]:
        """All metric names referenced anywhere in this expression tree."""
        if self.metric_name is not None:
            return (self.metric_name,)
        refs: list[str] = []
        for child in (self.binary_left, self.binary_right):
            if child is not None:
                refs.extend(child.referenced_metrics())
        if self.function_args:
            for arg in self.function_args:
                refs.extend(arg.referenced_metrics())
        return tuple(refs)


class DerivedMetric(BaseModel):
    """A metric computed from other metrics in the same ``aggregate:`` block.

    #1359: ``completion_rate: round(done / total * 100)`` — arithmetic over
    previously-declared metric names. The parser validates every referenced
    name was declared earlier in the block; the runtime evaluates the tree
    in Python over the aggregated results (division by zero → 0).
    """

    expression: DerivedMetricExpr

    model_config = ConfigDict(frozen=True)

    def referenced_metrics(self) -> tuple[str, ...]:
        return self.expression.referenced_metrics()
