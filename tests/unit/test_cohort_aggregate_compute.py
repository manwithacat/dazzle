"""``compute_cohort_aggregate_primary`` integration tests.

History:
- Phase 2 (#1144) wired the direct-FK path with N+1 fan-out.
- Phase 3 (#1144) added junction-binding via support, still N+1.
- #1153 retired the fan-out entirely: one ``Repository.aggregate``
  GROUP BY call for the direct-FK case, one bespoke JOIN query for
  the via case. Tests below pin the batched shapes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from dazzle.http.runtime.workspace_region_computes import compute_cohort_aggregate_primary


def _make_aggregated_repo(per_member: dict[str, float]) -> MagicMock:
    """Mock an aggregated-entity repo whose batched ``aggregate()``
    returns one bucket per member-id matched in ``filters[student__in]``.
    """
    spec = MagicMock()
    spec.name = "MarkingResult"
    # Aggregated entity has a `student` FK to "StudentProfile" (source).
    student_field = MagicMock()
    student_field.name = "student"
    student_field.type = MagicMock()
    student_field.type.kind = "ref"
    student_field.type.ref_entity = "StudentProfile"
    score = MagicMock()
    score.name = "score"
    score.type = MagicMock()
    score.type.kind = "int"
    spec.fields = [student_field, score]

    repo = MagicMock()
    repo.entity_spec = spec
    repo.table_name = "marking_result"

    async def _aggregate(
        *, dimensions, measures, filters=None, limit=200, measure_expressions=None
    ):
        requested = (filters or {}).get("student__in") or []
        out_buckets = []
        for mid in requested:
            if mid in per_member:
                bucket = MagicMock()
                bucket.dimensions = {"student": mid}
                bucket.measures = {"primary": per_member[mid]}
                out_buckets.append(bucket)
        return out_buckets

    repo.aggregate = AsyncMock(side_effect=_aggregate)
    return repo


def _run(coro):
    return asyncio.run(coro)


def test_direct_fk_batched_dispatch() -> None:
    """One Repository.aggregate call covers the whole cohort with a
    GROUP BY on the FK column."""
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
        )
    )
    assert result == {"m1": 6.5, "m2": 4.2}
    # One query for the whole cohort — N+1 retired.
    assert repo.aggregate.await_count == 1
    call = repo.aggregate.await_args
    # Dimension is the FK column.
    dims = call.kwargs["dimensions"]
    assert len(dims) == 1 and dims[0].name == "student"
    # Filters carry the IN clause.
    assert call.kwargs["filters"]["student__in"] == ["m1", "m2"]


def test_fk_path_strips_source_scope_predicate_for_cross_entity() -> None:
    """#1250 — the direct-FK aggregate path is cross-entity when
    `ref.entity != source_entity`. The source-entity __scope_predicate
    qualifies a column on a table that's not in the aggregate's FROM
    clause; merging it produces UndefinedTable and the silent-catch
    swallows the failure. Strip it before invoking
    Repository.aggregate."""
    repo = _make_aggregated_repo({"m1": 6.5})
    lens = CohortStripLens(
        id="avg_score",
        label="Avg Score",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
        ),
    )

    # Scoped persona — source-entity (StudentProfile) RBAC predicate.
    scope_filters = {
        "__scope_predicate": ('"StudentProfile"."school" = %s', ["school-uuid"]),
    }

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": repo},
            scope_only_filters=scope_filters,
        )
    )

    call = repo.aggregate.await_args
    # Post-fix the source-entity __scope_predicate is stripped before
    # passing through; the IN clause alone enforces source-row scoping.
    filters_arg = call.kwargs["filters"]
    assert "__scope_predicate" not in filters_arg, (
        f"FK path must strip the source-entity scope predicate when "
        f"aggregated_entity != source_entity; got {filters_arg}"
    )
    # The IN clause still restricts to scoped members.
    assert filters_arg["student__in"] == ["m1"]


def test_fk_path_keeps_scope_predicate_for_same_entity_aggregate() -> None:
    """#1250 sibling: when ref.entity == source_entity (same-entity
    aggregate, e.g. self-referencing FK), the source-entity scope
    predicate qualifies a column on the table that IS in the FROM —
    keep it. Otherwise we'd lose legitimate RBAC."""
    repo = _make_aggregated_repo({"m1": 3})
    lens = CohortStripLens(
        id="dependents",
        label="Dependents",
        # Self-aggregate: ref.entity is None → aggregated_entity == source_entity.
        primary_aggregate=LensAggregatePrimary(aggregate=AggregateRef(func="count")),
    )

    scope_filters = {
        "__scope_predicate": ('"StudentProfile"."school" = %s', ["school-uuid"]),
    }

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "m1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"StudentProfile": repo},
            scope_only_filters=scope_filters,
        )
    )

    call = repo.aggregate.await_args
    # Same-entity aggregate: scope predicate must reach Repository.aggregate.
    filters_arg = call.kwargs["filters"]
    assert "__scope_predicate" in filters_arg, filters_arg
    assert filters_arg["__scope_predicate"][1] == ["school-uuid"]


