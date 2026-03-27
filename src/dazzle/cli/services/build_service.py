"""CLI-facing build service wrapping build/migration operations."""

from pathlib import Path
from typing import Any


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
        from dazzle.core.lint import lint_appspec

        return lint_appspec(appspec)

    def plan_migrations(self, database_url: str, entities: Any) -> Any:
        """Check for pending migrations. Returns True if changes detected."""
        from alembic import command
        from alembic.util.exc import CommandError

        cfg = self._alembic_cfg(database_url)
        try:
            command.check(cfg)
            return None  # No changes
        except CommandError:
            return True  # Changes detected

    def auto_migrate(self, database_url: str, entities: Any, *, record_history: bool = True) -> Any:
        """Apply safe migrations automatically via Alembic."""
        from alembic import command

        cfg = self._alembic_cfg(database_url)
        command.upgrade(cfg, "head")

    def _alembic_cfg(self, database_url: str) -> Any:
        """Build Alembic config pointing to dazzle_back's alembic directory."""
        from alembic.config import Config as AlembicConfig

        alembic_dir = Path(__file__).resolve().parents[3] / "dazzle_back" / "alembic"
        cfg = AlembicConfig(str(alembic_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(alembic_dir))
        cfg.set_main_option("sqlalchemy.url", database_url)
        return cfg

    def generate_preview_files(self, appspec: Any, output_dir: str) -> list[str]:
        """Generate static preview HTML files from AppSpec."""
        from dazzle_ui.runtime.static_preview import generate_preview_files

        return [str(p) for p in generate_preview_files(appspec, output_dir)]

    def resolve_database_url(self, explicit_url: str = "") -> str:
        """Resolve the database URL from manifest/env/default."""
        from dazzle.cli.env import get_active_env
        from dazzle.core.manifest import load_manifest, resolve_database_url

        manifest = None
        if self._manifest_path.exists():
            manifest = load_manifest(self._manifest_path)
        return resolve_database_url(manifest, explicit_url=explicit_url, env_name=get_active_env())
