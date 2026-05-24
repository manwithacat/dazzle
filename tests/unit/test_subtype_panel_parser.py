"""#1217 Phase 3e.v — parser + linker tests for `subtype_panel:` block."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import LinkError
from dazzle.core.linker import build_appspec


def _link(dsl: str) -> ir.AppSpec:
    """Parse + link a single-file DSL string. Returns the linked AppSpec or raises."""
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


BASE_DSL = """\
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

"""


class TestSubtypePanelParses:
    def test_card_with_subtype_panel(self) -> None:
        dsl = (
            BASE_DSL
            + """\
surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail
"""
        )
        appspec = _link(dsl)
        card = next(s for s in appspec.surfaces if s.name == "asset_card")
        section = card.sections[0]
        assert section.subtype_panel is not None
        kinds = {b.when_kind for b in section.subtype_panel.branches}
        assert kinds == {"vehicle", "building"}
        by_kind = {b.when_kind: b.include_surface for b in section.subtype_panel.branches}
        assert by_kind["vehicle"] == "vehicle_detail"
        assert by_kind["building"] == "building_detail"


class TestSubtypePanelLinkerRule9:
    def test_unknown_kind_rejected(self) -> None:
        dsl = (
            BASE_DSL
            + """\
surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    subtype_panel:
      when kind = ufo: include surface vehicle_detail
"""
        )
        with pytest.raises(LinkError, match="E_SUBTYPE_PANEL_UNKNOWN_KIND"):
            _link(dsl)

    def test_subtype_panel_on_non_base_rejected(self) -> None:
        dsl = (
            BASE_DSL
            + """\
surface vehicle_card "Vehicle Card":
  uses entity Vehicle
  mode: view
  section main:
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
"""
        )
        with pytest.raises(LinkError, match="subtype_panel|polymorphic"):
            _link(dsl)


class TestSubtypePanelIncompleteWarning:
    def test_missing_kind_emits_warning(self) -> None:
        """A subtype_panel that lists vehicle but omits building should emit a
        W_SUBTYPE_PANEL_INCOMPLETE warning into ``AppSpec.metadata['link_warnings']``.

        Convention found: the linker already attaches `unused_import_warnings`
        to ``metadata['link_warnings']`` (see linker.py around line 127/308).
        Subtype-panel warnings join the same list.
        """
        dsl = (
            BASE_DSL
            + """\
surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
"""
        )
        appspec = _link(dsl)
        warnings = appspec.metadata.get("link_warnings", [])
        assert any("W_SUBTYPE_PANEL_INCOMPLETE" in str(w) for w in warnings), (
            f"expected W_SUBTYPE_PANEL_INCOMPLETE in {warnings!r}"
        )
        assert any("building" in str(w) for w in warnings)
