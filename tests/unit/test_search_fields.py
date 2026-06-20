"""Tests for surface search_fields and filter_fields wiring (#361, #596)."""

import pytest

from dazzle.http.runtime.app_factory import build_entity_filter_fields, build_entity_search_fields
from dazzle.http.runtime.query_builder import QueryBuilder

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


# Need SurfaceSpec import for the parametrized tests below
from dazzle.core.ir.surfaces import SurfaceSpec  # noqa: E402


def _surfaces_extracts_search_fields():
    return [_make_surface("Task", search_fields=["title", "description"])]


def _surfaces_no_search_fields():
    return [_make_surface("Task")]


def _surfaces_multiple_entities():
    return [
        _make_surface("Task", search_fields=["title"]),
        _make_surface("Bug", search_fields=["summary", "details"]),
    ]


def _surfaces_first_surface_wins():
    return [
        _make_surface("Task", search_fields=["title"]),
        SurfaceSpec(
            name="task_detail",
            entity_ref="Task",
            mode="list",
            search_fields=["description"],
        ),
    ]


def _surfaces_no_entity_ref():
    return [SurfaceSpec(name="dashboard", mode="list", search_fields=["q"])]


def _surfaces_ux_fallback():
    from dazzle.core.ir.ux import UXSpec

    return [
        SurfaceSpec(
            name="contact_list",
            entity_ref="Contact",
            mode="list",
            ux=UXSpec(search=["first_name", "last_name", "email"]),
        )
    ]


def _surfaces_top_level_wins():
    from dazzle.core.ir.ux import UXSpec

    return [
        SurfaceSpec(
            name="contact_list",
            entity_ref="Contact",
            mode="list",
            search_fields=["email"],
            ux=UXSpec(search=["first_name", "last_name"]),
        )
    ]


class TestBuildEntitySearchFields:
    """build_entity_search_fields() should extract search_fields from surface specs."""

    @pytest.mark.parametrize(
        ("surfaces_factory", "expected"),
        [
            (_surfaces_extracts_search_fields, {"Task": ["title", "description"]}),
            (_surfaces_no_search_fields, {}),
            (
                _surfaces_multiple_entities,
                {"Task": ["title"], "Bug": ["summary", "details"]},
            ),
            (_surfaces_first_surface_wins, {"Task": ["title"]}),
            (_surfaces_no_entity_ref, {}),
            (
                _surfaces_ux_fallback,
                {"Contact": ["first_name", "last_name", "email"]},
            ),
            (_surfaces_top_level_wins, {"Contact": ["email"]}),
        ],
        ids=[
            "test_extracts_search_fields",
            "test_no_search_fields_excluded",
            "test_multiple_entities",
            "test_first_surface_wins",
            "test_no_entity_ref_ignored",
            "test_falls_back_to_ux_search_when_surface_lacks_search_fields",
            "test_top_level_search_fields_wins_over_ux_search",
        ],
    )
    def test_build_entity_search_fields(self, surfaces_factory, expected) -> None:
        result = build_entity_search_fields(surfaces_factory())
        assert result == expected


# =============================================================================
# build_entity_filter_fields tests (#596)
# =============================================================================


def _make_surface_with_ux(
    entity_ref: str,
    filter_fields: list[str] | None = None,
    search_fields: list[str] | None = None,
):
    """Create a minimal surface with UX spec containing filter fields."""
    from dazzle.core.ir.ux import UXSpec

    ux = UXSpec(filter=filter_fields or [], search=search_fields or []) if filter_fields else None
    return SurfaceSpec(
        name=f"{entity_ref.lower()}_list",
        entity_ref=entity_ref,
        mode="list",
        ux=ux,
    )


class TestBuildEntityFilterFields:
    """build_entity_filter_fields() should extract ux.filter from surface specs."""

    @pytest.mark.parametrize(
        ("builder", "expected"),
        [
            (
                lambda: [
                    _make_surface_with_ux("Contact", filter_fields=["company_name", "status"])
                ],
                {"Contact": ["company_name", "status"]},
            ),
            (lambda: [_make_surface("Task")], {}),
            (lambda: [_make_surface_with_ux("Task")], {}),
            (
                lambda: [
                    _make_surface_with_ux("Task", filter_fields=["status"]),
                    _make_surface_with_ux("Bug", filter_fields=["severity", "assignee"]),
                ],
                {"Task": ["status"], "Bug": ["severity", "assignee"]},
            ),
            (
                lambda: [
                    _make_surface_with_ux("Task", filter_fields=["status"]),
                    SurfaceSpec(
                        name="task_detail",
                        entity_ref="Task",
                        mode="list",
                        ux=None,
                    ),
                ],
                {"Task": ["status"]},
            ),
        ],
        ids=[
            "test_extracts_filter_fields",
            "test_no_ux_excluded",
            "test_empty_filter_excluded",
            "test_multiple_entities",
            "test_first_surface_wins",
        ],
    )
    def test_filter_fields(self, builder, expected) -> None:
        result = build_entity_filter_fields(builder())
        assert result == expected
