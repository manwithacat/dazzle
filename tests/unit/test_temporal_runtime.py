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
    from dazzle.http.runtime.repository import Repository

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
    repo._subtype_join_sql = None
    repo._subtype_extra_cols = []
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

        from dazzle.http.runtime.query_builder import QueryBuilder

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

        from dazzle.http.runtime.query_builder import QueryBuilder

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

        from dazzle.http.runtime.repository import Repository

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
        repo._subtype_join_sql = None
        repo._subtype_extra_cols = []
        repo._record_query = lambda *_a, **_kw: None  # type: ignore[method-assign]

        asyncio.run(repo.read(uuid4()))
        sql = cursor.execute.call_args.args[0]
        assert 'AND "deleted_at" IS NULL' in sql
        assert 'AND "end_date" IS NULL' in sql


# ============================================================================
# 3a.iii: DB partial unique index
# ============================================================================


class TestPartialUniqueIndexSQL:
    """Phase 3a.iii: pg_backend emits a partial unique index per temporal
    entity. The index covers only currently-active rows (end_field IS
    NULL), so closing a row + opening a new one is allowed."""

    def test_temporal_unique_index_sql_shape(self) -> None:
        """Builder emits the expected partial unique index SQL.

        `Composed.as_string()` needs a connection or a context; we
        instead inspect the structural pieces (identifiers + SQL
        fragments) which is what matters for safety + correctness.
        """
        from dazzle.http.runtime.pg_backend import _create_temporal_unique_index_sql

        composed = _create_temporal_unique_index_sql(
            entity_name="Employment",
            key_field="person",
            end_field="end_date",
        )
        rendered = str(composed)  # repr-style; contains literal identifiers
        # SQL skeleton
        assert "CREATE UNIQUE INDEX IF NOT EXISTS" in rendered
        assert "WHERE" in rendered
        assert "IS NULL" in rendered
        # Identifiers correctly composed (psycopg Identifier wraps them)
        assert "Identifier('uniq_active_Employment_person')" in rendered
        assert "Identifier('Employment')" in rendered
        assert "Identifier('person')" in rendered
        assert "Identifier('end_date')" in rendered

    def test_index_name_uses_key_field(self) -> None:
        """The index name carries the key_field for grep-ability."""
        from dazzle.http.runtime.pg_backend import _create_temporal_unique_index_sql

        composed = _create_temporal_unique_index_sql(
            entity_name="ManagerLink",
            key_field="report",
            end_field="end_date",
        )
        assert "Identifier('uniq_active_ManagerLink_report')" in str(composed)


# ============================================================================
# 3a.iv: ?as_of= URL param threading + Repository as_of kwarg
# ============================================================================


class TestAsOfHelper:
    def test_predicate_shape(self) -> None:
        from datetime import date

        from dazzle.http.runtime.repository import _build_temporal_as_of_predicate

        sql, params = _build_temporal_as_of_predicate("start_date", "end_date", date(2026, 5, 24))
        # Open-interval test: must have started by as_of AND not yet ended.
        assert '"start_date" <= %s' in sql
        assert '"end_date" IS NULL OR "end_date" > %s' in sql
        assert params == [date(2026, 5, 24), date(2026, 5, 24)]


class TestReadAsOf:
    def test_read_with_as_of_uses_open_interval_predicate(self) -> None:
        import asyncio
        from datetime import date
        from uuid import uuid4

        repo = _make_employment_repo()
        repo._mock_cursor.fetchone = MagicMock(return_value=None)
        asyncio.run(repo.read(uuid4(), as_of=date(2025, 6, 1)))
        sql, params = repo._mock_cursor.execute.call_args.args
        # The tombstone-only clause is REPLACED with the open-interval test.
        assert 'AND ("start_date" <= %s' in sql
        assert '"end_date" IS NULL OR "end_date" > %s)' in sql
        # The original `AND "end_date" IS NULL` shouldn't appear standalone.
        # Two as_of params appended after the id.
        assert len(params) == 3  # id + as_of x2
        assert params[1] == date(2025, 6, 1)
        assert params[2] == date(2025, 6, 1)

    def test_read_without_as_of_keeps_tombstone(self) -> None:
        import asyncio
        from uuid import uuid4

        repo = _make_employment_repo()
        repo._mock_cursor.fetchone = MagicMock(return_value=None)
        asyncio.run(repo.read(uuid4()))
        sql = repo._mock_cursor.execute.call_args.args[0]
        # Tombstone path — no open-interval predicate.
        assert 'AND "end_date" IS NULL' in sql
        assert "start_date" not in sql


class TestListAsOf:
    def test_list_with_as_of_routes_through_scope_predicate(self) -> None:
        """List path: __as_of in filters dict → scope_predicate slot
        (the QueryBuilder special key, intercepted in add_filters)."""
        import asyncio
        from datetime import date
        from unittest.mock import patch

        repo = _make_employment_repo()
        captured_filters: dict = {}

        from dazzle.http.runtime.query_builder import QueryBuilder

        original = QueryBuilder.add_filters

        def _capture(self, filters):
            captured_filters.update(filters)
            return original(self, filters)

        with patch.object(QueryBuilder, "add_filters", _capture):
            asyncio.run(repo.list(filters={"__as_of": date(2025, 6, 1)}))

        # __as_of consumed by Repository, replaced with __scope_predicate
        # before reaching QueryBuilder.
        assert "__as_of" not in captured_filters
        scope = captured_filters.get("__scope_predicate")
        assert scope is not None
        sql, params = scope
        assert '"start_date" <= %s' in sql
        assert '"end_date" IS NULL OR "end_date" > %s' in sql
        assert params == [date(2025, 6, 1), date(2025, 6, 1)]


