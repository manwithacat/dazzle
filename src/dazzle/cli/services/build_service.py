"""CLI-facing build service wrapping build/migration operations."""

from __future__ import annotations

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
        """Plan migrations without applying. Returns MigrationPlan."""
        from dazzle_back.runtime.migrations import plan_migrations
        from dazzle_back.runtime.pg_backend import PostgresBackend

        db_manager = PostgresBackend(database_url)
        return plan_migrations(db_manager, entities)

    def auto_migrate(self, database_url: str, entities: Any, *, record_history: bool = True) -> Any:
        """Apply safe migrations automatically. Returns MigrationPlan."""
        from dazzle_back.runtime.migrations import auto_migrate
        from dazzle_back.runtime.pg_backend import PostgresBackend

        db_manager = PostgresBackend(database_url)
        return auto_migrate(db_manager, entities, record_history=record_history)

    def generate_preview_files(self, appspec: Any, output_dir: str) -> list[str]:
        """Generate static preview HTML files from AppSpec."""
        from dazzle_ui.runtime.static_preview import generate_preview_files

        return [str(p) for p in generate_preview_files(appspec, output_dir)]

    def resolve_database_url(self, explicit_url: str = "") -> str:
        """Resolve the database URL from manifest/env/default."""
        from dazzle.core.manifest import load_manifest, resolve_database_url

        manifest = None
        if self._manifest_path.exists():
            manifest = load_manifest(self._manifest_path)
        return resolve_database_url(manifest, explicit_url=explicit_url)
