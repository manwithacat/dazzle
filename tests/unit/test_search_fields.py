"""Tests for surface search_fields wiring (#361)."""

from __future__ import annotations

from dazzle_back.runtime.app_factory import build_entity_search_fields
from dazzle_back.runtime.query_builder import QueryBuilder

# =============================================================================
# QueryBuilder search tests
# =============================================================================


class TestQueryBuilderSearch:
    """QueryBuilder should generate LIKE conditions when search_query and search_fields are set."""

    def test_search_adds_like_conditions(self) -> None:
        """set_search() with fields should produce LIKE clauses in WHERE."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("urgent", fields=["title", "description"])
        sql, params = builder.build_select()
        assert "LIKE" in sql
        assert "%urgent%" in params
        # Two search fields → two LIKE conditions
        assert sql.count("LIKE") == 2

    def test_search_without_fields_is_noop(self) -> None:
        """set_search() without fields should not add WHERE clause."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("urgent")
        sql, params = builder.build_select()
        assert "WHERE" not in sql
        assert params == [20, 0]  # Just LIMIT/OFFSET

    def test_search_fields_quoted(self) -> None:
        """Search field names should be quoted to prevent SQL injection."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("test", fields=["title"])
        sql, _params = builder.build_select()
        assert '"title"' in sql

    def test_search_combined_with_filters(self) -> None:
        """Search should AND with existing filter conditions."""
        builder = QueryBuilder(table_name="tasks")
        builder.add_filter("status", "active")
        builder.set_search("urgent", fields=["title"])
        sql, params = builder.build_select()
        assert "WHERE" in sql
        assert "AND" in sql
        # Filter param + search param + LIMIT/OFFSET
        assert "%urgent%" in params
        assert "active" in params

    def test_search_count_query_includes_search(self) -> None:
        """COUNT query should also respect search conditions."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("test", fields=["title"])
        sql, params = builder.build_count()
        assert "COUNT(*)" in sql
        assert "LIKE" in sql
        assert "%test%" in params

    def test_search_uses_or_across_fields(self) -> None:
        """Multiple search fields should be joined with OR."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("x", fields=["title", "notes", "body"])
        sql, _params = builder.build_select()
        assert sql.count("OR") == 2  # 3 fields → 2 ORs

    def test_empty_search_query_is_noop(self) -> None:
        """Empty search string should not add conditions."""
        builder = QueryBuilder(table_name="tasks")
        builder.set_search("", fields=["title"])
        sql, params = builder.build_select()
        assert "WHERE" not in sql


# =============================================================================
# build_entity_search_fields tests
# =============================================================================


def _make_surface(entity_ref: str, search_fields: list[str] | None = None, **kwargs):
    """Create a minimal surface-like object with search_fields."""
    from dazzle.core.ir.surfaces import SurfaceSpec

    return SurfaceSpec(
        name=f"{entity_ref.lower()}_list",
        entity_ref=entity_ref,
        mode="list",
        search_fields=search_fields or [],
        **kwargs,
    )


class TestBuildEntitySearchFields:
    """build_entity_search_fields() should extract search_fields from surface specs."""

    def test_extracts_search_fields(self) -> None:
        """Surfaces with search_fields should be extracted."""
        surfaces = [_make_surface("Task", search_fields=["title", "description"])]
        result = build_entity_search_fields(surfaces)
        assert result == {"Task": ["title", "description"]}

    def test_no_search_fields_excluded(self) -> None:
        """Surfaces without search_fields should not appear."""
        surfaces = [_make_surface("Task")]
        result = build_entity_search_fields(surfaces)
        assert result == {}

    def test_multiple_entities(self) -> None:
        """Each entity's search fields should be extracted independently."""
        surfaces = [
            _make_surface("Task", search_fields=["title"]),
            _make_surface("Bug", search_fields=["summary", "details"]),
        ]
        result = build_entity_search_fields(surfaces)
        assert result == {"Task": ["title"], "Bug": ["summary", "details"]}

    def test_first_surface_wins(self) -> None:
        """If multiple surfaces reference the same entity, keep the first."""
        surfaces = [
            _make_surface("Task", search_fields=["title"]),
            _make_surface("Task", search_fields=["description"]),
        ]
        # Second surface has different name to avoid validation error
        surfaces[1] = SurfaceSpec(
            name="task_detail",
            entity_ref="Task",
            mode="list",
            search_fields=["description"],
        )
        result = build_entity_search_fields(surfaces)
        assert result == {"Task": ["title"]}

    def test_no_entity_ref_ignored(self) -> None:
        """Surfaces without entity_ref should be skipped."""
        from dazzle.core.ir.surfaces import SurfaceSpec

        surfaces = [SurfaceSpec(name="dashboard", mode="list", search_fields=["q"])]
        result = build_entity_search_fields(surfaces)
        assert result == {}


# Need SurfaceSpec import for the test_first_surface_wins test
from dazzle.core.ir.surfaces import SurfaceSpec  # noqa: E402
