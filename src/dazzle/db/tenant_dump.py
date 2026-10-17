"""Tenant-aware dump and restore-check under ``shared_schema`` RLS (#1788).

Under ``shared_schema`` tenancy ``dazzle db apply-rls`` puts every tenant-scoped
table under ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` with the restrictive
``tenant_fence`` policy on the ``dazzle.tenant_id`` GUC. On a host with a single
database role (Heroku Postgres: no ``CREATE ROLE``, no ``BYPASSRLS``) that role
owns the tables *and* is filtered by the fence, so no unbound session can dump
the database:

* a plain ``pg_dump`` (it sets ``row_security = off``) fails with
  ``query would be affected by row-level security policy`` — this is what
  breaks ``heroku pg:backups``;
* ``pg_dump --enable-row-security`` with no tenant bound "succeeds" and writes
  every fenced table empty.

The backup that works is one custom-format dump per tenant, each bound through
``PGOPTIONS="-c dazzle.tenant_id=<id>"`` (``pg_dump`` has no pre-SQL hook), all
reading one exported snapshot, plus a manifest of exact per-tenant counts. The
restore is sectioned: ``pre-data`` from the first dump, ``TABLE DATA`` from
every dump (fenced tables from each, the non-fenced tables from the first only),
``post-data`` once. ``TABLE DATA`` precedes ``ROW SECURITY`` / ``POLICY`` in the
TOC, so loading needs no binding. The shape is ported from cyfuture's
``scripts/db_ops.py`` (``backup`` / ``restore-check``), which proved it against
its production tenants.

Layout: models first, then pure helpers (no database, unit-tested), then the
psycopg/subprocess driver. Connection details reach the client tools only as
``PG*`` environment variables — never argv, where ``ps`` and error output show
the password.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dazzle import __version__
from dazzle.core.db_url import normalise_postgres_scheme
from dazzle.core.tenancy_inject import find_tenant_entity
from dazzle.db.artifact_registry import DB_ARTIFACTS
from dazzle.db.connection import fetchall, fetchval
from dazzle.db.tenant_ids import first_column, iter_tenant_ids
from dazzle.http.runtime.rls_schema import TENANT_GUC
from dazzle.http.runtime.sa_schema import scoped_entity_names

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
#: Row label used for non-fenced (global) tables in a mismatch report.
GLOBAL_TENANT = "(global)"

LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# PGOPTIONS is whitespace-split by libpq: a tenant id or role carrying spaces or
# backslashes would smuggle extra options. Both are validated before use.
TENANT_ID_RE = re.compile(r"[A-Za-z0-9-]+")
ROLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FILE_STEM_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

# ``pg_restore -l`` lines: "<id>; <oid> <oid> TABLE DATA <schema> <name> <owner>".
TOC_TABLE_DATA_RE = re.compile(r"^\s*\d+;\s+\d+\s+\d+\s+TABLE DATA\s+(\S+)\s+(.+?)\s+(\S+)\s*$")
TOC_GLOBAL_DATA_RE = re.compile(r"^\s*\d+;\s+\d+\s+\d+\s+(SEQUENCE SET|BLOBS|BLOB|LARGE OBJECT)\s")

# libpq connection keyword → environment variable.
_LIBPQ_ENV = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "passfile": "PGPASSFILE",
    "options": "PGOPTIONS",
    "application_name": "PGAPPNAME",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslcrl": "PGSSLCRL",
    "sslnegotiation": "PGSSLNEGOTIATION",
    "gssencmode": "PGGSSENCMODE",
    "channel_binding": "PGCHANNELBINDING",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "service": "PGSERVICE",
}

# Literal SQL (no interpolation).
_ROLE_BYPASSES_SQL = "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
_LIVE_TABLES_SQL = (
    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
    "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' ORDER BY relname"
)
_FORCED_TABLES_SQL = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace "
    "AND relkind = 'r' AND relforcerowsecurity ORDER BY relname"
)
_USER_SCHEMAS_SQL = (
    "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%' "
    "AND nspname <> 'information_schema' ORDER BY (nspname <> 'public'), nspname"
)
_SET_GUC_SQL = "SELECT set_config(%s, %s, false)"  # nosemgrep — bound parameters only

# ── models ────────────────────────────────────────────────────────────────


class DumpRefusal(RuntimeError):
    """The dump / restore-check must not run (CLI exit 2)."""


class DumpError(RuntimeError):
    """A dump / restore-check step failed (CLI exit 1)."""


class TenantEntry(BaseModel):
    id: str
    slug: str | None = None
    file: str


class DumpManifest(BaseModel):
    """``manifest.json`` — written last, so its presence marks a complete dump."""

    manifest_version: int = MANIFEST_VERSION
    label: str
    created_at: str
    dazzle_version: str
    alembic_version: str | None
    source_host: str
    source_dbname: str
    pg_server_version: str
    pg_dump_version: str
    partition_key: str
    tenant_entity: str | None
    tenants: list[TenantEntry]
    rls_tables: list[str]
    non_rls_tables: list[str]
    #: ``{tenant_id: {table: rows}}`` for every fenced table.
    counts: dict[str, dict[str, int]]
    #: ``{table: rows}`` for every non-fenced table (restored once).
    globals: dict[str, int]
    #: ``{file name: bytes}``.
    files: dict[str, int]


class TableClassification(BaseModel):
    """Fenced vs non-fenced tables of schema ``public``."""

    rls_tables: list[str]
    non_rls_tables: list[str]
    #: Non-fenced live tables that neither the IR, the artifact registry nor
    #: Alembic account for. Still restored once; reported so they are noticed.
    unaccounted: list[str] = Field(default_factory=list)


class CountMismatch(BaseModel):
    table: str
    tenant: str
    expected: int
    actual: int | None


class DumpPosture(BaseModel):
    """Whether an ordinary (unbound) ``pg_dump`` of this database can work."""

    forced_tables: list[str]
    role_bypasses_rls: bool

    @property
    def plain_dump_blocked(self) -> bool:
        """FORCE RLS is on and the connected role is filtered by it."""
        return bool(self.forced_tables) and not self.role_bypasses_rls


class RestoreCheckResult(BaseModel):
    label: str
    checks: int
    rows: int
    mismatches: list[CountMismatch]
    steps: list[str]


# ── pure helpers ──────────────────────────────────────────────────────────


def default_label(now: datetime | None = None) -> str:
    """``dump-<UTC %Y%m%dT%H%M%SZ>``."""
    now = now or datetime.now(UTC)
    return "dump-" + now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def registry_postures() -> dict[str, str]:
    """``{table: RlsPosture value}`` for every concrete registry table (ADR-0047)."""
    return {a.name: a.rls.value for a in DB_ARTIFACTS if not a.is_pattern}


def classify_tables(
    live: Mapping[str, tuple[bool, bool]],
    *,
    scoped: Iterable[str],
    app_entities: Iterable[str],
    registry: Mapping[str, str],
) -> TableClassification:
    """Split live ``public`` tables into fenced and non-fenced, cross-checked.

    ``live`` is ``{table: (relrowsecurity, relforcerowsecurity)}`` from
    ``pg_class``; ``scoped`` the IR's tenant-scoped entity names
    (``scoped_entity_names``); ``app_entities`` every IR entity name;
    ``registry`` :func:`registry_postures`. The live catalog decides, and every
    disagreement with the IR or the registry is a refusal — a dump partitioned
    on a wrong table set either duplicates rows (a non-fenced table restored
    from every dump) or loses them (a fenced table restored once).
    """
    scoped_set = set(scoped)
    entity_set = set(app_entities)
    problems: list[str] = []
    rls: list[str] = []
    non_rls: list[str] = []
    unaccounted: list[str] = []
    for table in sorted(live):
        enabled, forced = live[table]
        if table in scoped_set:
            if not (enabled and forced):
                problems.append(f"{table}: tenant-scoped in the DSL but RLS is not enabled+forced")
                continue
            rls.append(table)
            continue
        if enabled:
            posture = registry.get(table)
            where = (
                f"registry posture {posture}"
                if posture is not None
                else "not tenant-scoped in the DSL"
            )
            problems.append(f"{table}: RLS is enabled live but the table is {where}")
            continue
        non_rls.append(table)
        if table not in entity_set and table not in registry and table != "alembic_version":
            unaccounted.append(table)
    if problems:
        raise DumpRefusal(
            "the live RLS posture disagrees with the DSL / artifact registry:\n  "
            + "\n  ".join(problems)
            + "\nRun `dazzle db verify` and `dazzle db apply-rls` before dumping."
        )
    return TableClassification(rls_tables=rls, non_rls_tables=non_rls, unaccounted=unaccounted)


def dump_refusal(*, role_bypasses: bool, role: str | None, tenant_count: int) -> str | None:
    """Why a dump must not run, or None. Pure: the CLI refusal matrix."""
    if role_bypasses:
        who = f"role {role!r}" if role else "the connected role"
        return (
            f"{who} is a superuser or has BYPASSRLS, so RLS would not filter and every "
            "per-tenant dump would hold every tenant's rows. Pass --role <a NOSUPERUSER "
            "NOBYPASSRLS role that can read the tables> (e.g. CREATE ROLE app_backup "
            "NOLOGIN; GRANT <owner role> TO app_backup; then --role app_backup)."
        )
    if tenant_count == 0:
        return "no tenants in `organizations`; nothing to dump."
    return None


def dump_file_names(tenants: Iterable[tuple[str, str | None]]) -> dict[str, str]:
    """``{tenant_id: file name}``; ``<slug>.dump``, else ``<id>.dump``.

    The slug is reduced to ``[A-Za-z0-9._-]``; a slug that is empty after that,
    or already taken by another tenant, falls back to the id (ids are unique).
    """
    out: dict[str, str] = {}
    used: set[str] = set()
    for tenant_id, slug in tenants:
        stem = _FILE_STEM_UNSAFE.sub("-", slug).strip("-.") if slug else ""
        if not stem or stem in used or stem == "manifest":
            stem = tenant_id
        used.add(stem)
        out[tenant_id] = f"{stem}.dump"
    return out


def libpq_url(url: str) -> str:
    """A URL libpq accepts: ``postgres://`` and SQLAlchemy driver suffixes removed."""
    url = normalise_postgres_scheme(url)
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def url_to_pgenv(url: str) -> dict[str, str]:
    """Split a libpq URL / conninfo into ``PG*`` environment variables."""
    from psycopg.conninfo import conninfo_to_dict

    env: dict[str, str] = {}
    for key, value in conninfo_to_dict(libpq_url(url)).items():
        if value is None or value == "":
            continue
        var = _LIBPQ_ENV.get(key)
        if var is None:
            raise DumpError(f"unsupported connection parameter {key!r} in the database URL")
        env[var] = str(value)
    return env


