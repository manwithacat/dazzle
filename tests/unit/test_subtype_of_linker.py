"""#1217 Phase 3e.ii — linker validation tests for `subtype_of:`.

One test per diagnostic from spec §5. The 11 rules are:
  E_SUBTYPE_OF_UNKNOWN_BASE       — base name doesn't resolve
  E_SUBTYPE_OF_CYCLE              — cycle in subtype graph
  E_SUBTYPE_OF_MULTILEVEL         — A subtype_of B subtype_of C
  (rule 4: single-parent — parser-enforced via single-identifier check)
  (rule 5: folds into rule 3)
  E_SUBTYPE_DUPLICATE_PK          — child declares `pk`
  E_SUBTYPE_KIND_RESERVED         — base declares `kind` field
  (rule 8: closed-set — computed, no diagnostic)
  W_SUBTYPE_PANEL_INCOMPLETE / E_SUBTYPE_PANEL_UNKNOWN_KIND — surface rule (slice 3e.v)
  E_SUBTYPE_SOFT_DELETE_ON_CHILD  — child declares soft_delete
  E_SUBTYPE_GRANT_INCOMPLETE      — grant on child (separate Task 10)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import LinkError
from dazzle.core.linker import build_appspec


def _link(dsl: str) -> ir.AppSpec:
    """Parse + link in one step, surfacing LinkError if any rule fires."""
    path = Path("test.dz")
    module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, path)
    module = ir.ModuleIR(
        name=module_name or "test",
        file=path,
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )
    return build_appspec([module], root_module_name=module.name)


class TestSubtypeLinkerRule1_UnknownBase:
    def test_unknown_base_rejected(self) -> None:
        dsl = """\
module test
app a "A"

entity Vehicle "Vehicle":
  id: uuid pk
  subtype_of: NonExistent
  wheels: int required
"""
        with pytest.raises(LinkError, match="E_SUBTYPE_OF_UNKNOWN_BASE"):
            _link(dsl)


class TestSubtypeLinkerRule2_NoCycle:
    def test_self_cycle_rejected(self) -> None:
        dsl = """\
module test
app a "A"

entity Vehicle "Vehicle":
  id: uuid pk
  subtype_of: Vehicle
  wheels: int required
"""
        with pytest.raises(LinkError, match="E_SUBTYPE_OF_CYCLE"):
            _link(dsl)


class TestSubtypeLinkerRule3_NoMultilevel:
    def test_three_level_rejected(self) -> None:
        dsl = """\
module test
app a "A"

entity Vehicle "Vehicle":
  subtype_of: PoweredAsset
  wheels: int required

entity PoweredAsset "PoweredAsset":
  subtype_of: Asset
  power_source: str(40) required

entity Asset "Asset":
  id: uuid pk
"""
        with pytest.raises(LinkError, match="E_SUBTYPE_OF_MULTILEVEL"):
            _link(dsl)


class TestSubtypeLinkerRule6_NoDuplicatePK:
    def test_child_declares_pk_rejected(self) -> None:
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  id: uuid pk
  subtype_of: Asset
  wheels: int required
"""
        with pytest.raises(LinkError, match="E_SUBTYPE_DUPLICATE_PK"):
            _link(dsl)


class TestSubtypeLinkerRule7_KindReserved:
    def test_base_declares_kind_rejected(self) -> None:
        # `kind` is parser-reserved, so the only path to a base with a user-declared
        # `kind` field is programmatic IR mutation (archetype expansion, fixtures,
        # tooling). The linker still owes a defence-in-depth check.
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
"""
        path = Path("test.dz")
        module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, path)
        # Inject a colliding `kind` field on the base entity (frozen-model copy).
        asset = next(e for e in fragment.entities if e.name == "Asset")
        from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind

        polluted = asset.model_copy(
            update={
                "fields": [
                    *asset.fields,
                    FieldSpec(
                        name="kind",
                        type=FieldType(kind=FieldTypeKind.STR, max_length=40),
                        modifiers=[FieldModifier.REQUIRED],
                    ),
                ]
            }
        )
        new_entities = [polluted if e.name == "Asset" else e for e in fragment.entities]
        polluted_fragment = fragment.model_copy(update={"entities": new_entities})
        module = ir.ModuleIR(
            name=module_name or "test",
            file=path,
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=polluted_fragment,
        )
        with pytest.raises(LinkError, match="E_SUBTYPE_KIND_RESERVED"):
            build_appspec([module], root_module_name=module.name)


class TestSubtypeLinkerRule10_SoftDeleteOnChild:
    def test_child_soft_delete_rejected(self) -> None:
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  subtype_of: Asset
  soft_delete
  wheels: int required
"""
        with pytest.raises(LinkError, match="E_SUBTYPE_SOFT_DELETE_ON_CHILD"):
            _link(dsl)


class TestSubtypeLinkerHappyPath:
    def test_subtype_children_populated_and_kind_synthesised(self) -> None:
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
"""
        appspec = _link(dsl)
        entities = {e.name: e for e in appspec.domain.entities}
        # Base back-pointer populated, alphabetical sort.
        assert entities["Asset"].subtype_children == ("Building", "Vehicle")
        assert entities["Asset"].is_polymorphic_base is True
        # Child preserved.
        assert entities["Vehicle"].subtype_of == "Asset"
        assert entities["Vehicle"].is_polymorphic_child is True
        # Kind field synthesised on base.
        kind_field = next((f for f in entities["Asset"].fields if f.name == "kind"), None)
        assert kind_field is not None
        assert kind_field.type.kind == ir.FieldTypeKind.ENUM
        assert sorted(kind_field.type.enum_values or []) == ["building", "vehicle"]
