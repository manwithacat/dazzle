"""CLI-facing build service wrapping build/migration operations."""

from pathlib import Path
from typing import Any

from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest, resolve_database_url


class BuildService:
    """Thin wrapper around build and migration operations for CLI usage.

    Centralizes AppSpec loading, validation, and backend conversion
    used across multiple build commands.
    """

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest_path = (manifest_path or Path("dazzle.toml")).resolve()
        self._root = self._manifest_path.parent

    def load_appspec(self) -> Any:
        """Load and return the project AppSpec."""
        from dazzle.cli.utils import load_project_appspec

        return load_project_appspec(self._root)

    def lint(self, appspec: Any) -> tuple[list[str], list[str]]:
        """Lint an AppSpec. Returns (errors, warnings)."""

        errors, warnings, _relevance = lint_appspec(appspec)
        return errors, warnings

    def plan_migrations(self, database_url: str, entities: Any) -> Any:
        """Check for pending migrations. Returns True if changes detected."""
        from alembic import command
        from alembic.util.exc import CommandError

        from dazzle.cli.db import _autostamp_if_materialized

        cfg = self._alembic_cfg(database_url)
        # #1390: reconcile an empty alembic_version against an already-materialized
        # schema so `check` reports the real additive diff, not a baseline replay.
        _autostamp_if_materialized(cfg)
        try:
            command.check(cfg)
            return None  # No changes
        except CommandError:
            return True  # Changes detected

    def auto_migrate(self, database_url: str, entities: Any) -> Any:
        """Apply safe migrations automatically via Alembic.

        The ``record_history`` keyword (removed in #1195) was dead — the old
        ``MigrationHistory`` write path was retired in commit ``adb3e0ca``,
        and the current implementation just calls ``alembic upgrade head``.
        """
        from alembic import command

        from dazzle.cli.db import _autostamp_if_materialized

        cfg = self._alembic_cfg(database_url)
        # #1390: same reconciliation as plan_migrations — without it, an empty
        # alembic_version on a materialized DB replays the baseline instead of
        # applying the additive diff.
        _autostamp_if_materialized(cfg)
        command.upgrade(cfg, "head")

    def _alembic_cfg(self, database_url: str) -> Any:
        """Build Alembic config with framework env.py + project-local versions."""
        from alembic.config import Config as AlembicConfig

        from dazzle.cli.db import _get_framework_alembic_dir, _get_project_versions_dir

        framework_dir = _get_framework_alembic_dir()
        cfg = AlembicConfig(str(framework_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(framework_dir))
        cfg.set_main_option(
            "version_locations",
            f"{framework_dir / 'versions'} {_get_project_versions_dir()}",
        )
        cfg.set_main_option("sqlalchemy.url", database_url)
        return cfg

    def generate_preview_files(self, appspec: Any, output_dir: str) -> list[str]:
        """Generate static preview HTML files from AppSpec."""
        from dazzle.page.runtime.static_preview import generate_preview_files

        return [str(p) for p in generate_preview_files(appspec, output_dir)]

    def resolve_database_url(self, explicit_url: str = "") -> str:
        """Resolve the database URL from manifest/env/default."""
        from dazzle.cli.env import get_active_env

        manifest = None
        if self._manifest_path.exists():
            manifest = load_manifest(self._manifest_path)
        return resolve_database_url(manifest, explicit_url=explicit_url, env_name=get_active_env())
