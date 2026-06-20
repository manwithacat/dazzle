"""#1217 Phase 3e.iv — QueryBuilder shape tests for subtype_of.

Tests pin the SQL emission shape for subtype-specific queries. No real DB —
this is a unit test of the builder + repository's SQL composition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from dazzle.http.runtime.query_builder import QueryBuilder


class TestQueryBuilderJoins:
    """The QueryBuilder already supports joins+extra_select_cols. These tests
    document the shape we'll use for subtype queries."""

    def test_subtype_join_shape_is_emittable_today(self) -> None:
        builder = QueryBuilder(table_name="Vehicle", placeholder_style="%s")
        builder.joins.append('JOIN "Asset" ON "Vehicle"."id" = "Asset"."id"')
        builder.extra_select_cols.extend(
            [
                '"Asset"."acquired_at" AS "acquired_at"',
                '"Asset"."location" AS "location"',
                '"Asset"."kind" AS "kind"',
            ]
        )
        sql, _params = builder.build_select()
        assert 'JOIN "Asset" ON "Vehicle"."id" = "Asset"."id"' in sql
        assert '"Asset"."acquired_at"' in sql
        assert '"Asset"."kind"' in sql
        # Source-table qualification kicks in when joins are present
        assert '"Vehicle".*' in sql


# Higher-level integration test: Repository.list emits the subtype JOIN.
# The implementation lives at repository.py:937+; we drive it through a real
# parse+link+convert to get a back-layer EntitySpec, then mock the database
# connection to capture the SQL that gets emitted.


def _build_subtype_back_entities() -> dict[str, Any]:
    """Parse + link Asset/Vehicle DSL; return back-layer entities (post-conversion)."""
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


def _mock_db_manager(fetched_rows: list[Any] | None = None, count: int = 0) -> MagicMock:
    """Mock PostgresBackend that captures SQL via cursor.execute call_args."""
    db = MagicMock()
    db.placeholder = "%s"
    cursor = MagicMock()
    cursor.rowcount = count
    # Count query returns (count,); list query returns rows.
    cursor.fetchone.return_value = (count,)
    cursor.fetchall.return_value = fetched_rows or []
    conn = MagicMock()
    conn.cursor.return_value = cursor
    db.connection.return_value.__enter__.return_value = conn
    db.connection.return_value.__exit__.return_value = False
    db.get_persistent_connection.return_value = conn
    db._mock_cursor = cursor  # test introspection hook
    return db


class TestRepositoryListSubtypeJoin:
    """Repository.list on a polymorphic-child entity must:
    - JOIN to the base table on shared id
    - SELECT base columns alongside child columns
    - Source-qualify the child table when joins are present
    """

    @pytest.mark.asyncio
    async def test_list_on_child_entity_emits_join_to_base(self) -> None:
        import asyncio as _asyncio  # noqa: F401

        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]
        vehicle_spec = entities["Vehicle"]

        class VehicleModel(BaseModel):
            id: str | None = None
            wheels: int | None = None
            vin: str | None = None
            acquired_at: Any = None
            location: str | None = None
            kind: str | None = None

        db = _mock_db_manager(fetched_rows=[], count=0)
        repo = Repository(
            db_manager=db,
            entity_spec=vehicle_spec,
            model_class=VehicleModel,
            base_entity_spec=asset_spec,
        )

        await repo.list(page=1, page_size=20)

        # Find the SELECT call (the second call after the COUNT).
        select_calls = [
            c
            for c in db._mock_cursor.execute.call_args_list
            if isinstance(c.args[0], str) and c.args[0].lstrip().startswith("SELECT ")
        ]
        # One COUNT + one SELECT.
        assert any("SELECT COUNT(*)" in c.args[0] for c in select_calls)
        select_sql = next(c.args[0] for c in select_calls if "COUNT(*)" not in c.args[0])

        # JOIN to base on shared id.
        assert 'JOIN "Asset" ON "Vehicle"."id" = "Asset"."id"' in select_sql
        # Base columns pulled by-name (except id which already exists on child).
        assert '"Asset"."acquired_at" AS "acquired_at"' in select_sql
        assert '"Asset"."location" AS "location"' in select_sql
        # Source-alias qualification on the child's bare `.*`.
        assert '"Vehicle".*' in select_sql

    @pytest.mark.asyncio
    async def test_list_on_non_child_entity_emits_no_join(self) -> None:
        """A plain entity (no subtype_of) must not gain a JOIN."""
        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]

        class AssetModel(BaseModel):
            id: str | None = None
            acquired_at: Any = None
            location: str | None = None
            kind: str | None = None

        db = _mock_db_manager(fetched_rows=[], count=0)
        repo = Repository(
            db_manager=db,
            entity_spec=asset_spec,
            model_class=AssetModel,
            base_entity_spec=None,
        )

        await repo.list(page=1, page_size=20)

        select_sql = next(
            c.args[0]
            for c in db._mock_cursor.execute.call_args_list
            if isinstance(c.args[0], str)
            and c.args[0].lstrip().startswith("SELECT ")
            and "COUNT(*)" not in c.args[0]
        )
        assert "JOIN " not in select_sql

    @pytest.mark.asyncio
    async def test_list_on_child_returns_dicts_with_base_columns(self) -> None:
        """#1237 — list() must route through the dict-coercion path when a
        subtype JOIN is active, so base columns (acquired_at, location, kind)
        survive into the renderer instead of being dropped by Pydantic's
        default `extra='ignore'` on the child model."""
        from pydantic import BaseModel

        from dazzle.http.runtime.repository import Repository

        entities = _build_subtype_back_entities()
        asset_spec = entities["Asset"]
        vehicle_spec = entities["Vehicle"]

        # Deliberately narrow model — exposes the bug if list() returns models.
        class VehicleModel(BaseModel):
            id: str | None = None
            wheels: int | None = None
            vin: str | None = None

        row = {
            "id": str(uuid4()),
            "wheels": 4,
            "vin": "1HGCM82633A123456",
            "acquired_at": None,
            "location": "Warehouse 7",
            "kind": "Vehicle",
        }
        db = _mock_db_manager(fetched_rows=[row], count=1)
        repo = Repository(
            db_manager=db,
            entity_spec=vehicle_spec,
            model_class=VehicleModel,
            base_entity_spec=asset_spec,
        )

        result = await repo.list(page=1, page_size=20)

        assert result["total"] == 1
        items = result["items"]
        assert len(items) == 1
        item = items[0]
        # Must be a dict (not a stripped VehicleModel).
        assert isinstance(item, dict), f"expected dict, got {type(item).__name__}"
        assert item.get("kind") == "Vehicle"
        assert item.get("location") == "Warehouse 7"
        assert item.get("wheels") == 4


class TestAggregateByKind:
    """group_by: kind on a polymorphic base entity should "just work" — kind
    is just a regular column on the base table. This test pins the existing
    behaviour against accidental regressions when subtype tables enter the mix.
    """

    def test_aggregate_group_by_kind_emits_standard_group_by_sql(self) -> None:
        from dazzle.http.runtime.aggregate import Dimension, build_aggregate_sql

        # group_by: kind against the Asset base table.
        sql, _params = build_aggregate_sql(
            table_name="Asset",
            placeholder_style="%s",
            dimensions=[Dimension(name="kind")],
            measures={"count": "count"},
            filters=None,
        )
        # kind dimension column is selected, grouped, and ordered.
        assert '"Asset"."kind" AS "dim_0_id"' in sql
        assert 'GROUP BY "Asset"."kind"' in sql
        assert 'COUNT(*) AS "count"' in sql
