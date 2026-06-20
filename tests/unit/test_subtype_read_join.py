"""#1217 follow-up — Repository.read() JOINs to base for polymorphic-child entities.

Mirrors test_subtype_of_query.py for the read-by-id path. Without this JOIN,
the subtype_panel renderer (v0.71.186) receives only child columns in
detail.item and can't see `kind` to dispatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


def _build_subtype_back_entities() -> dict[str, Any]:
    """Parse + link Asset/Vehicle DSL; return back-layer entities by name."""
    from dazzle.core import ir
    from dazzle.core.dsl_parser_impl import parse_dsl
    from dazzle.core.linker import build_appspec
    from dazzle.http.converters import convert_entities

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
"""
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
    appspec = build_appspec([module], root_module_name=module.name)
    back_entities = convert_entities(appspec.domain.entities)
    return {e.name: e for e in back_entities}


def _mock_db_manager_capturing() -> tuple[MagicMock, list[str]]:
    """Mock backend that captures every executed SQL string."""
    executed_sql: list[str] = []
    cursor = MagicMock()

    def _record(sql: str, params: Any = None) -> None:
        executed_sql.append(sql)

    cursor.execute = MagicMock(side_effect=_record)
    cursor.fetchone = MagicMock(return_value=None)
    cursor.fetchall = MagicMock(return_value=[])

    conn = MagicMock()
    conn.cursor.return_value = cursor

    db = MagicMock()
    db.placeholder = "%s"
    db.connection.return_value.__enter__.return_value = conn
    db.connection.return_value.__exit__.return_value = False
    db.get_persistent_connection.return_value = conn
    return db, executed_sql


class TestSubtypeReadJoin:
    """Repository.read on a polymorphic-child entity must JOIN to base.

    Mirrors the list-path JOIN injection at repository.py:1015-1023.
    """

    @pytest.mark.asyncio
    async def test_read_on_child_emits_join_and_pulls_base_columns(self) -> None:
        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]
        vehicle_spec = entities["Vehicle"]

        class VehicleModel(BaseModel):
            id: str | None = None
            wheels: int | None = None
            vin: str | None = None

        db, executed_sql = _mock_db_manager_capturing()
        repo = Repository(
            db_manager=db,
            entity_spec=vehicle_spec,
            model_class=VehicleModel,
            base_entity_spec=asset_spec,
        )

        # Sanity: __init__ cached the JOIN.
        assert repo._subtype_join_sql is not None
        assert '"Asset"' in repo._subtype_join_sql

        await repo.read(uuid4())

        assert len(executed_sql) == 1
        sql = executed_sql[0]
        # JOIN to base on shared id.
        assert 'JOIN "Asset" ON "Vehicle"."id" = "Asset"."id"' in sql
        # Base columns by-name (except id which already exists on child).
        assert '"Asset"."acquired_at" AS "acquired_at"' in sql
        assert '"Asset"."location" AS "location"' in sql
        # Source-qualified id predicate (joined table also has id).
        assert '"Vehicle"."id" = ' in sql
        # `{table}.*` rather than bare `*`.
        assert '"Vehicle".*' in sql

    @pytest.mark.asyncio
    async def test_read_on_non_subtype_entity_uses_plain_select(self) -> None:
        """A base or plain entity (no subtype_of) must not gain a JOIN."""
        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]  # base, NOT a child

        class AssetModel(BaseModel):
            id: str | None = None
            acquired_at: Any = None
            location: str | None = None
            kind: str | None = None

        db, executed_sql = _mock_db_manager_capturing()
        repo = Repository(
            db_manager=db,
            entity_spec=asset_spec,
            model_class=AssetModel,
            base_entity_spec=None,
        )

        assert repo._subtype_join_sql is None

        await repo.read(uuid4())

        assert len(executed_sql) == 1
        sql = executed_sql[0]
        assert "JOIN " not in sql
        # Existing non-subtype shape is unchanged.
        assert sql.startswith("SELECT * FROM ")

    @pytest.mark.asyncio
    async def test_read_on_child_with_row_returns_dict_with_base_fields(self) -> None:
        """When a row is returned, the dict must include base columns so the
        subtype_panel renderer can read `kind` and dispatch."""
        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]
        vehicle_spec = entities["Vehicle"]

        class VehicleModel(BaseModel):
            id: str | None = None
            wheels: int | None = None
            vin: str | None = None

        db, _executed_sql = _mock_db_manager_capturing()
        # Override fetchone to return a row dict that mimics a JOIN result.
        the_id = uuid4()
        cursor = db.connection.return_value.__enter__.return_value.cursor.return_value
        cursor.fetchone.return_value = {
            "id": str(the_id),
            "wheels": 4,
            "vin": "1HGCM82633A123456",
            "acquired_at": None,
            "location": "Warehouse 7",
            "kind": "Vehicle",
        }

        repo = Repository(
            db_manager=db,
            entity_spec=vehicle_spec,
            model_class=VehicleModel,
            base_entity_spec=asset_spec,
        )

        result = await repo.read(the_id)

        # When subtype JOIN is in play, read() must return a dict so the
        # base fields survive into the renderer.
        assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
        assert result.get("kind") == "Vehicle"
        assert result.get("location") == "Warehouse 7"
        assert result.get("wheels") == 4
        assert result.get("vin") == "1HGCM82633A123456"