# ============================================================================
# 3a.v.ii: latest_one runtime resolution
# ============================================================================


class TestLatestOneResolverHelper:
    """The module-level helper that fetches current rows per latest_one
    field and attaches them under the field name on each input row."""

    def _person_entity_with_current_employment(self) -> ir.EntitySpec:
        return ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="legal_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",
                        via_field="person",
                    ),
                ),
            ],
        )

    def _mock_db(self, fetched_rows: list[dict]) -> MagicMock:
        cursor = MagicMock()
        cursor.execute = MagicMock()
        cursor.fetchall = MagicMock(return_value=fetched_rows)
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        db = MagicMock()
        db.placeholder = "%s"
        db.connection = MagicMock(return_value=ctx)
        db._mock_cursor = cursor
        return db

    def test_attaches_resolved_row_when_match(self) -> None:
        from dazzle.http.runtime.repository import _resolve_latest_one_fields

        person = self._person_entity_with_current_employment()
        rows = [{"id": "p1", "legal_name": "Alice"}]
        # Mock: one active employment for p1
        db = self._mock_db([{"id": "e1", "person": "p1", "role": "r1", "end_date": None}])

        result = _resolve_latest_one_fields(rows, person, db)
        assert result[0]["current_employment"] == {
            "id": "e1",
            "person": "p1",
            "role": "r1",
            "end_date": None,
        }

    def test_attaches_none_when_no_active_row(self) -> None:
        from dazzle.http.runtime.repository import _resolve_latest_one_fields

        person = self._person_entity_with_current_employment()
        rows = [{"id": "p1", "legal_name": "Alice"}]
        db = self._mock_db([])  # nothing returned — no active employment

        result = _resolve_latest_one_fields(rows, person, db)
        assert result[0]["current_employment"] is None

    def test_query_shape_uses_via_field_and_end_field_tombstone(self) -> None:
        from dazzle.http.runtime.repository import _resolve_latest_one_fields

        person = self._person_entity_with_current_employment()
        rows = [{"id": "p1"}, {"id": "p2"}]
        db = self._mock_db([])

        _resolve_latest_one_fields(rows, person, db)
        sql, params = db._mock_cursor.execute.call_args.args
        assert '"person" IN (%s, %s)' in sql
        assert '"end_date" IS NULL' in sql
        assert params == ["p1", "p2"]

    def test_no_op_when_entity_has_no_latest_one_fields(self) -> None:
        from dazzle.http.runtime.repository import _resolve_latest_one_fields

        plain_person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="legal_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
            ],
        )
        rows = [{"id": "p1", "legal_name": "Alice"}]
        db = self._mock_db([])

        result = _resolve_latest_one_fields(rows, plain_person, db)
        assert result == rows  # unchanged
        # The DB shouldn't have been touched.
        assert not db._mock_cursor.execute.called

    def test_as_of_composes_with_open_interval_predicate(self) -> None:
        from datetime import date

        from dazzle.http.runtime.repository import _resolve_latest_one_fields

        person = self._person_entity_with_current_employment()
        rows = [{"id": "p1"}]
        db = self._mock_db([])

        _resolve_latest_one_fields(rows, person, db, as_of=date(2025, 6, 1))
        sql, params = db._mock_cursor.execute.call_args.args
        assert '"end_date" IS NULL OR "end_date" > %s' in sql
        assert '"start_date" <= %s' in sql
        # Params: source_ids + [as_of, as_of]
        assert params[-2:] == [date(2025, 6, 1), date(2025, 6, 1)]


# ============================================================================
# 3a.iv follow-up: ?include_closed=true URL param friendly alias
# ============================================================================


class TestIncludeClosedURLParam:
    """`?include_closed=true` is a friendly URL alias for opting out
    of the default `<end_field>__isnull=True` filter. The list-handler
    sets `<end_field>__isnull=False` in the filter dict; the
    Repository layer's setdefault contract preserves the explicit
    False (explicit-caller-wins). Functional equivalent to
    `?filter[<end_field>__isnull]=false` but discoverable without
    knowing the field name."""

    def test_explicit_false_overrides_default(self) -> None:
        """Repository's setdefault contract preserves an explicit
        `<end_field>__isnull=False` filter — which is what the
        handler-level `?include_closed=true` URL param produces.
        Verifying the Repository contract here; the handler-level
        URL-param-to-filter-dict translation is a 4-line
        implementation in route_generator.py that's covered by
        bootstrap-app integration tests."""
        import asyncio
        from unittest.mock import patch

        repo = _make_employment_repo()
        captured: dict = {}

        from dazzle.http.runtime.query_builder import QueryBuilder

        original = QueryBuilder.add_filters

        def _capture(self, filters):
            captured.update(filters)
            return original(self, filters)

        with patch.object(QueryBuilder, "add_filters", _capture):
            # What ?include_closed=true → produces in merged_filters
            asyncio.run(repo.list(filters={"end_date__isnull": False}))

        assert captured.get("end_date__isnull") is False
