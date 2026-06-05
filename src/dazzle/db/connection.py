"""Database connection utilities for the `dazzle db` CLI.

Resolves DATABASE_URL and provides an async psycopg3 connection factory plus a
few asyncpg-shaped row helpers. This is the one-shot CLI path (connect → a few
statements → close); the request-serving runtime has its own pooled psycopg3
connections in ``back/runtime/pg_backend.py``. psycopg3 is the single Postgres
driver across the whole codebase (#1341).
"""

from pathlib import Path
from typing import Any

from dazzle.core.manifest import load_manifest, resolve_database_url


def resolve_db_url(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
    env_name: str = "",
) -> str:
    """Resolve the database URL.

    Priority: explicit_url > env profile > DATABASE_URL env > dazzle.toml > default.
    Delegates to dazzle.core.manifest.resolve_database_url.
    """
    manifest = None
    if project_root is not None:
        toml_path = project_root / "dazzle.toml"
        if toml_path.exists():
            manifest = load_manifest(toml_path)

    return resolve_database_url(manifest, explicit_url=explicit_url, env_name=env_name)


async def get_connection(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
) -> Any:
    """Create an async psycopg3 connection (autocommit, mapping rows).

    ``autocommit=True`` mirrors the prior asyncpg semantics: each ``dazzle db``
    command is a one-shot op whose statements — often DDL like TRUNCATE / CREATE
    POLICY — should land immediately without an explicit transaction. ``dict_row``
    yields mapping-style rows so call sites can read ``row["col"]``.

    Caller is responsible for closing it (``await conn.close()``).
    """
    import psycopg
    from psycopg.rows import dict_row

    url = resolve_db_url(explicit_url=explicit_url, project_root=project_root)
    return await psycopg.AsyncConnection.connect(url, autocommit=True, row_factory=dict_row)


async def fetchval(conn: Any, sql: str, params: Any = ()) -> Any:
    """Run ``sql`` and return the first column of the first row (or None).

    asyncpg-``fetchval`` equivalent for psycopg3. ``params`` is a sequence bound
    to ``%s`` placeholders.
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()
    if row is None:
        return None
    return next(iter(row.values()))


async def fetchrow(conn: Any, sql: str, params: Any = ()) -> Any:
    """Run ``sql`` and return the first row as a mapping (or None)."""
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


async def fetchall(conn: Any, sql: str, params: Any = ()) -> list[Any]:
    """Run ``sql`` and return all rows as mappings."""
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        return list(await cur.fetchall())
