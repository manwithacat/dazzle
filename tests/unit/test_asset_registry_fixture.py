"""#1217 Phase 3e.iv — regression tests for the asset_registry fixture.

Pin that the fixture parses, links, and emits subtype-aware DDL without
errors. These tests block accidental fixture rot when future slices touch
parser / linker / DDL.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

_FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "asset_registry"


def _load_fixture() -> ir.AppSpec:
    dsl_files = sorted((_FIXTURE_ROOT / "dsl").glob("*.dsl"))
    return build_appspec(parse_modules(dsl_files), "asset_registry")


class TestAssetRegistryFixture:
    def test_fixture_parses_and_links(self) -> None:
        appspec = _load_fixture()
        entity_names = {e.name for e in appspec.domain.entities}
        # Base + 3 subtypes.
        for expected in ("Asset", "Vehicle", "Building", "Equipment"):
            assert expected in entity_names

    def test_asset_is_polymorphic_base_with_three_children(self) -> None:
        appspec = _load_fixture()
        asset = next(e for e in appspec.domain.entities if e.name == "Asset")
        assert asset.is_polymorphic_base is True
        # Linker populates subtype_children alphabetically.
        assert set(asset.subtype_children) == {"Vehicle", "Building", "Equipment"}

    def test_vehicle_is_polymorphic_child_of_asset(self) -> None:
        appspec = _load_fixture()
        vehicle = next(e for e in appspec.domain.entities if e.name == "Vehicle")
        assert vehicle.is_polymorphic_child is True
        assert vehicle.subtype_of == "Asset"

    def test_kind_field_synthesised_with_three_enum_values(self) -> None:
        appspec = _load_fixture()
        asset = next(e for e in appspec.domain.entities if e.name == "Asset")
        kind_field = next((f for f in asset.fields if f.name == "kind"), None)
        assert kind_field is not None
        assert kind_field.type.kind == ir.FieldTypeKind.ENUM
        assert sorted(kind_field.type.enum_values or []) == [
            "building",
            "equipment",
            "vehicle",
        ]

    def test_ddl_emits_tpt_tables_with_cascade_fk(self) -> None:
        """Subtype DDL (slice 3e.iii): each child gets its own table whose
        `id` is BOTH primary key AND a FK to the base's id with ON DELETE
        CASCADE.
        """
        from dazzle.back.converters.entity_converter import convert_entities
        from dazzle.back.runtime.sa_schema import build_metadata

        appspec = _load_fixture()
        entities = convert_entities(appspec.domain.entities)
        md = build_metadata(entities)

        # Base + each subtype emits its own table.
        for table_name in ("Asset", "Vehicle", "Building", "Equipment"):
            assert table_name in md.tables, f"missing table {table_name}"

        # Child id is FK-with-cascade to base id.
        vehicle_id = md.tables["Vehicle"].c.id
        assert vehicle_id.primary_key is True
        fks = list(vehicle_id.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "Asset"
        assert fks[0].ondelete == "CASCADE"


class TestAssetRegistrySurfaces:
    def test_asset_card_has_subtype_panel_with_three_branches(self) -> None:
        appspec = _load_fixture()
        card = next(s for s in appspec.surfaces if s.name == "asset_card")
        section = card.sections[0]
        assert section.subtype_panel is not None
        kinds = {b.when_kind for b in section.subtype_panel.branches}
        assert kinds == {"vehicle", "building", "equipment"}

    def test_subtype_panel_branches_map_to_per_subtype_surfaces(self) -> None:
        appspec = _load_fixture()
        card = next(s for s in appspec.surfaces if s.name == "asset_card")
        by_kind = {b.when_kind: b.include_surface for b in card.sections[0].subtype_panel.branches}
        assert by_kind == {
            "vehicle": "vehicle_detail",
            "building": "building_detail",
            "equipment": "equipment_detail",
        }

    def test_subtype_panel_resolver_returns_correct_surface(self) -> None:
        """Sanity-check the resolver helper against the canonical fixture."""
        from dazzle.render.subtype_panel import resolve_subtype_panel_surface

        appspec = _load_fixture()
        card = next(s for s in appspec.surfaces if s.name == "asset_card")
        section = card.sections[0]
        result = resolve_subtype_panel_surface(section, "vehicle", appspec)
        assert result is not None
        assert result.name == "vehicle_detail"

    def test_per_subtype_surfaces_have_subtype_specific_fields(self) -> None:
        appspec = _load_fixture()
        vd = next(s for s in appspec.surfaces if s.name == "vehicle_detail")
        field_names = {e.field_name for e in vd.sections[0].elements}
        assert field_names == {"wheels", "vin", "fuel_type"}


def test_subtype_panel_include_surfaces_not_flagged_dead() -> None:
    """#1411: surfaces referenced only via a `subtype_panel` branch's
    `include surface X` are alive — the extended-lint dead-construct detector
    must not flag them. (Regression: the fuzz sweep caught these as false dead.)
    """
    from dazzle.core.lint import lint_appspec

    appspec = _load_fixture()
    _errors, warnings, _relevance = lint_appspec(appspec, extended=True)
    dead = [w for w in warnings if "Dead construct" in w and "surface" in w]
    for name in ("building_detail", "equipment_detail", "vehicle_detail"):
        assert not any(name in w for w in dead), (
            f"surface '{name}' is used via subtype_panel but was flagged dead: {dead}"
        )
