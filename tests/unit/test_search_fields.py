"""Tests for surface search_fields and filter_fields wiring (#361, #596)."""

from dazzle_back.runtime.app_factory import build_entity_filter_fields, build_entity_search_fields
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

    def test_falls_back_to_ux_search_when_surface_lacks_search_fields(self) -> None:
        """ux.search is the canonical form; build_entity_search_fields
        must read it too (#856). Previously only legacy top-level
        search_fields was honoured, which is why the contact_manager
        filterable_table search input produced no WHERE clause."""
        from dazzle.core.ir.ux import UXSpec

        surface = SurfaceSpec(
            name="contact_list",
            entity_ref="Contact",
            mode="list",
            ux=UXSpec(search=["first_name", "last_name", "email"]),
        )
        result = build_entity_search_fields([surface])
        assert result == {"Contact": ["first_name", "last_name", "email"]}

    def test_top_level_search_fields_wins_over_ux_search(self) -> None:
        """When both are declared, legacy top-level takes precedence — matches
        existing doc comment semantics and avoids breaking apps that set both."""
        from dazzle.core.ir.ux import UXSpec

        surface = SurfaceSpec(
            name="contact_list",
            entity_ref="Contact",
            mode="list",
            search_fields=["email"],
            ux=UXSpec(search=["first_name", "last_name"]),
        )
        result = build_entity_search_fields([surface])
        assert result == {"Contact": ["email"]}


# Need SurfaceSpec import for the test_first_surface_wins test
from dazzle.core.ir.surfaces import SurfaceSpec  # noqa: E402

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

    def test_extracts_filter_fields(self) -> None:
        surfaces = [_make_surface_with_ux("Contact", filter_fields=["company_name", "status"])]
        result = build_entity_filter_fields(surfaces)
        assert result == {"Contact": ["company_name", "status"]}

    def test_no_ux_excluded(self) -> None:
        surfaces = [_make_surface("Task")]
        result = build_entity_filter_fields(surfaces)
        assert result == {}

    def test_empty_filter_excluded(self) -> None:
        surfaces = [_make_surface_with_ux("Task")]
        result = build_entity_filter_fields(surfaces)
        assert result == {}

    def test_multiple_entities(self) -> None:
        surfaces = [
            _make_surface_with_ux("Task", filter_fields=["status"]),
            _make_surface_with_ux("Bug", filter_fields=["severity", "assignee"]),
        ]
        result = build_entity_filter_fields(surfaces)
        assert result == {"Task": ["status"], "Bug": ["severity", "assignee"]}

    def test_first_surface_wins(self) -> None:
        surfaces = [
            _make_surface_with_ux("Task", filter_fields=["status"]),
            SurfaceSpec(
                name="task_detail",
                entity_ref="Task",
                mode="list",
                ux=None,
            ),
        ]
        result = build_entity_filter_fields(surfaces)
        assert result == {"Task": ["status"]}
