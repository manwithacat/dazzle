"""Tests for view-based list surface projections (issue #230)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl

# ---------------------------------------------------------------------------
# IR tests
# ---------------------------------------------------------------------------


class TestSurfaceViewRef:
    """SurfaceSpec.view_ref field."""

    def test_default_none(self) -> None:
        surface = ir.SurfaceSpec(name="s", mode=ir.SurfaceMode.LIST)
        assert surface.view_ref is None

    def test_set_view_ref(self) -> None:
        surface = ir.SurfaceSpec(
            name="company_list",
            mode=ir.SurfaceMode.LIST,
            entity_ref="Company",
            view_ref="CompanyListView",
        )
        assert surface.view_ref == "CompanyListView"
        assert surface.entity_ref == "Company"


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestSurfaceSourceParsing:
    """Surface parser handles 'source: ViewName' syntax."""

    def test_parse_surface_with_source(self) -> None:
        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

view CompanyListView "Company List View":
  source: Company
  fields:
    name: str(200)

surface company_list "Company List":
  uses entity Company
  source: CompanyListView
  mode: list
  section main:
    field name "Name"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surfaces = fragment.surfaces
        assert len(surfaces) == 1
        assert surfaces[0].name == "company_list"
        assert surfaces[0].view_ref == "CompanyListView"
        assert surfaces[0].entity_ref == "Company"
        assert surfaces[0].mode == ir.SurfaceMode.LIST

    def test_parse_surface_without_source(self) -> None:
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title "Title"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surfaces = fragment.surfaces
        assert len(surfaces) == 1
        assert surfaces[0].view_ref is None


# ---------------------------------------------------------------------------
# Linker validation tests
# ---------------------------------------------------------------------------


def _build_module_ir(dsl: str) -> ir.ModuleIR:
    """Parse DSL text into a ModuleIR for linker tests."""
    module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    return ir.ModuleIR(
        name=module_name or "test",
        file=Path("test.dsl"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )


class TestLinkerViewRefValidation:
    """Linker validates view_ref on surfaces."""

    def test_valid_view_ref(self) -> None:
        from dazzle.core.linker import build_appspec

        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

view CompanyListView "Company List View":
  source: Company
  fields:
    name: str(200)

surface company_list "Company List":
  uses entity Company
  source: CompanyListView
  mode: list
  section main:
    field name "Name"
"""
        module = _build_module_ir(dsl)
        appspec = build_appspec([module], "test_app")
        assert len(appspec.surfaces) == 1
        assert appspec.surfaces[0].view_ref == "CompanyListView"

    def test_unknown_view_ref_error(self) -> None:
        from dazzle.core.linker import build_appspec

        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

surface company_list "Company List":
  uses entity Company
  source: NonExistentView
  mode: list
  section main:
    field name "Name"
"""
        module = _build_module_ir(dsl)
        with pytest.raises(Exception, match="unknown view.*NonExistentView"):
            build_appspec([module], "test_app")

    def test_view_source_entity_mismatch_error(self) -> None:
        from dazzle.core.linker import build_appspec

        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

entity Task "Task":
  id: uuid pk
  title: str(200) required

view TaskView "Task View":
  source: Task
  fields:
    title: str(200)

surface company_list "Company List":
  uses entity Company
  source: TaskView
  mode: list
  section main:
    field name "Name"
"""
        module = _build_module_ir(dsl)
        with pytest.raises(Exception, match="source entity.*Task.*does not match.*Company"):
            build_appspec([module], "test_app")


# ---------------------------------------------------------------------------
# QueryBuilder select_fields tests
# ---------------------------------------------------------------------------


class TestQueryBuilderProjection:
    """QueryBuilder uses select_fields for projection."""

    def test_default_select_star(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Company")
        sql, _params = builder.build_select()
        assert "SELECT *" in sql

    def test_select_with_fields(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Company")
        builder.select_fields = ["id", "name", "status"]
        sql, _params = builder.build_select()
        assert "SELECT" in sql
        assert '"id"' in sql
        assert '"name"' in sql
        assert '"status"' in sql
        assert "*" not in sql

    def test_select_count_ignores_fields(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Company")
        builder.select_fields = ["id", "name"]
        sql, _params = builder.build_select(count_only=True)
        assert "COUNT(*)" in sql


# ---------------------------------------------------------------------------
# Route handler select_fields threading tests
# ---------------------------------------------------------------------------


class TestListHandlerProjection:
    """create_list_handler passes select_fields through."""

    @pytest.mark.asyncio
    async def test_select_fields_passed_to_service(self) -> None:
        """Verify select_fields is passed through the handler to service.execute()."""

        class MockService:
            def __init__(self) -> None:
                self.last_kwargs: dict = {}

            async def execute(self, **kwargs: object) -> dict:
                self.last_kwargs = kwargs
                return {"items": [], "total": 0, "page": 1, "page_size": 20}

        class MockRequest:
            query_params: dict = {}

            class headers:
                @staticmethod
                def get(key: str, default: str = "") -> str:
                    return ""

            class state:
                pass

        try:
            from dazzle_back.runtime.route_generator import create_list_handler
        except ImportError:
            pytest.skip("FastAPI not available")

        service = MockService()
        handler = create_list_handler(
            service,
            select_fields=["id", "name", "status"],
        )

        request = MockRequest()
        result = await handler(
            request=request, page=1, page_size=20, sort=None, dir="asc", search=None
        )
        assert service.last_kwargs.get("select_fields") == ["id", "name", "status"]
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_no_select_fields_by_default(self) -> None:
        """Without select_fields, None is passed."""

        class MockService:
            def __init__(self) -> None:
                self.last_kwargs: dict = {}

            async def execute(self, **kwargs: object) -> dict:
                self.last_kwargs = kwargs
                return {"items": [], "total": 0, "page": 1, "page_size": 20}

        class MockRequest:
            query_params: dict = {}

            class headers:
                @staticmethod
                def get(key: str, default: str = "") -> str:
                    return ""

            class state:
                pass

        try:
            from dazzle_back.runtime.route_generator import create_list_handler
        except ImportError:
            pytest.skip("FastAPI not available")

        service = MockService()
        handler = create_list_handler(service)

        request = MockRequest()
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)
        assert service.last_kwargs.get("select_fields") is None
