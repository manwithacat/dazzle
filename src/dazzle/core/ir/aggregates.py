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
"""

from __future__ import annotations  # required: forward reference

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .conditions import ConditionExpr

AggregateFunc = Literal["count", "sum", "avg", "min", "max"]


class AggregateRef(BaseModel):
    """A single aggregate computation.

    Three shapes covered by named fields rather than func-disambiguation:

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

    The ``where:`` clause is a structured :class:`ConditionExpr` — the same
    type scope rules and view filters compile to — not a string. The legacy
    ``parse_aggregate_where`` indirection retires once every consumer reads
    typed ``where``.

    Invariants enforced by Pydantic at construction:

    - ``count`` requires either ``entity`` or no positional argument
      (``count(Entity)`` or — once a parent context is available —
      a bare ``count`` over the source).
    - ``sum`` / ``avg`` / ``min`` / ``max`` require ``column``. ``entity``
      is optional (cross-entity vs source-relative).
    - ``column`` must be a single field name (no dotted paths). Multi-hop
      FK traversals are deferred to a future ``path`` field.
    """

    func: AggregateFunc
    entity: str | None = None
    column: str | None = None
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
        else:
            if self.column is None:
                raise ValueError(
                    f"{self.func}() requires a column (e.g. avg(score), avg(Entity.score))"
                )
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
