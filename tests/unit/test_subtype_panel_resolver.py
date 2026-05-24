"""#1217 Phase 3e.v — `resolve_subtype_panel_surface` lookup tests.

Pin the dispatch primitive. The renderer integration (substituting the
resolved surface's content for the parent section's content) is a
follow-up — this test isolates the lookup contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec
from dazzle.render.subtype_panel import resolve_subtype_panel_surface


def _link(dsl: str) -> ir.AppSpec:
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


@pytest.fixture(scope="module")
def appspec() -> ir.AppSpec:
    dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk
  acquired_at: date required

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required

entity Building "Building":
  subtype_of: Asset
  floors: int required

surface vehicle_detail "Vehicle Detail":
  uses entity Vehicle
  mode: view
  section main:
    field wheels "Wheels"

surface building_detail "Building Detail":
  uses entity Building
  mode: view
  section main:
    field floors "Floors"

surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail
"""
    return _link(dsl)


def _asset_card_section(appspec: ir.AppSpec) -> ir.SurfaceSection:
    card = next(s for s in appspec.surfaces if s.name == "asset_card")
    return card.sections[0]


class TestResolveSubtypePanelSurface:
    def test_vehicle_kind_resolves_to_vehicle_detail(self, appspec: ir.AppSpec) -> None:
        section = _asset_card_section(appspec)
        result = resolve_subtype_panel_surface(section, "vehicle", appspec)
        assert result is not None
        assert result.name == "vehicle_detail"

    def test_building_kind_resolves_to_building_detail(self, appspec: ir.AppSpec) -> None:
        section = _asset_card_section(appspec)
        result = resolve_subtype_panel_surface(section, "building", appspec)
        assert result is not None
        assert result.name == "building_detail"

    def test_unknown_kind_returns_none(self, appspec: ir.AppSpec) -> None:
        section = _asset_card_section(appspec)
        result = resolve_subtype_panel_surface(section, "ufo", appspec)
        assert result is None

    def test_none_kind_returns_none(self, appspec: ir.AppSpec) -> None:
        section = _asset_card_section(appspec)
        result = resolve_subtype_panel_surface(section, None, appspec)
        assert result is None

    def test_section_without_subtype_panel_returns_none(self, appspec: ir.AppSpec) -> None:
        # Use vehicle_detail's section — it has no subtype_panel.
        vd = next(s for s in appspec.surfaces if s.name == "vehicle_detail")
        result = resolve_subtype_panel_surface(vd.sections[0], "vehicle", appspec)
        assert result is None
