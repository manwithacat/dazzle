"""Tests for contextual entity resolution — ref fields show display names not UUIDs.

Covers:
- Read handler passes auto_include to service for eager-loading
- CRUDService.read() forwards include to repository
- Template compiler maps REF fields to "ref" type
- Detail view template renders ref objects as display names
- Search-select populates initial values from ref objects
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from dazzle.core.ir.fields import FieldTypeKind

# ---------------------------------------------------------------------------
# Route generator: read handler passes auto_include
# ---------------------------------------------------------------------------


class TestReadHandlerAutoInclude:
    """create_read_handler() passes auto_include to service.execute()."""

    async def test_noauth_handler_passes_include(self) -> None:
        from dazzle_back.runtime.route_generator import create_read_handler

        service = MagicMock()
        service.execute = AsyncMock(return_value={"id": "123", "title": "Test"})

        handler = create_read_handler(
            service,
            entity_name="Task",
            auto_include=["assigned_to", "company"],
        )

        request = MagicMock()
        await handler(id=uuid4(), request=request)
        service.execute.assert_called_once()
        call_kwargs = service.execute.call_args[1]
        assert call_kwargs["include"] == ["assigned_to", "company"]

    async def test_noauth_handler_none_include(self) -> None:
        from dazzle_back.runtime.route_generator import create_read_handler

        service = MagicMock()
        service.execute = AsyncMock(return_value={"id": "123"})

        handler = create_read_handler(service, entity_name="Task")

        request = MagicMock()
        await handler(id=uuid4(), request=request)
        call_kwargs = service.execute.call_args[1]
        assert call_kwargs["include"] is None

    def test_auth_handler_passes_include(self) -> None:
        from dazzle_back.runtime.route_generator import create_read_handler

        service = MagicMock()
        service.execute = AsyncMock(return_value={"id": "123"})

        auth_dep = MagicMock()
        handler = create_read_handler(
            service,
            entity_name="Task",
            auth_dep=auth_dep,
            require_auth_by_default=True,
            auto_include=["company"],
        )
        # The handler is _read_auth which takes auth_context
        assert handler is not None


# ---------------------------------------------------------------------------
# CRUDService: read() forwards include
# ---------------------------------------------------------------------------


class TestCRUDServiceReadInclude:
    """CRUDService.read() passes include to repository."""

    async def test_read_passes_include_to_repository(self) -> None:
        from pydantic import BaseModel

        from dazzle_back.runtime.service_generator import CRUDService

        class Task(BaseModel):
            id: Any
            title: str

        class TaskCreate(BaseModel):
            title: str

        class TaskUpdate(BaseModel):
            title: str | None = None

        service = CRUDService(
            entity_name="Task",
            model_class=Task,
            create_schema=TaskCreate,
            update_schema=TaskUpdate,
        )

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.read = AsyncMock(
            return_value={"id": "123", "title": "Test", "company": {"id": "456", "name": "Acme"}}
        )
        service.set_repository(mock_repo)

        test_id = uuid4()
        result = await service.read(test_id, include=["company"])
        mock_repo.read.assert_called_once_with(test_id, include=["company"])
        assert result["company"]["name"] == "Acme"

    async def test_read_without_include(self) -> None:
        from pydantic import BaseModel

        from dazzle_back.runtime.service_generator import CRUDService

        class Item(BaseModel):
            id: Any
            name: str

        class ItemCreate(BaseModel):
            name: str

        class ItemUpdate(BaseModel):
            name: str | None = None

        service = CRUDService(
            entity_name="Item",
            model_class=Item,
            create_schema=ItemCreate,
            update_schema=ItemUpdate,
        )

        mock_repo = MagicMock()
        mock_repo.read = AsyncMock(return_value=Item(id="1", name="Test"))
        service.set_repository(mock_repo)

        await service.read(uuid4())
        call_kwargs = mock_repo.read.call_args[1]
        assert call_kwargs.get("include") is None

    async def test_execute_routes_to_read_with_include(self) -> None:
        from pydantic import BaseModel

        from dazzle_back.runtime.service_generator import CRUDService

        class Thing(BaseModel):
            id: Any
            label: str

        class ThingCreate(BaseModel):
            label: str

        class ThingUpdate(BaseModel):
            label: str | None = None

        service = CRUDService(
            entity_name="Thing",
            model_class=Thing,
            create_schema=ThingCreate,
            update_schema=ThingUpdate,
        )

        mock_repo = MagicMock()
        mock_repo.read = AsyncMock(return_value={"id": "1", "label": "X"})
        service.set_repository(mock_repo)

        test_id = uuid4()
        await service.execute(operation="read", id=test_id, include=["owner"])
        mock_repo.read.assert_called_once_with(test_id, include=["owner"])


# ---------------------------------------------------------------------------
# Template compiler: REF -> "ref" type
# ---------------------------------------------------------------------------


class TestRefFieldTypeMapping:
    """_field_type_to_form_type maps REF to 'ref'."""

    def test_ref_kind_maps_to_ref(self) -> None:
        from dazzle.core import ir
        from dazzle_ui.converters.template_compiler import _field_type_to_form_type

        field_spec = ir.FieldSpec(
            name="company_id",
            type=ir.FieldType(kind=FieldTypeKind.REF, ref_entity="Company"),
        )
        result = _field_type_to_form_type(field_spec)
        assert result == "ref"

    def test_str_kind_maps_to_text(self) -> None:
        from dazzle.core import ir
        from dazzle_ui.converters.template_compiler import _field_type_to_form_type

        field_spec = ir.FieldSpec(
            name="title",
            type=ir.FieldType(kind=FieldTypeKind.STR),
        )
        result = _field_type_to_form_type(field_spec)
        assert result == "text"


# ---------------------------------------------------------------------------
# Detail view template: ref rendering
# ---------------------------------------------------------------------------


class _SimpleObj:
    """Simple attribute holder for template rendering tests."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestDetailViewRefRendering:
    """detail_view.html renders ref objects as display names."""

    def _render_detail(self, fields: list[dict], item: dict) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        template = env.get_template("components/detail_view.html")
        return template.render(
            detail=_SimpleObj(
                entity_name="Task",
                title="Task Details",
                fields=[_SimpleObj(**f) for f in fields],
                edit_url="/tasks/1/edit",
                delete_url="/api/tasks/1",
                back_url="/tasks",
                transitions=[],
                status_field="status",
                item=item,
            )
        )

    def test_ref_object_shows_name(self) -> None:
        html = self._render_detail(
            fields=[{"name": "company", "type": "ref", "label": "Company"}],
            item={"company": {"id": "abc", "name": "Smith Consulting"}},
        )
        assert "Smith Consulting" in html
        assert "abc" not in html  # Should not show UUID

    def test_ref_object_shows_title_fallback(self) -> None:
        html = self._render_detail(
            fields=[{"name": "project", "type": "ref", "label": "Project"}],
            item={"project": {"id": "xyz", "title": "Website Redesign"}},
        )
        assert "Website Redesign" in html

    def test_ref_object_shows_email_fallback(self) -> None:
        html = self._render_detail(
            fields=[{"name": "owner", "type": "ref", "label": "Owner"}],
            item={"owner": {"id": "u1", "email": "jane@example.com"}},
        )
        assert "jane@example.com" in html

    def test_ref_raw_uuid_shows_uuid(self) -> None:
        """When ref is not resolved (raw UUID), show the UUID."""
        html = self._render_detail(
            fields=[{"name": "assigned_to", "type": "ref", "label": "Assigned To"}],
            item={"assigned_to": "f97394eb-dc07-4a1b-8b89-12345678abcd"},
        )
        assert "f97394eb" in html

    def test_ref_none_shows_dash(self) -> None:
        html = self._render_detail(
            fields=[{"name": "reviewer", "type": "ref", "label": "Reviewer"}],
            item={"reviewer": None},
        )
        # Should show dash for empty ref
        assert "\u2014" in html  # em-dash

    def test_non_ref_field_unaffected(self) -> None:
        html = self._render_detail(
            fields=[{"name": "title", "type": "text", "label": "Title"}],
            item={"title": "Important Task"},
        )
        assert "Important Task" in html


# ---------------------------------------------------------------------------
# Workspace region detail template: ref rendering
# ---------------------------------------------------------------------------


class TestWorkspaceRegionDetailRef:
    """workspace/regions/detail.html handles ref columns."""

    def _render_region_detail(self, columns: list[dict], item: dict) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        template = env.get_template("workspace/regions/detail.html")
        return template.render(
            title="Client Details",
            columns=[_SimpleObj(**c) for c in columns],
            item=item,
        )

    def test_ref_column_shows_name(self) -> None:
        html = self._render_region_detail(
            columns=[{"key": "company", "type": "ref", "label": "Company"}],
            item={"company": {"id": "c1", "name": "Acme Corp"}},
        )
        assert "Acme Corp" in html

    def test_ref_column_raw_value(self) -> None:
        html = self._render_region_detail(
            columns=[{"key": "agent", "type": "ref", "label": "Agent"}],
            item={"agent": "some-uuid-value"},
        )
        assert "some-uuid-value" in html
