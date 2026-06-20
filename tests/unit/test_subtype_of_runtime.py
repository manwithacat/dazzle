"""#1217 Phase 3e.iii — subtype repository methods + per-child trigger wiring.

Mock-based unit tests. The unit suite has no real-Postgres harness so we
verify the SQL emission shape and the kind-immutability guard against a
mocked PostgresBackend; the DB-level cross-row consistency (the actual
trigger firing) is tested manually against staging (Phase 3f).
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from dazzle.http.runtime.repository import create_subtype, update_subtype
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


def _mock_db_manager() -> MagicMock:
    """Build a mocked PostgresBackend with the placeholder + connection chain."""
    db = MagicMock()
    db.placeholder = "%s"
    # `with db.connection() as conn:` chain — yield a conn whose .cursor()
    # returns a mock cursor we can read .execute() call_args from.
    cursor = MagicMock()
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value = cursor
    db.connection.return_value.__enter__.return_value = conn
    db.connection.return_value.__exit__.return_value = False
    db._mock_cursor = cursor  # WHY: test introspection hook
    return db


def _asset_spec() -> EntitySpec:
    """Base entity with id (uuid pk) + acquired_at (date) + kind (synthesised)."""
    return EntitySpec(
        name="Asset",
        label="Asset",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="acquired_at",
                type=FieldType(kind="scalar", scalar_type=ScalarType.DATE),
                required=True,
            ),
            FieldSpec(
                name="kind",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=64),
                required=True,
            ),
        ],
        subtype_children=("Vehicle",),
    )


def _vehicle_spec() -> EntitySpec:
    """Child entity (subtype_of: Asset) with wheels."""
    return EntitySpec(
        name="Vehicle",
        label="Vehicle",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="wheels",
                type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
                required=True,
            ),
        ],
        subtype_of="Asset",
    )


def _non_subtype_spec() -> EntitySpec:
    """Bare entity with no subtype_of."""
    return EntitySpec(
        name="Lonely",
        label="Lonely",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
        ],
    )


class TestCreateSubtype:
    def test_returns_uuid(self) -> None:
        db = _mock_db_manager()
        new_id = create_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            payload={"acquired_at": "2026-05-24", "wheels": 4},
        )
        assert isinstance(new_id, UUID)

    def test_inserts_base_and_child_rows(self) -> None:
        db = _mock_db_manager()
        create_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            payload={"acquired_at": "2026-05-24", "wheels": 4},
        )
        # Two execute() calls — base INSERT then child INSERT.
        calls = db._mock_cursor.execute.call_args_list
        assert len(calls) == 2, f"expected 2 INSERTs, got {len(calls)}: {calls}"
        base_sql = calls[0].args[0]
        child_sql = calls[1].args[0]
        assert base_sql.startswith('INSERT INTO "Asset"')
        assert child_sql.startswith('INSERT INTO "Vehicle"')

    def test_kind_discriminator_auto_populated(self) -> None:
        db = _mock_db_manager()
        create_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            payload={"acquired_at": "2026-05-24", "wheels": 4},
        )
        calls = db._mock_cursor.execute.call_args_list
        base_sql = calls[0].args[0]
        base_values = calls[0].args[1]
        # The base INSERT must carry the "kind" column with value 'vehicle'.
        assert '"kind"' in base_sql
        assert "vehicle" in base_values

    def test_payload_split_by_field_ownership(self) -> None:
        """Base fields go to base INSERT; child fields go to child INSERT."""
        db = _mock_db_manager()
        create_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            payload={"acquired_at": "2026-05-24", "wheels": 4},
        )
        calls = db._mock_cursor.execute.call_args_list
        base_sql = calls[0].args[0]
        child_sql = calls[1].args[0]
        assert '"acquired_at"' in base_sql
        assert '"acquired_at"' not in child_sql
        assert '"wheels"' in child_sql
        assert '"wheels"' not in base_sql

    def test_shared_id_across_base_and_child(self) -> None:
        """The same uuid appears in both INSERTs (the join key)."""
        db = _mock_db_manager()
        new_id = create_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            payload={"acquired_at": "2026-05-24", "wheels": 4},
        )
        calls = db._mock_cursor.execute.call_args_list
        base_values = calls[0].args[1]
        child_values = calls[1].args[1]
        # The new_id (stringified by _python_to_postgres) appears in both.
        assert str(new_id) in base_values
        assert str(new_id) in child_values

    def test_rejects_non_subtype_child(self) -> None:
        db = _mock_db_manager()
        with pytest.raises(ValueError, match="not a subtype"):
            create_subtype(
                db_manager=db,
                base_spec=_asset_spec(),
                child_spec=_non_subtype_spec(),
                payload={},
            )

    def test_rejects_kind_in_payload(self) -> None:
        """`kind` is framework-owned — caller cannot set it directly."""
        db = _mock_db_manager()
        with pytest.raises(ValueError, match="kind"):
            create_subtype(
                db_manager=db,
                base_spec=_asset_spec(),
                child_spec=_vehicle_spec(),
                payload={"acquired_at": "2026-05-24", "wheels": 4, "kind": "other"},
            )


class TestUpdateSubtype:
    def test_rejects_payload_with_kind(self) -> None:
        """ADR-0026: kind is immutable post-create."""
        db = _mock_db_manager()
        row_id = UUID("00000000-0000-0000-0000-000000000001")
        with pytest.raises(ValueError, match="immutable"):
            update_subtype(
                db_manager=db,
                base_spec=_asset_spec(),
                child_spec=_vehicle_spec(),
                row_id=row_id,
                payload={"kind": "building"},
            )

    def test_splits_payload_into_base_and_child_updates(self) -> None:
        db = _mock_db_manager()
        row_id = UUID("00000000-0000-0000-0000-000000000001")
        update_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            row_id=row_id,
            payload={"acquired_at": "2026-06-01", "wheels": 6},
        )
        calls = db._mock_cursor.execute.call_args_list
        # Two UPDATEs — base then child.
        update_calls = [c for c in calls if c.args[0].startswith("UPDATE ")]
        assert len(update_calls) == 2
        base_sql = update_calls[0].args[0]
        child_sql = update_calls[1].args[0]
        assert 'UPDATE "Asset"' in base_sql
        assert '"acquired_at"' in base_sql
        assert 'UPDATE "Vehicle"' in child_sql
        assert '"wheels"' in child_sql

    def test_skips_table_when_no_fields_for_it(self) -> None:
        """If payload only touches child fields, only the child UPDATE fires."""
        db = _mock_db_manager()
        row_id = UUID("00000000-0000-0000-0000-000000000001")
        update_subtype(
            db_manager=db,
            base_spec=_asset_spec(),
            child_spec=_vehicle_spec(),
            row_id=row_id,
            payload={"wheels": 6},
        )
        calls = db._mock_cursor.execute.call_args_list
        update_calls = [c for c in calls if c.args[0].startswith("UPDATE ")]
        assert len(update_calls) == 1
        assert 'UPDATE "Vehicle"' in update_calls[0].args[0]

    def test_rejects_non_subtype_child(self) -> None:
        db = _mock_db_manager()
        row_id = UUID("00000000-0000-0000-0000-000000000001")
        with pytest.raises(ValueError, match="not a subtype"):
            update_subtype(
                db_manager=db,
                base_spec=_asset_spec(),
                child_spec=_non_subtype_spec(),
                row_id=row_id,
                payload={"wheels": 6},
            )
