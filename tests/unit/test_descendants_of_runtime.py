"""#1227 Phase 3b.ii — runtime recursive CTE for descendants_of / ancestors_of.

Module-level helper ``_resolve_recursive_traversal_fields`` runs a
recursive CTE per traversal field, then a batched fetch to resolve
the full rows. These tests pin:

1. Self-ref descendants: walk SQL uses the via FK in both the CTE
   anchor and the recursive step.
2. Self-ref ancestors: SQL walks up via the parent FK from each source.
3. Junction-mediated descendants: SQL hits the junction table; the
   helper probes information_schema for the child FK column.
4. Attaches an empty list when no walk results.
5. Attaches the resolved rows grouped by source id when results match.
6. No-op when entity has no traversal fields.
7. Handles empty input rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.core import ir


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
    )


def _make_db(*query_responses: list[dict]) -> MagicMock:
    """Build a mock DB whose cursor.fetchall returns each response in turn."""
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchall = MagicMock(side_effect=list(query_responses))
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    db = MagicMock()
    db.placeholder = "%s"
    db.connection = MagicMock(return_value=ctx)
    db._mock_cursor = cursor
    return db


def _department_with_descendants() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Department",
        fields=[
            _id_field(),
            _ref("parent_department", "Department"),
            ir.FieldSpec(
                name="all_descendants",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.DESCENDANTS_OF,
                    via_field="parent_department",
                ),
            ),
        ],
    )


def _department_with_ancestors() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Department",
        fields=[
            _id_field(),
            _ref("parent_department", "Department"),
            ir.FieldSpec(
                name="ancestor_chain",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.ANCESTORS_OF,
                    via_field="parent_department",
                ),
            ),
        ],
    )


def _person_with_junction_descendants() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Person",
        fields=[
            _id_field(),
            ir.FieldSpec(
                name="all_reports",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.DESCENDANTS_OF,
                    via_entity="ManagerLink",
                    via_field="manager",
                ),
            ),
        ],
    )


class TestSelfRefDescendantsSQL:
    def test_cte_uses_via_in_anchor_and_recurse(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        # First call: CTE returns (root, id) pairs. Second call: fetch
        # full rows. Test only inspects the first call's SQL.
        db = _make_db([], [])
        _resolve_recursive_traversal_fields(
            [{"id": "d1"}, {"id": "d2"}],
            _department_with_descendants(),
            db,
            "Department",
        )
        first_sql = db._mock_cursor.execute.call_args_list[0].args[0]
        assert "WITH RECURSIVE walk" in first_sql
        assert '"parent_department" IN (%s, %s)' in first_sql
        assert 'JOIN walk w ON t."parent_department" = w.id' in first_sql

    def test_attaches_empty_list_when_no_descendants(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        rows = [{"id": "d1"}]
        # CTE returns no pairs; helper short-circuits the second fetch.
        db = _make_db([])
        result = _resolve_recursive_traversal_fields(
            rows, _department_with_descendants(), db, "Department"
        )
        assert result[0]["all_descendants"] == []

    def test_attaches_resolved_rows_grouped_by_source(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        # d1 has descendants d10, d11; d2 has none.
        cte_pairs = [
            {"root": "d1", "id": "d10"},
            {"root": "d1", "id": "d11"},
        ]
        fetched = [
            {"id": "d10", "parent_department": "d1"},
            {"id": "d11", "parent_department": "d1"},
        ]
        db = _make_db(cte_pairs, fetched)
        rows = [{"id": "d1"}, {"id": "d2"}]
        result = _resolve_recursive_traversal_fields(
            rows, _department_with_descendants(), db, "Department"
        )
        d1_desc = result[0]["all_descendants"]
        assert len(d1_desc) == 2
        assert {r["id"] for r in d1_desc} == {"d10", "d11"}
        assert result[1]["all_descendants"] == []


class TestSelfRefAncestorsSQL:
    def test_cte_walks_up_via_parent_fk(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        db = _make_db([], [])
        _resolve_recursive_traversal_fields(
            [{"id": "d10"}],
            _department_with_ancestors(),
            db,
            "Department",
        )
        first_sql = db._mock_cursor.execute.call_args_list[0].args[0]
        assert "WITH RECURSIVE walk" in first_sql
        assert '"parent_department" IS NOT NULL' in first_sql
        # Anchor: from each source, project (parent, id-as-root).
        assert 'SELECT "parent_department", id FROM' in first_sql


class TestJunctionMediatedDescendants:
    def test_probes_information_schema_then_uses_junction(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        # The helper first runs an info_schema probe to find the
        # non-via FK on the junction. Provide that, then an empty CTE.
        probe_cols = [
            {"column_name": "id"},
            {"column_name": "manager"},
            {"column_name": "report"},
        ]
        cte_pairs: list[dict] = []
        db = _make_db(probe_cols, cte_pairs)
        rows = [{"id": "p1"}]
        result = _resolve_recursive_traversal_fields(
            rows, _person_with_junction_descendants(), db, "Person"
        )
        # First call should be the info_schema probe.
        probe_sql = db._mock_cursor.execute.call_args_list[0].args[0]
        assert "information_schema.columns" in probe_sql
        # Second call should be the CTE referencing the junction.
        cte_sql = db._mock_cursor.execute.call_args_list[1].args[0]
        assert '"ManagerLink"' in cte_sql
        assert '"manager"' in cte_sql
        assert '"report"' in cte_sql
        # No matches → empty list.
        assert result[0]["all_reports"] == []


class TestEdgeCases:
    def test_no_op_when_no_traversal_fields(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        plain = ir.EntitySpec(name="Plain", fields=[_id_field()])
        rows = [{"id": "p1"}]
        db = _make_db([])
        result = _resolve_recursive_traversal_fields(rows, plain, db, "Plain")
        assert result == rows
        assert not db._mock_cursor.execute.called

    def test_no_op_on_empty_rows(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        db = _make_db([])
        result = _resolve_recursive_traversal_fields(
            [], _department_with_descendants(), db, "Department"
        )
        assert result == []
        assert not db._mock_cursor.execute.called

    def test_rows_without_id_get_empty_lists(self) -> None:
        from dazzle.http.runtime.repository import (
            _resolve_recursive_traversal_fields,
        )

        rows = [{"id": None}]
        db = _make_db([])
        result = _resolve_recursive_traversal_fields(
            rows, _department_with_descendants(), db, "Department"
        )
        assert result[0]["all_descendants"] == []
        assert not db._mock_cursor.execute.called


class TestJunctionChildFKDiscovery:
    def test_discover_returns_first_non_via_non_id_column(self) -> None:
        from dazzle.http.runtime.repository import _discover_junction_child_fk

        db = _make_db(
            [
                {"column_name": "id"},
                {"column_name": "manager"},
                {"column_name": "report"},
                {"column_name": "created_at"},
            ]
        )
        col = _discover_junction_child_fk(db, "ManagerLink", "manager")
        assert col == "report"

    def test_discover_returns_none_when_no_other_columns(self) -> None:
        from dazzle.http.runtime.repository import _discover_junction_child_fk

        db = _make_db(
            [
                {"column_name": "id"},
                {"column_name": "manager"},
            ]
        )
        col = _discover_junction_child_fk(db, "ManagerLink", "manager")
        assert col is None

    def test_discover_returns_none_on_query_failure(self) -> None:
        from dazzle.http.runtime.repository import _discover_junction_child_fk

        cursor = MagicMock()
        cursor.execute = MagicMock(side_effect=RuntimeError("boom"))
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        db = MagicMock()
        db.connection = MagicMock(return_value=ctx)
        col = _discover_junction_child_fk(db, "ManagerLink", "manager")
        assert col is None
