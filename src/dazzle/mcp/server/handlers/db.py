"""Database operations MCP handlers.

Read-only operations: status, verify.
Write operations (reset, cleanup) are CLI-only per MCP/CLI boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .common import extract_progress, load_project_appspec, wrap_handler_errors


async def get_connection(*, project_root: Path) -> Any:
    """Get asyncpg connection for the project."""
    from dazzle.db.connection import get_connection as _get_conn

    return await _get_conn(project_root=project_root)


@wrap_handler_errors
def db_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Row counts per entity, database size."""
    progress = extract_progress(args)
    progress.log_sync("Querying database status...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    from dazzle.db.status import db_status_impl

    async def _run() -> dict[str, Any]:
        conn = await get_connection(project_root=project_path)
        try:
            return await db_status_impl(entities=entities, conn=conn)
        finally:
            await conn.close()

    result = asyncio.run(_run())
    return json.dumps(result, indent=2)


@wrap_handler_errors
def db_verify_handler(project_path: Path, args: dict[str, Any]) -> str:
    """FK integrity check with findings list."""
    progress = extract_progress(args)
    progress.log_sync("Verifying FK integrity...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    from dazzle.db.verify import db_verify_impl

    async def _run() -> dict[str, Any]:
        conn = await get_connection(project_root=project_path)
        try:
            return await db_verify_impl(entities=entities, conn=conn)
        finally:
            await conn.close()

    result = asyncio.run(_run())
    return json.dumps(result, indent=2)
