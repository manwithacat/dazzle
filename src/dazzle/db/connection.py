"""Database connection utilities for the `dazzle db` CLI.

Resolves DATABASE_URL and provides an async psycopg3 connection factory plus a
few asyncpg-shaped row helpers. This is the one-shot CLI path (connect → a few
statements → close); the request-serving runtime has its own pooled psycopg3
connections in ``back/runtime/pg_backend.py``. psycopg3 is the single Postgres
driver across the whole codebase (#1341).
"""

import json
import os
from pathlib import Path
from typing import Any

from dazzle.core.db_url import normalise_postgres_scheme
from dazzle.core.manifest import load_manifest, resolve_database_url


def _read_project_local_database_url(project_root: Path) -> str:
    """Prefer live serve binding / project .env over ambient MCP process env (#1629 G2).

    MCP often runs with monorepo cwd while ``dazzle serve`` used a different
    ``DATABASE_URL``. Without project-local resolution, ``db.status`` reports
    missing tables that the running app can see.
    """

    runtime = project_root / ".dazzle" / "runtime.json"
    if runtime.is_file():
        try:
            data = json.loads(runtime.read_text(encoding="utf-8"))
            url = data.get("database_url")
            if isinstance(url, str) and url.strip():
                return normalise_postgres_scheme(url.strip())
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    env_file = project_root / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                key, _, val = s.partition("=")
                if key.strip() != "DATABASE_URL":
                    continue
                val = val.strip().strip("'\"")
                if val:
                    return normalise_postgres_scheme(val)
        except OSError:
            pass

    # Optional project-scoped env var name used by some hosts
    scoped = os.environ.get(f"DATABASE_URL_{project_root.name.upper().replace('-', '_')}", "")
    if scoped:
        return normalise_postgres_scheme(scoped)
    return ""


def resolve_db_url(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
    env_name: str = "",
) -> str:
    """Resolve the database URL.

    Priority: explicit_url > project runtime.json / .env > env profile >
    DATABASE_URL env > dazzle.toml > default.

    Project-local sources rank above ambient process ``DATABASE_URL`` so MCP
    ``db.*`` tools bound to ``project_path`` see the same DB as a project-scoped
    ``dazzle serve`` (#1629 G2).
    """
    if explicit_url:
        return resolve_database_url(None, explicit_url=explicit_url, env_name=env_name)

    if project_root is not None:
        local = _read_project_local_database_url(project_root)
        if local:
            return local

    manifest = None
    if project_root is not None:
        toml_path = project_root / "dazzle.toml"
        if toml_path.exists():
            manifest = load_manifest(toml_path)

    return resolve_database_url(manifest, explicit_url="", env_name=env_name)


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
