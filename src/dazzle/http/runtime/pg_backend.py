"""
PostgreSQL database backend for Dazzle backend runtime.

Provides the PostgreSQL database backend — the sole runtime backend.

Requires: psycopg[binary]>=3.2
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import sql as pgsql

from dazzle.core.db_url import add_psycopg_driver, normalise_postgres_scheme
from dazzle.http.runtime.predicate_compiler import _USER_GUC_PREFIX
from dazzle.http.runtime.query_builder import quote_identifier
from dazzle.http.runtime.rls_schema import HOST_TENANT_GUC, TENANT_GUC, USER_GUC_PREFIX
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

logger = logging.getLogger(__name__)

# Drift guard (C-2): the inline GUC literal in ``_set_tenant_context`` below must
# equal the framework constant the fence DDL reads. If TENANT_GUC ever changes,
# this assertion fires at import time rather than letting the runtime set one GUC
# while the fence reads another (which would silently total-deny).
assert TENANT_GUC == "dazzle.tenant_id", (
    f"TENANT_GUC ({TENANT_GUC!r}) drifted from the set_config literal in "
    "_set_tenant_context — update both together."
)

# Drift guard (#1394): the inline GUC literal in ``_set_host_tenant_context`` must
# equal HOST_TENANT_GUC (the name a ``current_tenant`` scope policy body reads).
assert HOST_TENANT_GUC == "dazzle.host_tenant_id", (
    f"HOST_TENANT_GUC ({HOST_TENANT_GUC!r}) drifted from the set_config literal in "
    "_set_host_tenant_context — update both together."
)

# Drift guard (Phase C, C-2): the GUC name the runtime SETS in
# ``_set_rls_user_attrs`` (``f"{USER_GUC_PREFIX}{attr}"``) must equal the name the
# scope policy READS (``predicate_compiler`` builds it from ``_USER_GUC_PREFIX``).
# Both derive from the single source of truth in ``rls_schema`` — this assertion
# pins that they are the same object/value at import time, so a future edit to one
# can't silently total-deny every scope predicate.
assert _USER_GUC_PREFIX == USER_GUC_PREFIX == "dazzle.user_", (
    f"USER_GUC_PREFIX drift: predicate_compiler={_USER_GUC_PREFIX!r}, "
    f"rls_schema={USER_GUC_PREFIX!r} — the policy reads and the runtime sets must "
    "agree (shared constant in rls_schema)."
)


def _set_search_path(conn: Any, schema: str) -> None:
    """Set search_path on a connection using safe SQL composition.

    Uses psycopg.sql.SQL + Identifier (not Python str.format) to prevent injection.
    """
    # psycopg.sql.SQL.format() is safe SQL composition, not string interpolation
    stmt = pgsql.SQL("SET search_path TO {schema}, public").format(schema=pgsql.Identifier(schema))
    conn.execute(stmt)  # nosemgrep


def _set_tenant_context(conn: Any, tenant_id: str | None) -> None:
    """Set the per-transaction ``dazzle.tenant_id`` GUC for the RLS fence.

    RLS tenancy Phase B. The PostgreSQL row-level-security fence reads
    ``current_setting('dazzle.tenant_id', true)`` (companion spec §1.3 / §6); this
    binds that GUC to the authenticated user's tenant so the leased connection is
    physically scoped to one tenant. The GUC name is the fixed framework constant
    :data:`dazzle.http.runtime.rls_schema.TENANT_GUC` — the SAME constant the
    fence DDL reads — so the runtime and the fence can never disagree on the name
    even when the app's partition_key column is custom (C-2).

    - When ``tenant_id`` is ``None`` this is a **no-op**: no GUC is set, the
      ``current_setting`` is missing → ``NULL`` → the fence matches no rows and
      rejects writes (fail-closed — the correct behaviour for unauthenticated /
      no-tenant requests against fenced tables).
    - When present, the value is passed as a **bind parameter** to ``set_config``
      — never string-interpolated (``SET LOCAL`` cannot take a bind param, which
      is why ``set_config(name, value, true)`` is used). ``is_local = true`` makes
      the setting transaction-scoped, so it lives exactly for the queries that run
      on this leased connection before the surrounding block commits (companion
      §6.1/§6.2).
    """
    if tenant_id is None:
        return
    # The GUC name is the fixed framework constant TENANT_GUC; the literal below
    # must stay in lockstep with it (the module-load assertion guards drift). The
    # tenant id is always a bind parameter — never interpolated.
    conn.execute(
        pgsql.SQL("SELECT set_config('dazzle.tenant_id', %s, true)"),  # nosemgrep
        [tenant_id],
    )


def _set_host_tenant_context(conn: Any, host_tenant_id: str | None) -> None:
    """Set the per-transaction ``dazzle.host_tenant_id`` GUC for ``current_tenant`` (#1394).

    Distinct from ``_set_tenant_context``: this binds the host-resolved tenant id
    (``request.state.tenant.id`` from the #1289 tenant_host resolver), which a
    ``current_tenant`` scope policy body reads via
    ``current_setting('dazzle.host_tenant_id', true)``. The GUC name is the fixed
    framework constant :data:`HOST_TENANT_GUC` (module-load assertion guards drift).

    - ``None`` (non-tenant request / apex host) → **no-op**: the GUC stays unset,
      ``current_setting`` reads ``NULL`` → a ``current_tenant`` predicate matches
      no rows (fail-closed).
    - Present → passed as a **bind parameter** to ``set_config`` (never
      interpolated); ``is_local = true`` makes it transaction-scoped.
    """
    if host_tenant_id is None:
        return
    conn.execute(
        pgsql.SQL("SELECT set_config('dazzle.host_tenant_id', %s, true)"),  # nosemgrep
        [host_tenant_id],
    )


def _set_rls_user_attrs(conn: Any, attrs: dict[str, str] | None) -> None:
    """Set the per-transaction ``dazzle.user_<attr>`` GUCs for scope policies.

    RLS tenancy Phase C. The per-verb intra-tenant scope policies read
    ``current_setting('dazzle.user_<attr>', true)::<type>`` (companion §6); this
    binds each of those GUCs from the authenticated user's resolved attributes so
    the leased connection's RLS scope predicates evaluate against the right
    subject. The map is the per-request value produced by the auth dependency and
    carried on the ``_current_rls_user_attrs`` contextvar — keyed by the **bare
    attr name** (``"id"``, ``"school_id"``, …); values are the resolved scalar
    strings.

    The GUC name is built as ``f"{USER_GUC_PREFIX}{attr}"`` from the SAME
    framework constant the policy body reads (``predicate_compiler`` re-exports it
    as ``_USER_GUC_PREFIX``). So the name the runtime SETS is, by construction,
    the name the policy READS — they can never drift (mirrors the ``TENANT_GUC``
    drift-guard; the module-load assertion below pins it).

    - ``None`` / empty → **no-op**: no GUC is set, so every scope predicate that
      needs one sees a missing ``current_setting`` → ``NULL`` → matches no rows
      (fail-closed — correct for unauthenticated / no-scope requests and for an
      attr that resolved to the RBAC-deny sentinel, which the binder already
      dropped from the map).
    - Each name **and** value is passed as a **bind parameter** to ``set_config``
      — never string-interpolated. The GUC *name* is dynamic (one per referenced
      attr) but is still a bind param, so a hostile attr value can never reach the
      SQL text. ``is_local = true`` makes each setting transaction-scoped, so it
      lives exactly for the queries on this leased connection (companion §6.1/§6.2).
    """
    if not attrs:
        return
    for attr, value in attrs.items():
        # ``set_config(name, value, true)`` — both name and value are bind
        # parameters (never interpolated). The name is derived from the shared
        # USER_GUC_PREFIX so it equals the name the scope policy reads.
        conn.execute(
            pgsql.SQL("SELECT set_config(%s, %s, true)"),  # nosemgrep
            [f"{USER_GUC_PREFIX}{attr}", value],
        )


def _create_table_sql(table_name: str, columns: str) -> pgsql.Composed:
    """Build a safe CREATE TABLE statement."""
    return pgsql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        pgsql.Identifier(table_name),
        pgsql.SQL(columns),
    )


def _create_index_sql(entity_name: str, field_name: str) -> pgsql.Composed:
    """Build a safe CREATE INDEX statement."""
    idx_name = f"idx_{entity_name}_{field_name}"
    return pgsql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
        pgsql.Identifier(idx_name),
        pgsql.Identifier(entity_name),
        pgsql.Identifier(field_name),
    )


def _create_temporal_unique_index_sql(
    entity_name: str, key_field: str, end_field: str
) -> pgsql.Composed:
    """Build a PostgreSQL partial unique index for a temporal entity (#1223 3a.iii).

    Enforces the "at most one currently-active row per key_field"
    invariant declared by ``temporal: { key_field: X, end_field: Y }``.
    The index covers only rows where ``end_field IS NULL`` so closed
    intervals don't participate in uniqueness — opening a new active
    row after closing the previous one is allowed.
    """
    idx_name = f"uniq_active_{entity_name}_{key_field}"
    return pgsql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({}) WHERE {} IS NULL").format(
        pgsql.Identifier(idx_name),
        pgsql.Identifier(entity_name),
        pgsql.Identifier(key_field),
        pgsql.Identifier(end_field),
    )


# =============================================================================
# Connection Wrapper
# =============================================================================


class PgConnectionWrapper:
    """Wrapper that adds .execute() convenience method to psycopg connections.

    Proxies execute through cursor().execute(), returning the cursor.
    All other attribute access is forwarded to the underlying connection.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> Any:
        """Execute SQL via a new cursor and return it."""
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


# =============================================================================
# Postgres Type Mapping
# =============================================================================


def _scalar_type_to_postgres(scalar_type: ScalarType) -> str:
    """Map scalar types to PostgreSQL types."""
    mapping: dict[ScalarType, str] = {
        ScalarType.STR: "TEXT",
        ScalarType.TEXT: "TEXT",
        ScalarType.INT: "INTEGER",
        # DECIMAL → exact NUMERIC (#1321); precision/scale applied in
        # _field_type_to_postgres where they're available. FLOAT stays IEEE-754.
        ScalarType.DECIMAL: "NUMERIC",
        ScalarType.FLOAT: "DOUBLE PRECISION",
        ScalarType.BOOL: "BOOLEAN",
        ScalarType.DATE: "DATE",
        ScalarType.DATETIME: "TIMESTAMPTZ",
        ScalarType.UUID: "UUID",
        ScalarType.EMAIL: "TEXT",
        ScalarType.URL: "TEXT",
        ScalarType.SLUG: "TEXT",
        ScalarType.JSON: "JSONB",
    }
    return mapping.get(scalar_type, "TEXT")


def _field_type_to_postgres(field_type: FieldType) -> str:
    """Convert FieldType to PostgreSQL column type."""
    if field_type.kind == "scalar" and field_type.scalar_type:
        # decimal(p,s) → NUMERIC(p,s) for exact arithmetic (#1321). Precision is
        # optional → unconstrained NUMERIC; scale only when declared.
        if field_type.scalar_type == ScalarType.DECIMAL and field_type.precision is not None:
            if field_type.scale is not None:
                return f"NUMERIC({field_type.precision}, {field_type.scale})"
            return f"NUMERIC({field_type.precision})"
        return _scalar_type_to_postgres(field_type.scalar_type)
    elif field_type.kind == "enum":
        return "TEXT"
    elif field_type.kind == "ref":
        return "UUID"
    else:
        return "TEXT"


def _python_to_postgres(value: Any, field_type: FieldType | None = None) -> Any:
    """Convert Python value to PostgreSQL-compatible value."""
    import json
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if value is None:
        return None
    elif isinstance(value, UUID):
        return str(value)
    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, date):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return float(value)
    elif isinstance(value, bool):
        return value  # Postgres has native bool
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return json.dumps(value)
    else:
        return value


# =============================================================================
# PostgreSQL Backend
# =============================================================================


class PostgresBackend:
    """
    PostgreSQL database backend.

    Drop-in replacement for DatabaseManager that uses PostgreSQL
    instead of SQLite. Parses DATABASE_URL for connection parameters.

    Supports optional connection pooling via psycopg_pool.ConnectionPool.
    Call open_pool() to enable pooling; connection() will then lease from
    the pool instead of opening a fresh TCP connection per call.
    """

    def __init__(self, database_url: str, search_path: str | None = None):
        """
        Initialize the PostgreSQL backend.

        Args:
            database_url: PostgreSQL connection URL
                          (e.g. postgresql://user:pass@host:5432/dbname)
            search_path: Optional schema search path (e.g. 'tenant_abc')
        """
        self.database_url = database_url
        self.search_path = search_path
        self._connection: Any = None
        self._pool: Any = None

    def open_pool(self, min_size: int = 2, max_size: int = 10) -> None:
        """Open a connection pool for this backend.

        Once opened, connection() leases from the pool instead of
        creating a fresh TCP connection per call.

        Args:
            min_size: Minimum number of connections to keep open.
            max_size: Maximum number of connections allowed.
        """
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        def _reset_connection(conn: Any) -> None:
            """Rollback any aborted transaction before returning to pool."""
            conn.rollback()

        self._pool = ConnectionPool(
            self.database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            reset=_reset_connection,
            open=True,
        )
        logger.info("Connection pool opened (min=%d, max=%d)", min_size, max_size)

    def close_pool(self) -> None:
        """Close the connection pool, if open."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None
            logger.info("Connection pool closed")

    @property
    def _sa_url(self) -> str:
        """Return a SQLAlchemy-compatible URL using psycopg (v3) driver."""
        # Normalise Heroku-style postgres:// alias before adding driver suffix
        return add_psycopg_driver(normalise_postgres_scheme(self.database_url))

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """
        Get a database connection context manager.

        When a pool is open, leases a connection from the pool.
        Otherwise falls back to a direct connection (needed for
        migrations that run before the pool is opened).

        Yields a wrapped psycopg connection with dict_row factory.
        Rows support string key access (row["col"]).
        The wrapper adds .execute() for sqlite3 API compatibility.

        If a tenant schema is set via context var (by TenantMiddleware),
        it takes precedence over the instance's search_path.
        """
        from dazzle.http.runtime.tenant_isolation import (
            get_current_host_tenant_id,
            get_current_rls_user_attrs,
            get_current_tenant_id,
            get_current_tenant_schema,
        )

        effective_search_path = get_current_tenant_schema() or self.search_path
        # RLS tenancy Phase B — bind dazzle.tenant_id for the shared_schema fence.
        # None (unauthenticated / non-tenant) leaves the GUC unset → fence denies.
        tenant_id = get_current_tenant_id()
        # #1394 — bind dazzle.host_tenant_id (the host-resolved tenant) for
        # `current_tenant` scope policies. None (non-tenant / apex) → no-op.
        host_tenant_id = get_current_host_tenant_id()
        # RLS tenancy Phase C — bind the dazzle.user_<attr> GUCs the intra-tenant
        # scope policies read. Empty (no scope rules / unauthenticated) → no-op.
        rls_user_attrs = get_current_rls_user_attrs()

        if self._pool is not None:
            with self._pool.connection() as conn:
                if effective_search_path:
                    _set_search_path(conn, effective_search_path)
                _set_tenant_context(conn, tenant_id)
                _set_host_tenant_context(conn, host_tenant_id)
                _set_rls_user_attrs(conn, rls_user_attrs)
                try:
                    yield PgConnectionWrapper(conn)
                except Exception:
                    conn.rollback()
                    raise
            return

        # Direct-connect fallback (pre-pool: migrations, build-time)
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            if effective_search_path:
                _set_search_path(conn, effective_search_path)
            _set_tenant_context(conn, tenant_id)
            _set_host_tenant_context(conn, host_tenant_id)
            _set_rls_user_attrs(conn, rls_user_attrs)
            yield PgConnectionWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_persistent_connection(self) -> Any:
        """
        Get a persistent connection for the application lifecycle.

        Returns a wrapped psycopg connection (reuses existing if available).

        WARNING: this does NOT set the RLS tenant context (``dazzle.tenant_id``)
        — unlike :meth:`connection`. Using it against an RLS-fenced table will
        fail-closed (no rows / rejected writes) because the GUC is unset. Prefer
        :meth:`connection` for any tenant-scoped access (see #1331).
        """
        import psycopg
        from psycopg.rows import dict_row

        if self._connection is None or self._connection.closed:
            raw = psycopg.connect(self.database_url, row_factory=dict_row)
            if self.search_path:
                _set_search_path(raw, self.search_path)
            self._connection = PgConnectionWrapper(raw)
        return self._connection

    def close(self) -> None:
        """Close the persistent connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None

    @property
    def backend_type(self) -> str:
        return "postgres"

    @property
    def placeholder(self) -> str:
        return "%s"

    def create_table(self, entity: EntitySpec, *, registry: Any = None) -> None:
        """Create a table for an entity if it doesn't exist."""
        columns = self._build_columns(entity, registry=registry)
        stmt = _create_table_sql(entity.name, columns)

        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(stmt)

            # Create indexes
            for field in entity.fields:
                if field.indexed:
                    cursor.execute(_create_index_sql(entity.name, field.name))

            # Create FK indexes
            if registry is not None:
                from dazzle.http.runtime.relation_loader import get_foreign_key_indexes

                for fk_idx_sql in get_foreign_key_indexes(entity, registry):
                    cursor.execute(fk_idx_sql)

            # #1223 Phase 3a.iii — partial unique index for temporal entities.
            # Enforces "at most one currently-active row per key_field" at
            # the DB layer. The IR validator already confirmed the named
            # fields exist; we just translate the spec into SQL here.
            _temporal = entity.temporal
            if _temporal is not None:
                cursor.execute(
                    _create_temporal_unique_index_sql(
                        entity.name,
                        _temporal.key_field,
                        _temporal.end_field,
                    )
                )

    def _build_columns(self, entity: EntitySpec, *, registry: Any = None) -> str:
        """Build column definitions for CREATE TABLE."""
        columns = []
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append('"id" TEXT PRIMARY KEY')

        for field in entity.fields:
            col_def = self._build_column(field)
            columns.append(col_def)

        # Append FK constraints from the relation registry
        if registry is not None:
            from dazzle.http.runtime.relation_loader import get_foreign_key_constraints

            fk_clauses = get_foreign_key_constraints(entity, registry)
            columns.extend(fk_clauses)

        return ", ".join(columns)

    def _build_column(self, field: FieldSpec) -> str:
        """Build a single column definition."""
        pg_type = _field_type_to_postgres(field.type)
        col_name = quote_identifier(field.name)
        parts = [col_name, pg_type]

        if field.name == "id":
            parts.append("PRIMARY KEY")
        elif field.required:
            parts.append("NOT NULL")

        if field.unique:
            parts.append("UNIQUE")

        if field.default is not None:
            from dazzle.core.ir.params import ParamRef

            raw_default = (
                field.default.default if isinstance(field.default, ParamRef) else field.default
            )
            if raw_default is not None:
                default_val = _python_to_postgres(raw_default, field.type)
                if isinstance(default_val, str):
                    parts.append(f"DEFAULT '{default_val}'")
                elif isinstance(default_val, bool):
                    parts.append(f"DEFAULT {'TRUE' if default_val else 'FALSE'}")
                else:
                    parts.append(f"DEFAULT {default_val}")

        return " ".join(parts)

    def create_all_tables(
        self,
        entities: list[EntitySpec],
        surfaces: list[Any] | None = None,
    ) -> None:
        """Create tables for all entities in topological (FK-dependency) order.

        Uses SQLAlchemy MetaData.create_all() which internally sorts tables
        by foreign key dependencies, preventing errors when a table references
        another that hasn't been created yet.

        When ``surfaces`` is provided, composite list-path indexes are
        emitted alongside the base schema (#1202).
        """
        from sqlalchemy import create_engine

        from dazzle.http.runtime.sa_schema import build_metadata

        metadata = build_metadata(entities, surfaces=surfaces)
        engine = create_engine(self._sa_url)
        try:
            metadata.create_all(engine, checkfirst=True)
        finally:
            engine.dispose()

        # Create application-level indexes (not in SA schema)
        from dazzle.http.runtime.relation_loader import (
            RelationRegistry,
            get_foreign_key_indexes,
        )

        registry = RelationRegistry.from_entities(entities)
        with self.connection() as conn:
            cursor = conn.cursor()
            for entity in entities:
                for field in entity.fields:
                    if field.indexed:
                        cursor.execute(_create_index_sql(entity.name, field.name))
                for fk_idx_sql in get_foreign_key_indexes(entity, registry):
                    cursor.execute(fk_idx_sql)
                # #1223 Phase 3a.iii — partial unique index per temporal entity.
                _temporal_bulk = entity.temporal
                if _temporal_bulk is not None:
                    cursor.execute(
                        _create_temporal_unique_index_sql(
                            entity.name,
                            _temporal_bulk.key_field,
                            _temporal_bulk.end_field,
                        )
                    )

        # #1217 Phase 3e.iii — install the shared assert_subtype_kind() plpgsql
        # function and one BEFORE INSERT/UPDATE trigger per polymorphic child
        # table. The function is idempotent (CREATE OR REPLACE) and the
        # triggers are dropped + re-created so this path is safe to call
        # multiple times.
        children = [e for e in entities if e.subtype_of is not None]
        if children:
            from dazzle.core.archetype_expander import _to_snake_case
            from dazzle.http.runtime.triggers import (
                build_assert_subtype_kind_function,
                build_child_kind_trigger,
            )

            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(build_assert_subtype_kind_function())
                for entity in children:
                    expected_kind = _to_snake_case(entity.name)
                    cursor.execute(
                        f'DROP TRIGGER IF EXISTS "{entity.name}_kind_consistency" '
                        f'ON "{entity.name}"'
                    )
                    cursor.execute(
                        build_child_kind_trigger(
                            child_table=entity.name,
                            base_table=entity.subtype_of or "",
                            expected_kind=expected_kind,
                        )
                    )

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
                (table_name,),
            )
            return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> list[str]:
        """Get column names for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
            return [row["column_name"] for row in cursor.fetchall()]

    def get_column_info(self, table_name: str) -> list[dict[str, Any]]:
        """Get detailed column information for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_table_indexes(self, table_name: str) -> list[str]:
        """Get index names for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = %s",
                (table_name,),
            )
            return [row["indexname"] for row in cursor.fetchall()]
