"""
Alembic environment configuration for Dazzle.

Reads DATABASE_URL from the environment and uses the EntitySpec → SQLAlchemy
MetaData bridge as ``target_metadata`` so that ``--autogenerate`` can diff
the DSL schema against the live database.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object (provides access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging (if present).
if config.config_file_name and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Target metadata — built from DSL EntitySpecs
# ---------------------------------------------------------------------------

# Ensure the project src/ is on sys.path so imports work.
_src = str(Path(__file__).resolve().parents[2])  # src/
if _src not in sys.path:
    sys.path.insert(0, _src)


def _load_target_metadata():  # type: ignore[no-untyped-def]
    """Lazily load target metadata from the active Dazzle project.

    Falls back to an empty MetaData if no project entities are available
    (e.g. when running ``alembic current`` without a project context).
    """
    try:
        # Try to load entities from the project in CWD
        from dazzle.core.dsl_parser import parse_modules
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle_back.runtime.sa_schema import build_metadata

        project_root = Path.cwd()
        manifest_path = project_root / "dazzle.toml"
        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            dsl_files = discover_dsl_files(project_root, manifest)
            if dsl_files:
                modules = parse_modules(dsl_files)
                appspec = build_appspec(modules, str(project_root))
                # Convert IR entities to BackendSpec EntitySpec
                from dazzle_back.converters import convert_appspec_to_backend

                backend_spec = convert_appspec_to_backend(appspec)
                return build_metadata(backend_spec.entities)
    except Exception:
        pass

    # Fallback: empty metadata
    import sqlalchemy

    return sqlalchemy.MetaData()


target_metadata = _load_target_metadata()

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """Get database URL from env or alembic config."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return config.get_main_option("sqlalchemy.url", "")


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    from sqlalchemy import create_engine

    url = _get_url()
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required for online migrations.")

    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