def pg_client_env(
    base_env: Mapping[str, str],
    url: str,
    *,
    tenant_id: str | None = None,
    role: str | None = None,
) -> dict[str, str]:
    """Environment for a Postgres client tool.

    The connection comes from ``url`` through ``PG*`` variables (inherited
    ``PG*`` connection variables are cleared first, so nothing leaks in from
    the caller's shell); ``PGOPTIONS`` binds the tenant GUC and, with ``role``,
    ``SET ROLE`` for the whole session.
    """
    env = {k: v for k, v in base_env.items() if k not in _LIBPQ_ENV.values()}
    conn_env = url_to_pgenv(url)
    if conn_env.pop("PGOPTIONS", None):
        raise DumpError("the database URL must not carry 'options'; the dump sets PGOPTIONS")
    options: list[str] = []
    if tenant_id is not None:
        if not TENANT_ID_RE.fullmatch(tenant_id):
            raise DumpError(f"invalid tenant id {tenant_id!r}")
        options.append(f"-c {TENANT_GUC}={tenant_id}")
    if role is not None:
        if not ROLE_RE.fullmatch(role):
            raise DumpError(f"invalid role name {role!r}")
        options.append(f"-c role={role}")
    env.update(conn_env)
    if options:
        env["PGOPTIONS"] = " ".join(options)
    return env


