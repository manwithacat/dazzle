"""Database operations MCP handlers.

Read-only operations: status, verify.
Write operations (reset, cleanup) are CLI-only per MCP/CLI boundary.
"""

import json
from pathlib import Path
from typing import Any

from dazzle.db.connection import resolve_db_url
from dazzle.db.status import db_status_impl
from dazzle.db.verify import db_verify_impl

from .common import extract_progress, load_project_appspec, wrap_async_handler_errors


async def get_connection(*, project_root: Path) -> Any:
    """Get a psycopg3 async connection for the project."""
    from dazzle.db.connection import get_connection as _get_conn

    return await _get_conn(project_root=project_root)


def _mask_db_url(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        creds, hostpart = rest.rsplit("@", 1)
        if ":" in creds:
            user, _pw = creds.split(":", 1)
            return f"{scheme}://{user}:***@{hostpart}"
        return url
    except ValueError:
        return url


@wrap_async_handler_errors
async def db_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Row counts per entity, database size."""
    progress = extract_progress(args)
    progress.log_sync("Querying database status...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    resolved_url = resolve_db_url(project_root=project_path)
    conn = await get_connection(project_root=project_path)
    try:
        result = await db_status_impl(entities=entities, conn=conn)
    finally:
        await conn.close()

    if isinstance(result, dict):
        result["database_url_masked"] = _mask_db_url(resolved_url)
        result["project_root"] = str(project_path)
    return json.dumps(result, indent=2)


@wrap_async_handler_errors
async def db_verify_handler(project_path: Path, args: dict[str, Any]) -> str:
    """FK integrity check with findings list."""
    progress = extract_progress(args)
    progress.log_sync("Verifying FK integrity...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    conn = await get_connection(project_root=project_path)
    try:
        result = await db_verify_impl(entities=entities, conn=conn)
    finally:
        await conn.close()

    return json.dumps(result, indent=2)
