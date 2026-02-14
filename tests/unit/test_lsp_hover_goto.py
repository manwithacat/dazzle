"""Tests for LSP hover and go-to-definition across all constructs (issue #235)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.core import ir


def _make_minimal_appspec(**kwargs: Any) -> ir.AppSpec:
    """Build a minimal AppSpec with specified collections."""
    return ir.AppSpec(
        name="test",
        title="Test",
        domain=ir.DomainSpec(entities=kwargs.get("entities", [])),
        surfaces=kwargs.get("surfaces", []),
        views=kwargs.get("views", []),
        enums=kwargs.get("enums", []),
        processes=kwargs.get("processes", []),
        ledgers=kwargs.get("ledgers", []),
        transactions=kwargs.get("transactions", []),
        workspaces=kwargs.get("workspaces", []),
        experiences=kwargs.get("experiences", []),
        personas=kwargs.get("personas", []),
        stories=kwargs.get("stories", []),
        webhooks=kwargs.get("webhooks", []),
        approvals=kwargs.get("approvals", []),
        slas=kwargs.get("slas", []),
        islands=kwargs.get("islands", []),
    )


class TestBuildNameIndex:
    """_build_name_index creates a complete lookup dict."""

    def test_entities_indexed(self) -> None:
        from dazzle.lsp.server import _build_name_index

        entity = ir.EntitySpec(name="Task", fields=[])
        appspec = _make_minimal_appspec(entities=[entity])
        index = _build_name_index(appspec)
        assert "Task" in index
        assert index["Task"] == ("entity", entity)

    def test_surfaces_indexed(self) -> None:
        from dazzle.lsp.server import _build_name_index

        surface = ir.SurfaceSpec(name="task_list", mode=ir.SurfaceMode.LIST)
        appspec = _make_minimal_appspec(surfaces=[surface])
        index = _build_name_index(appspec)
        assert "task_list" in index
        assert index["task_list"][0] == "surface"

    def test_views_indexed(self) -> None:
        from dazzle.lsp.server import _build_name_index

        view = ir.ViewSpec(name="TaskView", source_entity="Task", fields=[])
        appspec = _make_minimal_appspec(views=[view])
        index = _build_name_index(appspec)
        assert "TaskView" in index
        assert index["TaskView"][0] == "view"

    def test_multiple_types_indexed(self) -> None:
        from dazzle.lsp.server import _build_name_index

        entity = ir.EntitySpec(name="Company", fields=[])
        surface = ir.SurfaceSpec(name="company_list", mode=ir.SurfaceMode.LIST)
        appspec = _make_minimal_appspec(entities=[entity], surfaces=[surface])
        index = _build_name_index(appspec)
        assert len(index) == 2
        assert "Company" in index
        assert "company_list" in index

    def test_empty_appspec(self) -> None:
        from dazzle.lsp.server import _build_name_index

        appspec = _make_minimal_appspec()
        index = _build_name_index(appspec)
        assert index == {}


class TestGenericHover:
    """_format_generic_hover produces markdown for any construct."""

    def test_view_hover(self) -> None:
        from dazzle.lsp.server import _format_generic_hover

        view = ir.ViewSpec(
            name="TaskView",
            title="Task View",
            source_entity="Task",
            fields=[ir.ViewFieldSpec(name="title", type="str(200)")],
        )
        result = _format_generic_hover("view", view)
        assert "TaskView" in result
        assert "Task View" in result
        assert "Source entity" in result
        assert "Task" in result

    def test_enum_hover(self) -> None:
        from dazzle.core.ir.enums import EnumValueSpec
        from dazzle.lsp.server import _format_generic_hover

        enum = ir.EnumSpec(
            name="Status",
            values=[
                EnumValueSpec(name="draft"),
                EnumValueSpec(name="active"),
                EnumValueSpec(name="archived"),
            ],
        )
        result = _format_generic_hover("enum", enum)
        assert "Status" in result
        assert "draft" in result
        assert "active" in result

    def test_minimal_hover(self) -> None:
        """Construct with just a name still produces valid hover."""
        from dazzle.lsp.server import _format_generic_hover

        # Use a simple object with just 'name'
        class SimpleSpec:
            name = "Foo"
            title = None

        result = _format_generic_hover("custom", SimpleSpec())
        assert "Foo" in result
        assert "custom" in result


class TestFindDefinitionInFile:
    """_find_definition_in_file works for all construct types."""

    def test_find_entity(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text('entity Task "Task":\n  id: uuid pk\n')
        loc = _find_definition_in_file(dsl, "Task")
        assert loc is not None
        assert loc.range.start.line == 0

    def test_find_view(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text('view TaskView "Task View":\n  source: Task\n')
        loc = _find_definition_in_file(dsl, "TaskView")
        assert loc is not None
        assert loc.range.start.line == 0

    def test_find_process(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text(
            'entity Foo "Foo":\n  id: uuid pk\n\nprocess OrderFlow "Order Flow":\n  state pending:\n'
        )
        loc = _find_definition_in_file(dsl, "OrderFlow")
        assert loc is not None
        assert loc.range.start.line == 3

    def test_find_ledger(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text('ledger Revenue "Revenue":\n  account_code: 1001\n')
        loc = _find_definition_in_file(dsl, "Revenue")
        assert loc is not None

    def test_not_found(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text('entity Task "Task":\n  id: uuid pk\n')
        loc = _find_definition_in_file(dsl, "NonExistent")
        assert loc is None

    def test_selection_range_on_name(self, tmp_path: Path) -> None:
        from dazzle.lsp.server import _find_definition_in_file

        dsl = tmp_path / "test.dsl"
        dsl.write_text('entity Task "Task":\n  id: uuid pk\n')
        loc = _find_definition_in_file(dsl, "Task")
        assert loc is not None
        # "entity " = 7 chars, "Task" = 4 chars -> range should be [7, 11)
        assert loc.range.start.character == 7
        assert loc.range.end.character == 11