def assert_argv_clean(argv: Iterable[str], url: str) -> None:
    """Refuse a command line that would expose the URL or its password."""
    secrets = [url, libpq_url(url)]
    try:
        password = url_to_pgenv(url).get("PGPASSWORD")
    except DumpError:
        password = None
    if password:
        secrets.append(password)
    for arg in argv:
        if any(secret and secret in str(arg) for secret in secrets):
            raise DumpError("refusing to put database credentials on a command line")


def pg_tool(pg_bin: str | None, name: str) -> str:
    return str(Path(pg_bin) / name) if pg_bin else name


def pg_dump_argv(pg_bin: str | None, out_file: Path, snapshot: str | None) -> list[str]:
    argv = [
        pg_tool(pg_bin, "pg_dump"),
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--enable-row-security",
        "--file",
        str(out_file),
    ]
    if snapshot:
        argv.append(f"--snapshot={snapshot}")
    return argv


_RESTORE_COMMON = ("--no-owner", "--no-acl", "--exit-on-error")


def pg_restore_argv(
    pg_bin: str | None,
    dump: Path,
    *,
    section: str,
    dbname: str,
    toc_list: Path | None = None,
) -> list[str]:
    """``pg_restore`` for one section; ``--dbname`` carries the bare name only."""
    argv = [pg_tool(pg_bin, "pg_restore"), f"--section={section}"]
    if toc_list is not None:
        argv += ["-L", str(toc_list)]
    return [*argv, *_RESTORE_COMMON, "--dbname", dbname, str(dump)]


