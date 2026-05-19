"""Slice 3 / #1144 phase 2: ``compute_cohort_aggregate_primary`` integration.

The helper fires per-member ``Repository.aggregate`` calls for each
cohort source row, returning a dict[member_id, value]. Pre-Slice 3 the
runtime raised ``NotImplementedError``; phase 2 implements the no-via
case (direct FK from aggregated entity → source entity).

Phase 3 (junction-binding via:) is intentionally out of scope here —
when ``via:`` is set, the helper logs a warning and returns an empty
dict so cells render without values.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.back.runtime.workspace_region_computes import compute_cohort_aggregate_primary
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    ViaBinding,
    ViaCondition,
)
from dazzle.core.ir.workspaces import (
    CohortStripLens,
    LensAggregatePrimary,
)


def _make_aggregated_repo(per_member: dict[str, float]):
    """Mock an aggregated-entity repo whose ``aggregate()`` returns the
    value for the member id present in ``filters``."""

    spec = MagicMock()
    # Aggregated entity has a `student` FK to "StudentProfile" (source).
    student_field = MagicMock()
    student_field.name = "student"
    student_field.type = MagicMock()
    student_field.type.kind = "ref"
    student_field.type.ref_entity = "StudentProfile"
    other_field = MagicMock()
    other_field.name = "score"
    other_field.type = MagicMock()
    other_field.type.kind = "int"
    spec.fields = [student_field, other_field]

    repo = MagicMock()
    repo.entity_spec = spec

    async def _aggregate(*, dimensions, measures, filters=None, limit=1, measure_expressions=None):
        member_id = filters.get("student") if filters else None
        if member_id not in per_member:
            return []
        bucket = MagicMock()
        bucket.measures = {"primary": per_member[member_id]}
        return [bucket]

    repo.aggregate = AsyncMock(side_effect=_aggregate)
    return repo


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_direct_fk_per_member_dispatch() -> None:
    """Aggregated entity has a direct FK to the source entity — the
    helper fires one query per member with the FK filter and returns
    a member_id → value dict."""
    repo = _make_aggregated_repo({"m1": 6.5, "m2": 4.2})
    lens = CohortStripLens(
        id="avg_score",
        label="Avg Score",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
        ),
    )

    result = _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}, {"id": "m2"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": repo},
            scope_only_filters=None,
            member_via="id",
        )
    )
    assert result == {"m1": 6.5, "m2": 4.2}
    # One Repository.aggregate call per member (N+1 — phase 3 batches).
    assert repo.aggregate.await_count == 2


def test_source_relative_aggregate_no_entity() -> None:
    """When the AggregateRef has no entity, the source entity's repo
    is used. The FK-to-source lookup still resolves (self-reference
    edge case isn't supported — instead this exercises avg(column) on
    the cohort source itself, which the runtime treats as
    ``ref.entity = source_entity``)."""
    repo = _make_aggregated_repo({"m1": 7.0})
    # Match the helper's behaviour: source_relative refs fall back to
    # ``source_entity`` for the repo lookup. The mocked entity_spec
    # carries a FK named "student" referring to "StudentProfile" —
    # which is also the source. So this exercises the source-rel path.
    lens = CohortStripLens(
        id="bare_avg",
        label="Bare Avg",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", column="score"),
        ),
    )
    result = _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"StudentProfile": repo},
            scope_only_filters=None,
            member_via="id",
        )
    )
    assert result == {"m1": 7.0}


def test_via_clause_missing_junction_repo_warns(caplog: pytest.LogCaptureFixture) -> None:
    """When the via's junction entity isn't in the repositories registry,
    the helper logs a clear warning and returns empty."""
    repo = _make_aggregated_repo({"m1": 6.5})
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
            via=ViaCondition(junction_entity="ClassEnrolment", bindings=[]),
        ),
    )
    with caplog.at_level("WARNING"):
        result = _run(
            compute_cohort_aggregate_primary(
                items=[{"id": "m1"}],
                lens=lens,
                source_entity="StudentProfile",
                repositories={"MarkingResult": repo},
                scope_only_filters=None,
                member_via="id",
            )
        )
    assert result == {}
    assert any("junction entity" in msg.lower() for msg in caplog.messages)


def test_missing_fk_returns_empty_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """When the aggregated entity has no FK to the source entity, the
    helper can't filter per-member. Logs a clear warning and returns
    empty (cells render without values rather than fabricating ones)."""
    repo = MagicMock()
    # Spec with NO FK back to StudentProfile.
    spec = MagicMock()
    f = MagicMock()
    f.name = "score"
    f.type = MagicMock()
    f.type.kind = "int"
    spec.fields = [f]
    repo.entity_spec = spec
    repo.aggregate = AsyncMock(return_value=[])

    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
        ),
    )
    with caplog.at_level("WARNING"):
        result = _run(
            compute_cohort_aggregate_primary(
                items=[{"id": "m1"}],
                lens=lens,
                source_entity="StudentProfile",
                repositories={"MarkingResult": repo},
                scope_only_filters=None,
                member_via="id",
            )
        )
    assert result == {}
    assert any("no fk" in msg.lower() for msg in caplog.messages)
    repo.aggregate.assert_not_called()


def test_where_clause_propagates_to_aggregate_filters() -> None:
    """The AggregateRef's where: clause must reach Repository.aggregate
    as a __scope_predicate, AND-composed with the per-member FK filter."""
    repo = _make_aggregated_repo({"m1": 6.5})
    where_expr = ConditionExpr(
        comparison=Comparison(
            field="latest_for_event",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal=True),
        )
    )
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(
                func="avg",
                entity="MarkingResult",
                column="score",
                where=where_expr,
            ),
        ),
    )
    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": repo},
            scope_only_filters=None,
            member_via="id",
        )
    )
    call = repo.aggregate.await_args
    filters_arg = call.kwargs["filters"]
    # Per-member FK filter present.
    assert filters_arg["student"] == "m1"
    # The where-clause flowed through to __scope_predicate
    assert "__scope_predicate" in filters_arg
    pred_sql, _params = filters_arg["__scope_predicate"]
    assert "latest_for_event" in pred_sql


def test_count_aggregate_uses_count_measure() -> None:
    """count() routes to the bare ``"count"`` measure spec; scalars
    route to ``"<func>:<col>"``."""
    repo = _make_aggregated_repo({"m1": 5})
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
        ),
    )
    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": repo},
            scope_only_filters=None,
            member_via="id",
        )
    )
    measures = repo.aggregate.await_args.kwargs["measures"]
    assert measures == {"primary": "count"}


def _make_junction_repo(entity_name: str, fk_to: str, fk_col: str):
    """Mock a junction-entity repo with one FK to the aggregated side
    (e.g. ``ClassEnrolment.student_profile → StudentProfile``)."""
    spec = MagicMock()
    spec.name = entity_name
    fk_field = MagicMock()
    fk_field.name = fk_col
    fk_field.type = MagicMock()
    fk_field.type.kind = "ref"
    fk_field.type.ref_entity = fk_to
    id_field = MagicMock()
    id_field.name = "id"
    id_field.type = MagicMock()
    id_field.type.kind = "uuid"
    spec.fields = [fk_field, id_field]
    repo = MagicMock()
    repo.entity_spec = spec
    return repo


def _make_repo_with_fk_to_junction(
    entity_name: str, junction_name: str, fk_col: str = "class_enrolment"
):
    """Mock an aggregated-entity repo that has a FK to the junction
    entity (e.g. ``MarkingResult.class_enrolment → ClassEnrolment``)."""
    spec = MagicMock()
    spec.name = entity_name
    fk_field = MagicMock()
    fk_field.name = fk_col
    fk_field.type = MagicMock()
    fk_field.type.kind = "ref"
    fk_field.type.ref_entity = junction_name
    score = MagicMock()
    score.name = "score"
    score.type = MagicMock()
    score.type.kind = "int"
    spec.fields = [fk_field, score]
    repo = MagicMock()
    repo.entity_spec = spec
    return repo


def test_via_junction_to_aggregated_direction() -> None:
    """Phase 3: when the junction has a FK to the aggregated entity
    (``Enrolment.marking_result``), the subquery selects that FK and
    filters the aggregated entity on its primary key ``id``.

    DSL example::
        via: Enrolment(student_profile = id)
    """
    # ClassEnrolment.marking_result → MarkingResult.id
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    # Aggregated entity (MarkingResult) has no FK to source — we'll
    # link through the junction only.
    spec = MagicMock()
    spec.name = "MarkingResult"
    score = MagicMock()
    score.name = "score"
    score.type = MagicMock()
    score.type.kind = "int"
    spec.fields = [score]
    aggregated = MagicMock()
    aggregated.entity_spec = spec
    aggregated.aggregate = AsyncMock(return_value=[])

    via = ViaCondition(
        junction_entity="ClassEnrolment",
        bindings=[
            ViaBinding(junction_field="student_profile", target="id", operator="="),
        ],
    )
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
            via=via,
        ),
    )

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "stud-1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
            member_via="id",
        )
    )
    # The subquery should reference the junction → aggregated FK
    # ("marking_result") as the SELECT column.
    filters_arg = aggregated.aggregate.await_args.kwargs["filters"]
    pred_sql, pred_params = filters_arg["__scope_predicate"]
    assert '"id" IN (SELECT "marking_result" FROM "ClassEnrolment"' in pred_sql
    assert '"student_profile" = %s' in pred_sql
    assert pred_params == ["stud-1"]


def test_via_aggregated_to_junction_direction() -> None:
    """Phase 3: when the aggregated entity has the FK to the junction
    (``MarkingResult.class_enrolment``), the subquery selects the
    junction's ``id`` and filters the aggregated entity on its FK.

    Less common but supported for completeness."""
    # MarkingResult.class_enrolment → ClassEnrolment.id
    aggregated = _make_repo_with_fk_to_junction(
        "MarkingResult", junction_name="ClassEnrolment", fk_col="class_enrolment"
    )
    aggregated.aggregate = AsyncMock(return_value=[])

    # Junction has NO FK to MarkingResult — only the reverse direction
    # is available, forcing the agg_to_junction fallback.
    junction_spec = MagicMock()
    junction_spec.name = "ClassEnrolment"
    student_field = MagicMock()
    student_field.name = "student_profile"
    student_field.type = MagicMock()
    student_field.type.kind = "ref"
    student_field.type.ref_entity = "StudentProfile"
    junction_spec.fields = [student_field]
    junction = MagicMock()
    junction.entity_spec = junction_spec

    via = ViaCondition(
        junction_entity="ClassEnrolment",
        bindings=[
            ViaBinding(junction_field="student_profile", target="id", operator="="),
        ],
    )
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
            via=via,
        ),
    )
    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "stud-1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
            member_via="id",
        )
    )
    filters_arg = aggregated.aggregate.await_args.kwargs["filters"]
    pred_sql, pred_params = filters_arg["__scope_predicate"]
    # Selects junction's id; filters aggregated entity on its FK col.
    assert '"class_enrolment" IN (SELECT "id" FROM "ClassEnrolment"' in pred_sql
    assert pred_params == ["stud-1"]


def test_via_no_link_warns(caplog: pytest.LogCaptureFixture) -> None:
    """When neither direction resolves (no FK between aggregated entity
    and junction), warn clearly and return empty."""
    spec = MagicMock()
    spec.name = "MarkingResult"
    score = MagicMock()
    score.name = "score"
    score.type = MagicMock()
    score.type.kind = "int"
    spec.fields = [score]
    aggregated = MagicMock()
    aggregated.entity_spec = spec
    aggregated.aggregate = AsyncMock(return_value=[])

    junction_spec = MagicMock()
    junction_spec.name = "ClassEnrolment"
    junction_spec.fields = []
    junction = MagicMock()
    junction.entity_spec = junction_spec

    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
            via=ViaCondition(junction_entity="ClassEnrolment", bindings=[]),
        ),
    )
    with caplog.at_level("WARNING"):
        result = _run(
            compute_cohort_aggregate_primary(
                items=[{"id": "stud-1"}],
                lens=lens,
                source_entity="StudentProfile",
                repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
                scope_only_filters=None,
                member_via="id",
            )
        )
    assert result == {}
    assert any("no fk" in msg.lower() for msg in caplog.messages)
    aggregated.aggregate.assert_not_called()


def test_via_null_binding() -> None:
    """``field = null`` bindings render as IS NULL in the subquery."""
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    aggregated = MagicMock()
    spec = MagicMock()
    spec.name = "MarkingResult"
    spec.fields = []
    aggregated.entity_spec = spec
    aggregated.aggregate = AsyncMock(return_value=[])

    via = ViaCondition(
        junction_entity="ClassEnrolment",
        bindings=[
            ViaBinding(junction_field="student_profile", target="id", operator="="),
            ViaBinding(junction_field="revoked_at", target="null", operator="="),
        ],
    )
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
            via=via,
        ),
    )
    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "stud-1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
            member_via="id",
        )
    )
    filters_arg = aggregated.aggregate.await_args.kwargs["filters"]
    pred_sql, _params = filters_arg["__scope_predicate"]
    assert '"revoked_at" IS NULL' in pred_sql


def test_missing_repo_returns_empty() -> None:
    """When the aggregated entity isn't in the repositories registry,
    return empty — common in unit tests that haven't wired the repo."""
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="Missing", column="score"),
        ),
    )
    result = _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"StudentProfile": MagicMock()},
            scope_only_filters=None,
            member_via="id",
        )
    )
    assert result == {}
