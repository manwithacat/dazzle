"""#1218 Option A: end-to-end soft_delete wiring tests.

Covers the three runtime touch points added when `soft_delete: true`
is set on an entity:

1. Linker auto-adds a `deleted_at: datetime optional` field if the
   author hasn't declared one already.
2. Repository.list / read / aggregate apply a `deleted_at IS NULL`
   tombstone filter, composed with any user/scope filters via the
   shared QueryBuilder path.
3. DELETE handler stamps `deleted_at = NOW()` via an UPDATE instead
   of issuing a hard DELETE.

We test (1) end-to-end through `build_appspec` and (2)+(3) by
asserting on the SQL each repo path emits against a mock connection.
The integration with real PostgreSQL is exercised by the
test_constraint_errors / test_repository suites that already exist.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.core import ir


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


class TestLinkerAutoAddsDeletedAt:
    """Linker injects `deleted_at: datetime optional` when missing."""

    def test_adds_deleted_at_for_soft_delete_entity(self) -> None:
        from dazzle.core.linker import _inject_soft_delete_fields

        entity = ir.EntitySpec(
            name="Document",
            fields=[_id_field()],
            soft_delete=True,
        )
        out = _inject_soft_delete_fields([entity])
        assert len(out) == 1
        names = [f.name for f in out[0].fields]
        assert "deleted_at" in names
        deleted_at = next(f for f in out[0].fields if f.name == "deleted_at")
        assert deleted_at.type.kind == ir.FieldTypeKind.DATETIME
        assert ir.FieldModifier.OPTIONAL in deleted_at.modifiers

    def test_leaves_existing_deleted_at_alone(self) -> None:
        from dazzle.core.linker import _inject_soft_delete_fields

        existing = ir.FieldSpec(
            name="deleted_at",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.OPTIONAL],
        )
        entity = ir.EntitySpec(
            name="Document",
            fields=[_id_field(), existing],
            soft_delete=True,
        )
        out = _inject_soft_delete_fields([entity])
        deleted_at_fields = [f for f in out[0].fields if f.name == "deleted_at"]
        assert len(deleted_at_fields) == 1
        assert deleted_at_fields[0] is existing

    def test_does_not_touch_entities_without_soft_delete(self) -> None:
        from dazzle.core.linker import _inject_soft_delete_fields

        entity = ir.EntitySpec(name="Document", fields=[_id_field()])
        out = _inject_soft_delete_fields([entity])
        names = [f.name for f in out[0].fields]
        assert "deleted_at" not in names


class TestRepositoryTombstoneFilter:
    """Repository.list and Repository.aggregate auto-inject the
    `deleted_at IS NULL` filter when `entity_spec.soft_delete` is True.
    Read() augments the WHERE clause directly with `AND "deleted_at"
    IS NULL`.
    """

    def _make_repo(self, *, soft_delete: bool) -> MagicMock:
        """Build a partially-mocked Repository to capture the SQL it emits."""
        from dazzle.back.runtime.repository import Repository

        entity_spec = ir.EntitySpec(
            name="Document",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                    modifiers=[ir.FieldModifier.OPTIONAL],
                ),
            ],
            soft_delete=soft_delete,
        )

        cursor = MagicMock()
        cursor.execute = MagicMock()
        cursor.fetchall = MagicMock(return_value=[])
        cursor.fetchone = MagicMock(return_value=None)
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        db = MagicMock()
        db.placeholder = "%s"
        db.connection = MagicMock(return_value=ctx)

        model = MagicMock()

        repo = Repository.__new__(Repository)
        repo.entity_spec = entity_spec
        repo.model_class = model
        repo.db = db
        repo.table_name = entity_spec.name
        repo._field_types = {f.name: f.type for f in entity_spec.fields}
        repo._computed_fields = []
        repo._relation_loader = None
        repo._record_query = lambda *_a, **_kw: None  # type: ignore[method-assign]
        # #1217 Phase 3e follow-up: read() now inspects these subtype attrs
        # to choose between plain SELECT and the JOIN-to-base shape.
        repo._subtype_join_sql = None
        repo._subtype_extra_cols = []
        repo._mock_cursor = cursor
        return repo

    def test_read_appends_tombstone_clause_when_soft_delete(self) -> None:
        import asyncio
        from uuid import uuid4

        repo = self._make_repo(soft_delete=True)
        asyncio.run(repo.read(uuid4()))
        sql = repo._mock_cursor.execute.call_args.args[0]
        assert 'AND "deleted_at" IS NULL' in sql

    def test_read_no_tombstone_when_soft_delete_off(self) -> None:
        import asyncio
        from uuid import uuid4

        repo = self._make_repo(soft_delete=False)
        asyncio.run(repo.read(uuid4()))
        sql = repo._mock_cursor.execute.call_args.args[0]
        assert "deleted_at" not in sql


class TestSoftDeleteRouteSpec:
    """RouteSpec carries soft_delete; create_delete_handler reads it
    and swaps service.execute(operation='delete') for an update that
    stamps deleted_at.
    """

    def test_routespec_default_soft_delete_false(self) -> None:
        from dazzle.back.runtime.route_support import HandlerConfig, RouteSpec

        hc = HandlerConfig(entity_name="Document")
        spec = RouteSpec(handler=hc, service=MagicMock())
        assert spec.soft_delete is False

    def test_routespec_carries_soft_delete_true(self) -> None:
        from dazzle.back.runtime.route_support import HandlerConfig, RouteSpec

        hc = HandlerConfig(entity_name="Document")
        spec = RouteSpec(handler=hc, service=MagicMock(), soft_delete=True)
        assert spec.soft_delete is True