def filter_toc(toc_lines: Iterable[str], *, rls_tables: Iterable[str], first: bool) -> list[str]:
    """``pg_restore -l`` lines to load in the data pass of one dump.

    The first dump loads every ``TABLE DATA`` entry plus the global data
    entries (``SEQUENCE SET``, large objects); every other dump loads only the
    ``TABLE DATA`` of the fenced ``public`` tables, so non-fenced tables load
    exactly once.
    """
    wanted = set(rls_tables)
    keep: list[str] = []
    for raw in toc_lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        m = TOC_TABLE_DATA_RE.match(line)
        if m:
            if first or (m.group(1) == "public" and m.group(2) in wanted):
                keep.append(line)
            continue
        if first and TOC_GLOBAL_DATA_RE.match(line):
            keep.append(line)
    return keep


def compare_counts(
    manifest: DumpManifest,
    counts: Mapping[str, Mapping[str, int]],
    globals_: Mapping[str, int],
) -> list[CountMismatch]:
    """Every manifest count the observed counts do not reproduce exactly."""
    out: list[CountMismatch] = []
    for tenant, tables in sorted(manifest.counts.items()):
        got = counts.get(tenant, {})
        for table, expected in sorted(tables.items()):
            actual = got.get(table)
            if actual != expected:
                out.append(
                    CountMismatch(table=table, tenant=tenant, expected=expected, actual=actual)
                )
    for table, expected in sorted(manifest.globals.items()):
        actual = globals_.get(table)
        if actual != expected:
            out.append(
                CountMismatch(table=table, tenant=GLOBAL_TENANT, expected=expected, actual=actual)
            )
    return out


def total_count_checks(manifest: DumpManifest) -> int:
    return sum(len(t) for t in manifest.counts.values()) + len(manifest.globals)


def drop_first_statements(schemas: Iterable[str]) -> list[str]:
    """SQL that wipes every user schema of a restore-check target, then recreates public."""
    names = list(schemas)
    stmts = [f'DROP SCHEMA "{s}" CASCADE' for s in names]  # nosemgrep — catalog names
    if "public" not in names:
        stmts.append('DROP SCHEMA IF EXISTS "public" CASCADE')
    stmts.append('CREATE SCHEMA "public"')
    return stmts


def read_manifest(from_dir: Path) -> DumpManifest:
    """Load and sanity-check ``manifest.json`` + the dump files it lists."""
    path = from_dir / MANIFEST_NAME
    if not path.is_file():
        raise DumpRefusal(f"no {MANIFEST_NAME} in {from_dir} (an incomplete or foreign dump)")
    manifest = DumpManifest.model_validate_json(path.read_text())
    if not manifest.tenants:
        raise DumpRefusal("the manifest lists no tenants")
    for name, size in manifest.files.items():
        f = from_dir / name
        if not f.is_file() or f.stat().st_size != size:
            raise DumpError(f"{name} is missing or not {size} bytes")
    return manifest


# ── driver ────────────────────────────────────────────────────────────────


def role_bypasses_rls(conn: Any) -> bool:
    """True when the session's current role is superuser or BYPASSRLS."""
    row = conn.execute(_ROLE_BYPASSES_SQL).fetchone()
    return bool(row and first_column(row))


