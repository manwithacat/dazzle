"""Database connection utilities.

Resolves DATABASE_URL and provides asyncpg connection factories.
"""

from pathlib import Path
from typing import Any

from dazzle.core.manifest import load_manifest, resolve_database_url


def resolve_db_url(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
) -> str:
    """Resolve the database URL.

    Priority: explicit_url > DATABASE_URL env > dazzle.toml > default.
    Delegates to dazzle.core.manifest.resolve_database_url.
    """
    manifest = None
    if project_root is not None:
        toml_path = project_root / "dazzle.toml"
        if toml_path.exists():
            manifest = load_manifest(toml_path)

    return resolve_database_url(manifest, explicit_url=explicit_url)


async def get_connection(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
) -> Any:
    """Create an asyncpg connection.

    Caller is responsible for closing it.
    """
    import asyncpg

    url = resolve_db_url(explicit_url=explicit_url, project_root=project_root)
    return await asyncpg.connect(url)