def test_source_relative_aggregate_no_entity() -> None:
    """When AggregateRef has no entity, the source entity supplies the
    repo (self-reference)."""
    repo = _make_aggregated_repo({"m1": 7.0})
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
        )
    )
    assert result == {"m1": 7.0}


def test_via_clause_missing_junction_repo_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Missing junction → warn + return empty."""
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
            )
        )
    assert result == {}
    assert any("junction entity" in msg.lower() for msg in caplog.messages)


def test_missing_fk_returns_empty_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """No FK from aggregated → source ⇒ warn + return empty."""
    repo = MagicMock()
    spec = MagicMock()
    spec.name = "MarkingResult"
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
            )
        )
    assert result == {}
    assert any("no fk" in msg.lower() for msg in caplog.messages)
    repo.aggregate.assert_not_called()


def test_where_clause_propagates_to_aggregate_filters() -> None:
    """The AggregateRef's where: clause reaches Repository.aggregate
    as a __scope_predicate, AND-composed with the cohort IN clause."""
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
        )
    )
    call = repo.aggregate.await_args
    filters_arg = call.kwargs["filters"]
    assert filters_arg["student__in"] == ["m1"]
    assert "__scope_predicate" in filters_arg
    pred_sql, _params = filters_arg["__scope_predicate"]
    assert "latest_for_event" in pred_sql


def test_count_aggregate_uses_count_measure() -> None:
    """count() routes to the bare ``"count"`` measure spec."""
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
        )
    )
    measures = repo.aggregate.await_args.kwargs["measures"]
    assert measures == {"primary": "count"}


# ─────────────── via-junction batched tests ───────────────


def _make_junction_repo(entity_name: str, fk_to: str, fk_col: str) -> MagicMock:
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


def _make_aggregated_with_db_mock(
    entity_name: str, table_name: str, *, has_fk_to: str | None = None
) -> MagicMock:
    """Aggregated repo with a stubbed ``db.connection()`` cursor for
    the bespoke via-batched SQL path. ``cursor.execute`` records the
    issued SQL+params; ``fetchall()`` returns whatever the caller
    stuffed into ``repo._mock_rows``.
    """
    spec = MagicMock()
    spec.name = entity_name
    if has_fk_to:
        fk = MagicMock()
        fk.name = "class_enrolment"
        fk.type = MagicMock()
        fk.type.kind = "ref"
        fk.type.ref_entity = has_fk_to
        spec.fields = [fk]
    else:
        spec.fields = []
    repo = MagicMock()
    repo.entity_spec = spec
    repo.table_name = table_name

    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchall = MagicMock(return_value=[])

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    repo.db = MagicMock()
    repo.db.placeholder = "%s"
    repo.db.connection = MagicMock(return_value=ctx)

    repo._mock_cursor = cursor
    repo._mock_conn = conn
    return repo


def test_via_junction_to_aggregated_batched() -> None:
    """Via path runs one JOIN-aware query over the whole cohort.

    Junction has FK to aggregated entity (direction junction_to_agg).
    Bindings of the form ``student_profile = id`` become the GROUP BY
    dimension and the IN clause.
    """
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    aggregated = _make_aggregated_with_db_mock("MarkingResult", "marking_result")
    aggregated._mock_cursor.fetchall = MagicMock(
        return_value=[{"member_id": "s1", "primary": 6.5}, {"member_id": "s2", "primary": 8.0}]
    )

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

    result = _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "s1"}, {"id": "s2"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
        )
    )
    assert result == {"s1": 6.5, "s2": 8.0}

    # One SQL execution covers the whole cohort.
    assert aggregated._mock_cursor.execute.call_count == 1
    sql_text, params = aggregated._mock_cursor.execute.call_args.args
    # Shape — INNER JOIN through the junction, GROUP BY the binding col.
    assert 'FROM "marking_result" a' in sql_text
    assert 'INNER JOIN "ClassEnrolment" j' in sql_text
    assert 'GROUP BY j."student_profile"' in sql_text
    # Member IN clause carries both ids as bound params.
    assert 'j."student_profile" IN (%s, %s)' in sql_text
    assert params[-2:] == ["s1", "s2"]


def test_via_null_binding_batched() -> None:
    """Non-id bindings (``field = null``) compose into the WHERE clause
    as junction-side filters."""
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    aggregated = _make_aggregated_with_db_mock("MarkingResult", "marking_result")

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
            items=[{"id": "s1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
        )
    )
    sql_text, _params = aggregated._mock_cursor.execute.call_args.args
    assert 'j."revoked_at" IS NULL' in sql_text


def test_via_no_link_warns(caplog: pytest.LogCaptureFixture) -> None:
    """No FK between aggregated and junction → warn + return empty."""
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
            )
        )
    assert result == {}
    assert any("no fk" in msg.lower() for msg in caplog.messages)
    aggregated.aggregate.assert_not_called()


def test_missing_repo_returns_empty() -> None:
    """Aggregated entity not in repositories → empty result."""
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
        )
    )
    assert result == {}


# ─────────────── #1216: share: shared-parent JOIN tests ───────────────


def _make_repo_with_fks(entity_name: str, table_name: str, fks: dict[str, str]) -> MagicMock:
    """Build a mock repo whose entity_spec has named ref fields.

    `fks` maps field name → target entity name. Used to fake the
    shared-parent schema (ClassEnrolment.student_profile → StudentProfile,
    MarkingResult.student_profile → StudentProfile) without needing both
    sides to FK to each other.
    """
    spec = MagicMock()
    spec.name = entity_name
    fields = []
    id_field = MagicMock()
    id_field.name = "id"
    id_field.type = MagicMock()
    id_field.type.kind = "uuid"
    fields.append(id_field)
    for col, target in fks.items():
        ref = MagicMock()
        ref.name = col
        ref.type = MagicMock()
        ref.type.kind = "ref"
        ref.type.ref_entity = target
        fields.append(ref)
    spec.fields = fields

    repo = MagicMock()
    repo.entity_spec = spec
    repo.table_name = table_name

    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchall = MagicMock(return_value=[])
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    repo.db = MagicMock()
    repo.db.placeholder = "%s"
    repo.db.connection = MagicMock(return_value=ctx)

    repo._mock_cursor = cursor
    return repo


def test_share_builds_shared_parent_join_sql() -> None:
    """#1216: cohort source row (ClassEnrolment) and aggregated row
    (MarkingResult) both reference StudentProfile. `share: StudentProfile`
    bridges them with a single GROUP BY query keyed on source.id."""
    source = _make_repo_with_fks(
        "ClassEnrolment",
        "class_enrolment",
        {"student_profile": "StudentProfile", "teaching_group": "TeachingGroup"},
    )
    aggregated = _make_repo_with_fks(
        "MarkingResult", "marking_result", {"student_profile": "StudentProfile"}
    )
    aggregated._mock_cursor.fetchall = MagicMock(
        return_value=[
            {"member_id": "e1", "primary": 7.4},
            {"member_id": "e2", "primary": 9.0},
        ]
    )

    lens = CohortStripLens(
        id="cohort",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
            share="StudentProfile",
        ),
    )

    result = _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "e1"}, {"id": "e2"}],
            lens=lens,
            source_entity="ClassEnrolment",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": source},
            scope_only_filters=None,
        )
    )
    assert result == {"e1": 7.4, "e2": 9.0}

    assert aggregated._mock_cursor.execute.call_count == 1
    sql_text, params = aggregated._mock_cursor.execute.call_args.args
    # Source table joined directly (no junction abstraction).
    assert 'FROM "marking_result" a' in sql_text
    assert 'INNER JOIN "class_enrolment" s' in sql_text
    assert 'a."student_profile" = s."student_profile"' in sql_text
    assert 'GROUP BY s."id"' in sql_text
    assert 's."id" IN (%s, %s)' in sql_text
    assert params[-2:] == ["e1", "e2"]


def test_share_with_where_clause_uses_alias_not_table_name() -> None:
    """#1229 — when share: + aggregate where: compose, the sub-WHERE must
    reference the FROM alias ``a`` (not the raw ``"marking_result"`` table
    name). Pre-fix the bare table name leaked through and Postgres rejected
    the statement with UndefinedTable."""
    source = _make_repo_with_fks(
        "ClassEnrolment",
        "class_enrolment",
        {"student_profile": "StudentProfile"},
    )
    aggregated = _make_repo_with_fks(
        "MarkingResult", "marking_result", {"student_profile": "StudentProfile"}
    )
    aggregated._mock_cursor.fetchall = MagicMock(return_value=[{"member_id": "e1", "primary": 7.4}])

    where_expr = ConditionExpr(
        comparison=Comparison(
            field="latest_for_event",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal=True),
        )
    )

    lens = CohortStripLens(
        id="cohort",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(
                func="avg", entity="MarkingResult", column="score", where=where_expr
            ),
            share="StudentProfile",
        ),
    )

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "e1"}],
            lens=lens,
            source_entity="ClassEnrolment",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": source},
            scope_only_filters=None,
        )
    )

    sql_text, _params = aggregated._mock_cursor.execute.call_args.args
    # The sub-WHERE composed from the where_expr must reference the alias
    # ``a`` (Postgres treats ``"a"`` and ``a`` as the same identifier when
    # the alias was introduced unquoted in the FROM clause).
    assert '"a"."latest_for_event"' in sql_text, sql_text
    # And must NOT reference the unaliased entity name (would 500 with
    # UndefinedTable on Postgres).
    assert '"MarkingResult"."latest_for_event"' not in sql_text, sql_text


def test_via_with_where_clause_uses_alias_not_table_name() -> None:
    """#1229 — mirrors test_share_with_where_clause_uses_alias_not_table_name
    for the via: junction path. Same root cause: predicate compiler emits
    entity-name qualifiers but FROM clause aliases the table to ``a``."""
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    aggregated = _make_aggregated_with_db_mock("MarkingResult", "marking_result")
    aggregated._mock_cursor.fetchall = MagicMock(return_value=[{"member_id": "s1", "primary": 6.5}])

    where_expr = ConditionExpr(
        comparison=Comparison(
            field="latest_for_event",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal=True),
        )
    )

    via = ViaCondition(
        junction_entity="ClassEnrolment",
        bindings=[ViaBinding(junction_field="student_profile", target="id", operator="=")],
    )
    lens = CohortStripLens(
        id="cohort",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(
                func="avg", entity="MarkingResult", column="score", where=where_expr
            ),
            via=via,
        ),
    )

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "s1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=None,
        )
    )

    sql_text, _params = aggregated._mock_cursor.execute.call_args.args
    assert '"a"."latest_for_event"' in sql_text, sql_text
    assert '"MarkingResult"."latest_for_event"' not in sql_text, sql_text


def test_share_with_scope_predicate_strips_source_qualifier() -> None:
    """#1231 — when scope_only_filters carries a __scope_predicate (RBAC
    scope on the source entity), the share path must strip it before
    composition. Without the strip, the predicate is qualified by source
    entity name (e.g. ``"ClassEnrolment"."school" = $N``) and Postgres
    rejects the statement because the source table is aliased ``s`` in
    the FROM clause. The IN clause already enforces source-row scoping."""
    source = _make_repo_with_fks(
        "ClassEnrolment", "class_enrolment", {"student_profile": "StudentProfile"}
    )
    aggregated = _make_repo_with_fks(
        "MarkingResult", "marking_result", {"student_profile": "StudentProfile"}
    )
    aggregated._mock_cursor.fetchall = MagicMock(return_value=[{"member_id": "e1", "primary": 7.4}])

    lens = CohortStripLens(
        id="cohort",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
            share="StudentProfile",
        ),
    )

    # Simulate the scoped-persona path: scope_only_filters carries a
    # __scope_predicate against the source entity (ClassEnrolment).
    scope_filters = {
        "__scope_predicate": ('"ClassEnrolment"."school" = %s', ["school-uuid"]),
    }

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "e1"}],
            lens=lens,
            source_entity="ClassEnrolment",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": source},
            scope_only_filters=scope_filters,
        )
    )

    sql_text, params = aggregated._mock_cursor.execute.call_args.args
    # The unaliased source-entity qualifier must not appear in the SQL.
    assert '"ClassEnrolment"."school"' not in sql_text, sql_text
    # And the scope predicate's bound param ("school-uuid") must be absent
    # — confirming the strip removed both the SQL and the params slot.
    assert "school-uuid" not in params, params


def test_via_with_scope_predicate_strips_source_qualifier() -> None:
    """#1231 — mirror of the share test for the via: path. Same root cause:
    source-entity __scope_predicate references a table not in the FROM."""
    junction = _make_junction_repo("ClassEnrolment", fk_to="MarkingResult", fk_col="marking_result")
    aggregated = _make_aggregated_with_db_mock("MarkingResult", "marking_result")
    aggregated._mock_cursor.fetchall = MagicMock(return_value=[{"member_id": "s1", "primary": 6.5}])

    via = ViaCondition(
        junction_entity="ClassEnrolment",
        bindings=[ViaBinding(junction_field="student_profile", target="id", operator="=")],
    )
    lens = CohortStripLens(
        id="cohort",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
            via=via,
        ),
    )

    scope_filters = {
        "__scope_predicate": ('"StudentProfile"."school" = %s', ["school-uuid"]),
    }

    _run(
        compute_cohort_aggregate_primary(
            items=[{"id": "s1"}],
            lens=lens,
            source_entity="StudentProfile",
            repositories={"MarkingResult": aggregated, "ClassEnrolment": junction},
            scope_only_filters=scope_filters,
        )
    )

    sql_text, params = aggregated._mock_cursor.execute.call_args.args
    assert '"StudentProfile"."school"' not in sql_text, sql_text
    assert "school-uuid" not in params, params


def test_share_missing_pivot_fk_warns(caplog: pytest.LogCaptureFixture) -> None:
    """When `share:` is set but either side lacks a FK to the named
    pivot, log a warning naming the missing side and return empty."""
    source = _make_repo_with_fks(
        "ClassEnrolment", "class_enrolment", {"teaching_group": "TeachingGroup"}
    )
    aggregated = _make_repo_with_fks("MarkingResult", "marking_result", {})

    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
            share="StudentProfile",
        ),
    )
    with caplog.at_level("WARNING"):
        result = _run(
            compute_cohort_aggregate_primary(
                items=[{"id": "e1"}],
                lens=lens,
                source_entity="ClassEnrolment",
                repositories={"MarkingResult": aggregated, "ClassEnrolment": source},
                scope_only_filters=None,
            )
        )
    assert result == {}
    assert any("not reachable" in r.message for r in caplog.records)


def test_share_ambiguous_fk_refuses(caplog: pytest.LogCaptureFixture) -> None:
    """Hardening: when either side has *multiple* FKs to the named
    pivot, refuse rather than silently guess which one to JOIN on.

    Real-world trigger: a transfer-records table where the entity has
    `student_profile` AND `original_student_profile`, both `ref
    StudentProfile`. We don't try to pick.
    """
    source = _make_repo_with_fks(
        "ClassEnrolment", "class_enrolment", {"student_profile": "StudentProfile"}
    )
    aggregated = _make_repo_with_fks(
        "MarkingResult",
        "marking_result",
        {
            "student_profile": "StudentProfile",
            "original_student_profile": "StudentProfile",
        },
    )

    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="MarkingResult"),
            share="StudentProfile",
        ),
    )
    with caplog.at_level("WARNING"):
        result = _run(
            compute_cohort_aggregate_primary(
                items=[{"id": "e1"}],
                lens=lens,
                source_entity="ClassEnrolment",
                repositories={"MarkingResult": aggregated, "ClassEnrolment": source},
                scope_only_filters=None,
            )
        )
    assert result == {}
    assert any("ambiguous" in r.message for r in caplog.records)