async def read_dump_posture(conn: Any) -> DumpPosture:
    """:class:`DumpPosture` over an async ``dazzle db`` connection."""
    forced = [str(r["relname"]) for r in await fetchall(conn, _FORCED_TABLES_SQL)]
    bypass = bool(await fetchval(conn, _ROLE_BYPASSES_SQL))
    return DumpPosture(forced_tables=forced, role_bypasses_rls=bypass)


def live_table_rls(conn: Any) -> dict[str, tuple[bool, bool]]:
    """``{table: (relrowsecurity, relforcerowsecurity)}`` for ``public`` tables."""
    rows = conn.execute(_LIVE_TABLES_SQL).fetchall()
    return {str(r[0]): (bool(r[1]), bool(r[2])) for r in rows}


def _tenant_slugs(conn: Any, tenant_entity: Any, ids: list[str]) -> dict[str, str | None]:
    """Human-readable names from the tenant-root table (``slug``, else ``name``)."""
    from psycopg import sql

    slugs: dict[str, str | None] = dict.fromkeys(ids)
    if tenant_entity is None:
        return slugs
    fields = {f.name for f in tenant_entity.fields}
    col = next((c for c in ("slug", "name") if c in fields), None)
    if col is None:
        return slugs
    exists = conn.execute("SELECT to_regclass(%s)", (f'public."{tenant_entity.name}"',)).fetchone()
    if not exists or first_column(exists) is None:
        return slugs
    query = sql.SQL("SELECT id::text, {}::text FROM public.{}").format(
        sql.Identifier(col), sql.Identifier(tenant_entity.name)
    )
    for tid, value in conn.execute(query).fetchall():
        if tid in slugs and value:
            slugs[tid] = str(value)
    return slugs


