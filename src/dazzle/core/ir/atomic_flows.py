"""
Atomic-flow specification types for DAZZLE IR (#1228 Phase 3c).

An ``atomic`` block declares a multi-entity creation operation that
executes in a single DB transaction. All creates succeed or all roll
back — there is no partial state.

DSL keyword note: the issue proposal called this construct ``flow``,
but ``flow`` is already the E2E test construct (``flow.py`` in this
package). The user-facing alternative ``atomic`` was suggested in the
Q1 design question on #1228 — it's short, signals atomicity, and
doesn't collide.

IR class is ``AtomicFlowSpec`` rather than ``FlowSpec`` (also taken
by E2E flow tests).

Status at v0.71.177 (slice 3c.i): parsed into IR + validated; runtime
service + route generation lands in slices 3c.ii / 3c.iii.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .fields import FieldType
from .location import SourceLocation
from .predicates import CompOp, ScopePredicate


class FlowFieldValueKind(StrEnum):
    """Kinds of right-hand-side value an atomic-flow create can assign."""

    LITERAL = "literal"
    INPUT_REF = "input_ref"  # input.<name>
    ABOVE_REF = "above_ref"  # above.<EntityName>.<field>


class FlowFieldValue(BaseModel):
    """Right-hand-side value of a flow create's field assignment.

    Exactly one of the three slots is populated, keyed by ``kind``.

    - LITERAL: ``literal`` carries the value (string, int, float, bool).
    - INPUT_REF: ``input_name`` names a declared input.
    - ABOVE_REF: ``above_entity`` + ``above_field`` refer to a value
      produced by an earlier create in the same flow.
    """

    kind: FlowFieldValueKind
    literal: str | int | float | bool | None = None
    input_name: str | None = None
    above_entity: str | None = None
    above_field: str | None = None

    model_config = ConfigDict(frozen=True)


class FlowInput(BaseModel):
    """A typed input parameter for an atomic flow.

    Reuses the same ``FieldType`` shape as entity field declarations,
    so authoring is consistent (``str(200)``, ``ref Role``, ``date``,
    etc. all work).
    """

    name: str
    type: FieldType
    required: bool = False

    model_config = ConfigDict(frozen=True)


class FlowCreate(BaseModel):
    """A single create step within an atomic flow.

    Maps a target entity to a dict of field assignments. The order of
    steps within the flow is the order they execute in.
    """

    kind: Literal["create"] = "create"
    entity: str
    assignments: dict[str, FlowFieldValue]

    model_config = ConfigDict(frozen=True)


class FlowUpdate(BaseModel):
    """An update step within an atomic flow (#1313, ADR-0029).

    Targets an existing row of ``entity`` — selected by ``target`` (an
    ``input.<id>`` or ``above.<Entity>.id`` reference resolving to the
    row's primary key) — and applies ``assignments``. "End-dating" a row
    is just an update that sets the entity's temporal end column; there is
    no separate step kind (the single-`update`-kind grammar, ADR-0029).

    The executor resolves the target row, enforces ``scope: update:`` (source
    + destination, #1312) in-transaction, then issues the UPDATE (#1313).
    """

    kind: Literal["update"] = "update"
    entity: str
    target: FlowFieldValue
    assignments: dict[str, FlowFieldValue]

    model_config = ConfigDict(frozen=True)


# A step within an atomic flow — discriminated on ``kind`` so the parser /
# executor / validator can dispatch uniformly and steps keep declaration order.
# Named ``AtomicFlowStep`` (not ``FlowStep``) to avoid colliding with the E2E
# `flow` construct's pre-existing ``FlowStep`` (`FlowStepKind.SNAPSHOT`, ...).
AtomicFlowStep = Annotated[FlowCreate | FlowUpdate, Field(discriminator="kind")]


class FlowAuditMode(StrEnum):
    """How a flow's per-step audit fact is recorded (#1317, ADR-0029 invariant 5).

    - ``ASYNC`` (default): one ``allow`` fact per committed step is enqueued on
      the async ``AuditLogger`` *after* the flow commits (best-effort; dropped on
      queue overflow / crash before drain). The shipped #1313 slice-1e behaviour.
    - ``STRICT``: each committed step's audit row is written to the dedicated
      ``_dazzle_atomic_audit`` side-table on the flow's **own connection, inside
      the transaction**, so the audit commits or rolls back atomically with the
      mutation (no drop, no async-drainer race). The upgrade path for flows that
      need a guaranteed trail.
    """

    ASYNC = "async"
    STRICT = "strict"


class FlowAggregateFn(StrEnum):
    """Aggregate function in a flow-level invariant (#1318, ADR-0031)."""

    SUM = "sum"
    COUNT = "count"


class InvariantRhs(BaseModel):
    """Right-hand bound of a flow invariant: a literal OR an anchor-row field.

    Exactly one form is populated: ``literal`` for `= 0` / `<= 1000`; the
    ``anchor_input`` + ``anchor_field`` pair for `<= input.budget.total`.
    """

    literal: int | float | None = None
    anchor_input: str | None = None
    anchor_field: str | None = None

    model_config = ConfigDict(frozen=True)


class FlowInvariant(BaseModel):
    """A flow-level aggregate invariant (#1318, ADR-0031).

    Asserts ``<agg_fn>(<entity>.<field> where <filter>) <op> <rhs>`` holds at
    commit, else the whole flow rolls back. ``filter_predicate``,
    ``anchor_entity`` and ``anchor_input`` are ``None`` in raw parser output and
    filled in by the linker.

    ``raw_filter`` carries the parser-captured ``where`` filter terms — a
    conjunction (AND) of ``<column> = (input.<name> | literal)`` equalities — as
    a frozen tuple of ``(column, kind, value)`` triples where ``kind`` ∈
    {"input", "literal"}. The linker compiles these into ``filter_predicate``
    (a ``ScopePredicate``) in Task 4; until then it is the raw provenance the
    linker reads.
    """

    agg_fn: FlowAggregateFn
    entity: str
    field: str | None  # None only for COUNT
    filter_predicate: ScopePredicate | None
    anchor_entity: str | None
    anchor_input: str | None
    op: CompOp
    rhs: InvariantRhs
    raw_filter: tuple[tuple[str, str, str], ...] = ()
    location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class FlowFailureMode(StrEnum):
    """How the framework handles a create failure mid-flow."""

    ROLLBACK_ALL = "rollback_all"  # default + only option in 3c.i


class AtomicFlowSpec(BaseModel):
    """An atomic multi-entity mutation operation.

    All steps execute in a single DB transaction. ``above.<Entity>``
    references resolve to values produced by earlier steps in the flow;
    the framework executes them in declaration order. Steps may be
    ``create`` (FlowCreate) or ``update`` (FlowUpdate); the executor
    currently runs creates and stubs updates (slice 1a, ADR-0029).
    """

    name: str
    label: str
    intent: str | None = None
    permit_execute: list[str]  # role names allowed to execute the flow
    on_failure: FlowFailureMode = FlowFailureMode.ROLLBACK_ALL
    audit_mode: FlowAuditMode = FlowAuditMode.ASYNC  # #1317 — per-flow `audit:` opt-in
    inputs: list[FlowInput]
    steps: list[AtomicFlowStep]
    invariants: list[FlowInvariant] = []
    derived_step_order: list[int] | None = None
    """#1315 — execution order as indices into ``steps``, derived parent-before-child
    from the FK graph at link time for the **create-DAG family** (all-create, no
    same-entity repeat, no FK cycle). ``None`` ⇒ run ``steps`` in declared order
    (updates / same-entity / cyclic FKs, where order is temporal/semantic, not
    structural). Declared ``steps`` order is preserved either way (provenance +
    analysis); the executor consumes this when set."""
    location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
