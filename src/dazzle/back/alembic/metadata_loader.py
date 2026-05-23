"""Side-effect-free DSL → SQLAlchemy MetaData loader for Alembic.

This module is deliberately importable outside an Alembic run. Unlike
``env.py`` (which executes ``config = context.config`` at module level and
therefore crashes with ``AttributeError`` when imported directly), this
module performs no module-level work and imports nothing from
``alembic.context``.

Both ``env.py`` (during an Alembic run) and ``dazzle db baseline`` (a plain
CLI invocation) call :func:`load_target_metadata` so the DSL-derived schema
is built from exactly one code path.
"""

import logging
from pathlib import Path

import sqlalchemy

logger = logging.getLogger(__name__)


def load_target_metadata() -> sqlalchemy.MetaData:
    """Build SQLAlchemy ``MetaData`` from the Dazzle project in the CWD.

    Parses the project's DSL files, links them into an ``AppSpec``, converts
    the domain entities to SQLAlchemy tables, and returns the resulting
    ``MetaData``. Used as Alembic's ``target_metadata`` so ``--autogenerate``
    can diff the DSL schema against the live database.

    Falls back to an empty ``MetaData`` when no project context is available
    (e.g. ``alembic current`` run outside a project directory). Genuine
    parse / link / IO errors propagate to the caller — silently returning
    empty metadata would let ``--autogenerate`` produce a migration that
    drops every table.
    """
    from dazzle.back.converters.entity_converter import convert_entities
    from dazzle.back.runtime.sa_schema import build_metadata
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules
    from dazzle.core.renderer_registry import known_renderer_names

    project_root = Path.cwd()
    manifest_path = project_root / "dazzle.toml"
    if not manifest_path.exists():
        return sqlalchemy.MetaData()

    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(project_root, manifest)
    if not dsl_files:
        return sqlalchemy.MetaData()

    modules = parse_modules(dsl_files)
    # ``build_appspec`` wants the module name (e.g. "aegismark.core" from
    # `[project] root` in dazzle.toml), NOT the filesystem path.
    # ProjectManifest.project_root is misleadingly named — it holds the
    # module string, not a Path. Passing the cwd here raises LinkError on
    # every db migrate / revision (#886).
    appspec = build_appspec(
        modules,
        manifest.project_root,
        known_renderers=known_renderer_names(manifest),
    )
    entities = convert_entities(appspec.domain.entities)
    return build_metadata(entities, surfaces=list(appspec.surfaces))