def collect_counts(
    conn: Any,
    tenant_ids: Iterable[str],
    rls_tables: Iterable[str],
    non_rls_tables: Iterable[str],
    partition_key: str,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Exact counts: per tenant, bound **and** filtered on the partition key.

    The GUC binding is what the fence sees; the explicit ``WHERE`` keeps the
    numbers right for a role RLS does not filter (a superuser restore target).
    Non-fenced tables are counted once, unbound.
    """
    from psycopg import sql

    rls = list(rls_tables)
    counts: dict[str, dict[str, int]] = {}
    for tenant_id in tenant_ids:
        conn.execute(_SET_GUC_SQL, (TENANT_GUC, tenant_id))
        per: dict[str, int] = {}
        for table in rls:
            query = sql.SQL("SELECT count(*) FROM public.{} WHERE {}::text = %s").format(
                sql.Identifier(table), sql.Identifier(partition_key)
            )
            per[table] = int(first_column(conn.execute(query, (tenant_id,)).fetchone()))
        counts[tenant_id] = per
    conn.execute(_SET_GUC_SQL, (TENANT_GUC, ""))
    globals_: dict[str, int] = {}
    for table in non_rls_tables:
        query = sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
        globals_[table] = int(first_column(conn.execute(query).fetchone()))
    return counts, globals_


def _alembic_version(conn: Any) -> str | None:
    if (
        first_column(conn.execute("SELECT to_regclass('public.alembic_version')").fetchone())
        is None
    ):
        return None
    rows = conn.execute("SELECT version_num FROM public.alembic_version ORDER BY 1").fetchall()
    return ",".join(str(first_column(r)) for r in rows) or None


def tool_version(pg_bin: str | None, name: str) -> str:
    try:
        result = subprocess.run(
            [pg_tool(pg_bin, name), "--version"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError as e:
        raise DumpError(
            f"{name} not found{' in ' + pg_bin if pg_bin else ' on PATH'}; install the "
            "PostgreSQL client tools (at least the server's major version) or pass --pg-bin"
        ) from e
    if result.returncode != 0:
        raise DumpError(f"{name} --version failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _run_pg(argv: list[str], env: Mapping[str, str], url: str, what: str) -> str:
    assert_argv_clean(argv, url)
    result = subprocess.run(argv, env=dict(env), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise DumpError(f"{what} failed (exit {result.returncode}):\n{result.stderr.strip()}")
    return result.stdout


def _connection_identity(conn: Any) -> tuple[str, str]:
    """``(host, dbname)`` of a live connection; never carries credentials."""
    return (conn.info.host or "", conn.info.dbname or "")


def _check_dump_request(label: str, role: str | None, out_dir: Path) -> None:
    if not LABEL_RE.fullmatch(label):
        raise DumpRefusal(f"invalid label {label!r} (letters, digits, '.', '_', '-')")
    if role is not None and not ROLE_RE.fullmatch(role):
        raise DumpRefusal(f"invalid role name {role!r}")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise DumpRefusal(f"{out_dir} already exists and is not empty")


def _dump_tenant_ids(conn: Any, role: str | None) -> list[str]:
    """``SET ROLE`` (when asked), then the tenant ids — or the refusal."""
    from psycopg import sql

    if role:
        conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    tenant_ids = iter_tenant_ids(conn)
    reason = dump_refusal(
        role_bypasses=role_bypasses_rls(conn), role=role, tenant_count=len(tenant_ids)
    )
    if reason:
        raise DumpRefusal(reason)
    bad = [t for t in tenant_ids if not TENANT_ID_RE.fullmatch(t)]
    if bad:
        raise DumpError(f"tenant ids not safe for PGOPTIONS: {bad}")
    return tenant_ids


def run_dump(
    *,
    url: str,
    appspec: Any,
    out_dir: Path,
    label: str | None = None,
    role: str | None = None,
    pg_bin: str | None = None,
    base_env: Mapping[str, str] | None = None,
) -> tuple[DumpManifest, TableClassification]:
    """One tenant-bound custom-format dump per tenant + ``manifest.json``.

    ``out_dir`` must be absent or empty. Raises :class:`DumpRefusal` for the
    preconditions (see :func:`dump_refusal`, :func:`classify_tables`) and
    :class:`DumpError` when a step fails.
    """
    import psycopg

    now = datetime.now(UTC)
    label = label or default_label(now)
    _check_dump_request(label, role, out_dir)

    entities = list(appspec.domain.entities)
    partition_key = str(appspec.tenancy.isolation.partition_key)
    tenant_entity = find_tenant_entity(entities)
    scoped = scoped_entity_names(entities, partition_key)
    env_base = dict(os.environ if base_env is None else base_env)
    pg_dump_version = tool_version(pg_bin, "pg_dump")
    conn_url = libpq_url(url)

    with psycopg.connect(conn_url) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        source_host, source_dbname = _connection_identity(conn)
        tenant_ids = _dump_tenant_ids(conn, role)
        classification = classify_tables(
            live_table_rls(conn),
            scoped=scoped,
            app_entities=[e.name for e in entities],
            registry=registry_postures(),
        )
        slugs = _tenant_slugs(conn, tenant_entity, tenant_ids)
        files_by_tenant = dump_file_names((t, slugs[t]) for t in tenant_ids)
        alembic_version = _alembic_version(conn)
        server_version = str(first_column(conn.execute("SHOW server_version").fetchone()))
        snapshot = str(first_column(conn.execute("SELECT pg_export_snapshot()").fetchone()))
        counts, globals_ = collect_counts(
            conn,
            tenant_ids,
            classification.rls_tables,
            classification.non_rls_tables,
            partition_key,
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        # The dumps import the exported snapshot, so this transaction stays open
        # until the last one finishes.
        files: dict[str, int] = {}
        for tenant_id in tenant_ids:
            fname = files_by_tenant[tenant_id]
            argv = pg_dump_argv(pg_bin, out_dir / fname, snapshot)
            env = pg_client_env(env_base, url, tenant_id=tenant_id, role=role)
            _run_pg(argv, env, url, f"pg_dump for tenant {tenant_id}")
            files[fname] = (out_dir / fname).stat().st_size
        conn.rollback()

    manifest = DumpManifest(
        label=label,
        created_at=now.isoformat().replace("+00:00", "Z"),
        dazzle_version=__version__,
        alembic_version=alembic_version,
        source_host=source_host,
        source_dbname=source_dbname,
        pg_server_version=server_version,
        pg_dump_version=pg_dump_version,
        partition_key=partition_key,
        tenant_entity=tenant_entity.name if tenant_entity is not None else None,
        tenants=[TenantEntry(id=t, slug=slugs[t], file=files_by_tenant[t]) for t in tenant_ids],
        rls_tables=classification.rls_tables,
        non_rls_tables=classification.non_rls_tables,
        counts=counts,
        globals=globals_,
        files=files,
    )
    (out_dir / MANIFEST_NAME).write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest, classification


def same_database(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """``(host, dbname)`` identity; an empty host means the local socket."""

    def norm(ident: tuple[str, str]) -> tuple[str, str]:
        host, db = ident
        host = host.lower()
        if host in ("", "127.0.0.1", "::1") or host.startswith("/"):
            host = "localhost"
        return (host, db)

    return norm(a) == norm(b)


def _prepare_target(conn: Any, manifest: DumpManifest, drop_first: bool) -> str | None:
    """Refuse a source / non-empty target; wipe it under ``drop_first``."""
    if same_database(_connection_identity(conn), (manifest.source_host, manifest.source_dbname)):
        raise DumpRefusal("the target is the dump's source database; refusing")
    schemas = [str(first_column(r)) for r in conn.execute(_USER_SCHEMAS_SQL).fetchall()]
    existing = int(
        first_column(
            conn.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname = ANY(%s)", (schemas,)
            ).fetchone()
        )
    )
    extra = [s for s in schemas if s != "public"]
    if not existing and not extra:
        return None
    if not drop_first:
        raise DumpRefusal(
            f"the target already has {existing} table(s) in {', '.join(schemas)} "
            "(pass --drop-first to wipe it — scratch databases only)"
        )
    for stmt in drop_first_statements(schemas):
        conn.execute(stmt)
    return f"dropped {', '.join(schemas)} ({existing} tables) and recreated public"


def run_restore_check(
    *,
    from_dir: Path,
    target_url: str,
    drop_first: bool = False,
    pg_bin: str | None = None,
    base_env: Mapping[str, str] | None = None,
) -> RestoreCheckResult:
    """Restore a dump directory into ``target_url`` and recount against the manifest."""
    import psycopg

    manifest = read_manifest(from_dir)
    steps: list[str] = []
    conn_url = libpq_url(target_url)
    with psycopg.connect(conn_url, autocommit=True) as conn:
        dropped = _prepare_target(conn, manifest, drop_first)
        if dropped:
            steps.append(dropped)

    env = pg_client_env(dict(os.environ if base_env is None else base_env), target_url)
    dbname = env.get("PGDATABASE", "")
    first = from_dir / manifest.tenants[0].file

    argv = pg_restore_argv(pg_bin, first, section="pre-data", dbname=dbname)
    _run_pg(argv, env, target_url, "pg_restore pre-data")
    steps.append(f"pre-data from {first.name}")

    for i, tenant in enumerate(manifest.tenants):
        dump = from_dir / tenant.file
        toc = _run_pg(
            [pg_tool(pg_bin, "pg_restore"), "-l", str(dump)],
            env,
            target_url,
            f"pg_restore -l {dump.name}",
        )
        keep = filter_toc(toc.splitlines(), rls_tables=manifest.rls_tables, first=i == 0)
        fd, list_name = tempfile.mkstemp(prefix="dazzle_toc_", suffix=".list")
        os.close(fd)
        list_file = Path(list_name)
        try:
            list_file.write_text("\n".join(keep) + "\n")
            argv = pg_restore_argv(pg_bin, dump, section="data", dbname=dbname, toc_list=list_file)
            _run_pg(argv, env, target_url, f"pg_restore data from {dump.name}")
        finally:
            list_file.unlink(missing_ok=True)
        steps.append(f"data from {dump.name} ({len(keep)} entries)")

    argv = pg_restore_argv(pg_bin, first, section="post-data", dbname=dbname)
    _run_pg(argv, env, target_url, "pg_restore post-data")
    steps.append(f"post-data from {first.name}")

    with psycopg.connect(conn_url, autocommit=True) as conn:
        counts, globals_ = collect_counts(
            conn,
            [t.id for t in manifest.tenants],
            manifest.rls_tables,
            manifest.non_rls_tables,
            manifest.partition_key,
        )
    rows = sum(sum(c.values()) for c in counts.values()) + sum(globals_.values())
    return RestoreCheckResult(
        label=manifest.label,
        checks=total_count_checks(manifest),
        rows=rows,
        mismatches=compare_counts(manifest, counts, globals_),
        steps=steps,
    )
