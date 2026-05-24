"""#1223 Phase 3a.ii — Repository tombstone filter for temporal entities.

When `entity.temporal` is declared with `default_filter == "active"`,
Repository.list / .read / .aggregate auto-inject `<end_field> IS NULL`
into their queries so closed-interval rows are hidden by default.
Composes with soft_delete + scope predicates via the same `setdefault`
contract the soft_delete filter uses.

These tests mock the DB connection and assert on the SQL each repo
path emits. Real-PostgreSQL integration is exercised by the
test_constraint_errors suite (which doesn't yet cover temporal — that
arrives with 3a.iii's partial unique index).
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


def _make_employment_repo(*, default_filter: str = "active") -> MagicMock:
    """Build a partially-mocked Repository for the Employment entity."""
    from dazzle.back.runtime.repository import Repository

    entity_spec = ir.EntitySpec(
        name="Employment",
        fields=[
            _id_field(),
            ir.FieldSpec(
                name="person",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
            ),
            ir.FieldSpec(
                name="start_date",
                type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="end_date",
                type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
            ),
        ],
        temporal=ir.TemporalSpec(
            start_field="start_date",
            end_field="end_date",
            key_field="person",
            default_filter=default_filter,
        ),
    )

    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchall = MagicMock(return_value=[])
    # fetchone serves both the single-row read (None → 404) and the
    # list-path count query (returns a 1-tuple of zero); a plain
    # MagicMock(return_value=...) covers both because list() reads
    # row[0] from the first call and read() returns immediately on
    # the None we set explicitly per-test.
    cursor.fetchone = MagicMock(return_value=(0,))
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)

    db = MagicMock()
    db.placeholder = "%s"
    db.connection = MagicMock(return_value=ctx)

    repo = Repository.__new__(Repository)
    repo.entity_spec = entity_spec
    repo.model_class = MagicMock()
    repo.db = db
    repo.table_name = entity_spec.name
    repo._field_types = {f.name: f.type for f in entity_spec.fields}
    repo._computed_fields = []
    repo._relation_loader = None
    repo._record_query = lambda *_a, **_kw: None  # type: ignore[method-assign]
    repo._mock_cursor = cursor
    return repo


class TestReadTombstone:
    def test_read_appends_temporal_clause_when_active_default(self) -> None:
        import asyncio
        from uuid import uuid4

        repo = _make_employment_repo()
        repo._mock_cursor.fetchone = MagicMock(return_value=None)  # not found path
        asyncio.run(repo.read(uuid4()))
        sql = repo._mock_cursor.execute.call_args.args[0]
        assert 'AND "end_date" IS NULL' in sql

    def test_read_no_temporal_clause_when_default_filter_none(self) -> None:
        import asyncio
        from uuid import uuid4

        repo = _make_employment_repo(default_filter="none")
        repo._mock_cursor.fetchone = MagicMock(return_value=None)
        asyncio.run(repo.read(uuid4()))
        sql = repo._mock_cursor.execute.call_args.args[0]
        assert "end_date" not in sql


class TestListTombstone:
    """Repository.list merges `end_date__isnull` into the filters dict
    via QueryBuilder when temporal default_filter is active."""

    def test_list_filters_include_end_field_isnull(self) -> None:
        """The setdefault contract means we can't directly inspect the
        dict (it's passed to QueryBuilder), but we can intercept by
        stubbing QueryBuilder.add_filters to capture the dict."""
        import asyncio
        from unittest.mock import patch

        repo = _make_employment_repo()

        captured: dict = {}

        original = None

        def _capture_add_filters(self, filters):
            captured.update(filters)
            if original is not None:
                return original(self, filters)
            return None

        from dazzle.back.runtime.query_builder import QueryBuilder

        original = QueryBuilder.add_filters

        with patch.object(QueryBuilder, "add_filters", _capture_add_filters):
            asyncio.run(repo.list())

        assert captured.get("end_date__isnull") is True

    def test_list_explicit_caller_override_wins(self) -> None:
        """A caller passing `end_date__isnull=False` explicitly should
        win over the default — the `setdefault` contract preserves
        explicit caller intent. Future hook for `?include_closed=true`."""
        import asyncio
        from unittest.mock import patch

        repo = _make_employment_repo()
        captured: dict = {}

        from dazzle.back.runtime.query_builder import QueryBuilder

        original = QueryBuilder.add_filters

        def _capture_add_filters(self, filters):
            captured.update(filters)
            return original(self, filters)

        with patch.object(QueryBuilder, "add_filters", _capture_add_filters):
            asyncio.run(repo.list(filters={"end_date__isnull": False}))

        assert captured.get("end_date__isnull") is False


class TestSoftDeleteAndTemporalCompose:
    """When an entity carries BOTH soft_delete and temporal, both
    filters apply — `deleted_at IS NULL AND end_date IS NULL`."""

    def test_both_filters_set_independently(self) -> None:
        import asyncio
        from uuid import uuid4

        from dazzle.back.runtime.repository import Repository

        entity_spec = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="end_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
                ir.FieldSpec(
                    name="start_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                ),
            ],
            soft_delete=True,
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="person",
            ),
        )

        cursor = MagicMock()
        cursor.execute = MagicMock()
        cursor.fetchone = MagicMock(return_value=None)  # read() → 404 path
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        db = MagicMock()
        db.placeholder = "%s"
        db.connection = MagicMock(return_value=ctx)

        repo = Repository.__new__(Repository)
        repo.entity_spec = entity_spec
        repo.model_class = MagicMock()
        repo.db = db
        repo.table_name = entity_spec.name
        repo._field_types = {f.name: f.type for f in entity_spec.fields}
        repo._computed_fields = []
        repo._relation_loader = None
        repo._record_query = lambda *_a, **_kw: None  # type: ignore[method-assign]

        asyncio.run(repo.read(uuid4()))
        sql = cursor.execute.call_args.args[0]
        assert 'AND "deleted_at" IS NULL' in sql
        assert 'AND "end_date" IS NULL' in sql
