"""#1217 renderer follow-up — subtype_panel augments dispatch ctx fields.

When a VIEW surface has section.subtype_panel and the row's kind matches a
branch, the dispatch ctx builder appends the per-subtype surface's fields
to the flat ctx["fields"] list. The fragment renderer stays section-ignorant.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec


@pytest.fixture(scope="module")
def appspec_with_subtype_panel() -> ir.AppSpec:
    """Parse + link a small subtype-panel fixture in-memory."""
    dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk
  acquired_at: date required
  location: str(120)

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
  vin: str(17) required

entity Building "Building":
  subtype_of: Asset
  floors: int required

surface vehicle_detail "Vehicle Detail":
  uses entity Vehicle
  mode: view
  section main:
    field wheels "Wheels"
    field vin "VIN"

surface building_detail "Building Detail":
  uses entity Building
  mode: view
  section main:
    field floors "Floors"

surface asset_card "Asset":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    field location "Location"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail
"""
    module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dz"))
    module = ir.ModuleIR(
        name=module_name or "test",
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        file=Path("test.dz"),
        fragment=fragment,
    )
    return build_appspec([module], root_module_name=module.name)


def _make_render_ctx(item: dict[str, Any]) -> SimpleNamespace:
    """Build a minimal render_ctx with `detail` shape consumed by _build_dispatch_ctx."""
    # detail.fields is the FieldContext list; detail.item is the row dict.
    # Use minimal stubs — _build_dispatch_ctx only reads `name`, `label`, `type`.
    detail = SimpleNamespace(
        item=item,
        fields=[
            SimpleNamespace(name="acquired_at", label="Acquired", type="date"),
            SimpleNamespace(name="location", label="Location", type="str"),
        ],
        entity_name="Asset",
        transitions=[],
        integration_actions=[],
        external_link_actions=[],
        edit_url=None,
        delete_url=None,
        back_url="/",
    )
    return SimpleNamespace(detail=detail, table=None, form=None)


def _make_services(appspec: ir.AppSpec) -> SimpleNamespace:
    return SimpleNamespace(app_spec=appspec)


def _get_surface(appspec: ir.AppSpec, name: str) -> ir.SurfaceSpec:
    return next(s for s in appspec.surfaces if s.name == name)


class TestSubtypePanelDispatchAugmentation:
    def test_vehicle_kind_appends_vehicle_detail_fields(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "asset_card")
        render_ctx = _make_render_ctx(
            {
                "id": "abc",
                "kind": "vehicle",
                "acquired_at": "2026-01-01",
                "location": "Garage",
                "wheels": 4,
                "vin": "1HG...",
            }
        )
        services = _make_services(appspec_with_subtype_panel)
        ctx = _build_dispatch_ctx(render_ctx, surface, services=services)
        field_keys = [f["key"] for f in ctx["fields"]]
        # Base fields present first (from detail.fields):
        assert "acquired_at" in field_keys
        assert "location" in field_keys
        # Per-subtype fields appended:
        assert "wheels" in field_keys
        assert "vin" in field_keys
        # Values pulled from item:
        wheels_field = next(f for f in ctx["fields"] if f["key"] == "wheels")
        assert wheels_field["value"] == 4

    def test_building_kind_appends_building_detail_fields(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "asset_card")
        render_ctx = _make_render_ctx(
            {
                "id": "abc",
                "kind": "building",
                "acquired_at": "2026-01-01",
                "location": "Site A",
                "floors": 3,
            }
        )
        services = _make_services(appspec_with_subtype_panel)
        ctx = _build_dispatch_ctx(render_ctx, surface, services=services)
        field_keys = [f["key"] for f in ctx["fields"]]
        assert "floors" in field_keys
        # Cross-kind fields NOT pulled in:
        assert "wheels" not in field_keys
        assert "vin" not in field_keys

    def test_unknown_kind_no_augmentation(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "asset_card")
        render_ctx = _make_render_ctx({"id": "abc", "kind": "ufo"})
        services = _make_services(appspec_with_subtype_panel)
        ctx = _build_dispatch_ctx(render_ctx, surface, services=services)
        field_keys = [f["key"] for f in ctx["fields"]]
        # Only base fields, no panel branch matched:
        assert field_keys == ["acquired_at", "location"]

    def test_missing_kind_no_augmentation(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "asset_card")
        render_ctx = _make_render_ctx({"id": "abc"})  # no kind
        services = _make_services(appspec_with_subtype_panel)
        ctx = _build_dispatch_ctx(render_ctx, surface, services=services)
        field_keys = [f["key"] for f in ctx["fields"]]
        assert "wheels" not in field_keys

    def test_no_services_graceful_fallback(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "asset_card")
        render_ctx = _make_render_ctx({"id": "abc", "kind": "vehicle"})
        # services not provided — must not crash, just skip augmentation
        ctx = _build_dispatch_ctx(render_ctx, surface)
        field_keys = [f["key"] for f in ctx["fields"]]
        assert "wheels" not in field_keys

    def test_surface_without_panel_unaffected(self, appspec_with_subtype_panel) -> None:
        from dazzle.back.runtime.page_routes import _build_dispatch_ctx

        surface = _get_surface(appspec_with_subtype_panel, "vehicle_detail")
        render_ctx = _make_render_ctx({"id": "abc", "kind": "vehicle", "wheels": 4})
        # vehicle_detail surface has no subtype_panel
        services = _make_services(appspec_with_subtype_panel)
        ctx = _build_dispatch_ctx(render_ctx, surface, services=services)
        # No panel → no augmentation; only the detail.fields entries appear:
        field_keys = [f["key"] for f in ctx["fields"]]
        assert field_keys == ["acquired_at", "location"]
