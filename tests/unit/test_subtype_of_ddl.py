"""#1217 Phase 3e.iii — TPT DDL emission for `subtype_of:`.

Verifies that ``build_metadata`` emits table-per-type (TPT) DDL when
``subtype_of:`` is declared:

- Base table is emitted unchanged (the linker-synthesised ``kind`` column
  rides along on ``entity.fields`` for free).
- Child table contains only subtype-specific fields. Its ``id`` column is
  BOTH primary key AND foreign key to base.id with ``ON DELETE CASCADE``.
- Child table excludes base-owned fields (e.g. ``acquired_at``).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata

# Canonical Asset / Vehicle / Building shape from test_subtype_of_linker.py.
_TPT_DSL = """\
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


def _link(dsl: str) -> ir.AppSpec:
    """Parse + link in one step (mirrors test_subtype_of_linker.py)."""
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


def _build_md() -> object:
    appspec = _link(_TPT_DSL)
    back_entities = convert_entities(list(appspec.domain.entities))
    return build_metadata(back_entities)


def test_base_table_has_kind_column() -> None:
    """Linker synthesises the ``kind`` enum field on the base; build_metadata
    must round-trip it as a column on the Asset table."""
    md = _build_md()
    table = md.tables["Asset"]  # type: ignore[attr-defined]
    assert "kind" in table.c
    # Enum is stored as TEXT in sa_schema (`_field_type_to_sa` returns sa.Text
    # for FieldTypeKind.ENUM), so just assert existence + nullability/type
    # discoverable rather than pinning the SQLAlchemy class.
    assert table.c.kind.nullable is False


def test_child_table_shares_pk_via_fk() -> None:
    """Vehicle.id must be both PK and a FK to Asset.id with ON DELETE CASCADE."""
    md = _build_md()
    table = md.tables["Vehicle"]  # type: ignore[attr-defined]

    id_col = table.c.id
    assert id_col.primary_key is True

    fks = list(id_col.foreign_keys)
    assert len(fks) == 1, f"expected exactly one FK on Vehicle.id, got {len(fks)}"
    fk = fks[0]
    assert fk.column.table.name == "Asset"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_child_table_has_only_subtype_specific_fields() -> None:
    """Vehicle must own its own ``wheels`` column but NOT the base-owned
    ``acquired_at`` or ``kind`` columns (those live on Asset)."""
    md = _build_md()
    table = md.tables["Vehicle"]  # type: ignore[attr-defined]

    col_names = set(table.c.keys())
    assert "wheels" in col_names
    assert "acquired_at" not in col_names
    assert "kind" not in col_names
    # id is shared via the FK, so it should be present.
    assert "id" in col_names
