"""Tests for [database] config in dazzle.toml and resolve_database_url()."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.core.manifest import (
    _DEFAULT_DATABASE_URL,
    DatabaseConfig,
    ProjectManifest,
    _normalise_postgres_scheme,
    load_manifest,
    resolve_database_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_TOML = textwrap.dedent("""\
    [project]
    name = "test-app"
    version = "0.1.0"

    [modules]
    paths = ["./dsl"]
""")


def _write_toml(tmp_path: Path, extra: str = "") -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(_MINIMAL_TOML + extra, encoding="utf-8")
    return p


def _make_manifest(db_url: str = _DEFAULT_DATABASE_URL) -> ProjectManifest:
    """Create a minimal ProjectManifest with given database URL."""
    return ProjectManifest(
        name="test",
        version="0.1.0",
        project_root=".",
        module_paths=["./dsl"],
        database=DatabaseConfig(url=db_url),
    )


# ---------------------------------------------------------------------------
# load_manifest tests
# ---------------------------------------------------------------------------


class TestLoadManifestDatabase:
    def test_with_database_section(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [database]
                url = "postgresql://myhost:5433/mydb"
            """),
        )
        mf = load_manifest(toml_path)
        assert mf.database.url == "postgresql://myhost:5433/mydb"

    def test_without_database_section(self, tmp_path: Path) -> None:
        """Backward compat: no [database] section → default."""
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.database.url == _DEFAULT_DATABASE_URL

    def test_env_indirection_in_toml(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [database]
                url = "env:DATABASE_URL"
            """),
        )
        mf = load_manifest(toml_path)
        assert mf.database.url == "env:DATABASE_URL"


# ---------------------------------------------------------------------------
# resolve_database_url tests
# ---------------------------------------------------------------------------


class TestResolveDatabaseUrl:
    def test_explicit_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI --database-url beats everything."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://env:5432/envdb")
        manifest = _make_manifest("postgresql://toml:5432/tomldb")
        result = resolve_database_url(manifest, explicit_url="postgresql://cli:5432/clidb")
        assert result == "postgresql://cli:5432/clidb"

    def test_env_wins_over_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL env var beats manifest."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://env:5432/envdb")
        manifest = _make_manifest("postgresql://toml:5432/tomldb")
        result = resolve_database_url(manifest)
        assert result == "postgresql://env:5432/envdb"

    def test_manifest_direct_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Manifest URL used when no env var."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = _make_manifest("postgresql://toml:5433/tomldb")
        result = resolve_database_url(manifest)
        assert result == "postgresql://toml:5433/tomldb"

    def test_manifest_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env:VAR_NAME indirection resolves at runtime."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("MY_DB_URL", "postgresql://resolved:5432/db")
        manifest = _make_manifest("env:MY_DB_URL")
        result = resolve_database_url(manifest)
        assert result == "postgresql://resolved:5432/db"

    def test_manifest_env_prefix_missing_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env:VAR_NAME falls through to default when var is unset."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("MY_DB_URL", raising=False)
        manifest = _make_manifest("env:MY_DB_URL")
        result = resolve_database_url(manifest)
        assert result == _DEFAULT_DATABASE_URL

    def test_default_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No config anywhere → default."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        result = resolve_database_url(None)
        assert result == _DEFAULT_DATABASE_URL

    def test_default_fallback_with_default_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Manifest with default URL → default."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = _make_manifest()
        result = resolve_database_url(manifest)
        assert result == _DEFAULT_DATABASE_URL

    def test_heroku_normalization_explicit(self) -> None:
        """postgres:// normalised to postgresql:// for explicit URL."""
        result = resolve_database_url(None, explicit_url="postgres://user:pass@host:5432/db")
        assert result == "postgresql://user:pass@host:5432/db"

    def test_heroku_normalization_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """postgres:// normalised from env var."""
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")
        result = resolve_database_url(None)
        assert result == "postgresql://user:pass@host:5432/db"

    def test_heroku_normalization_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """postgres:// normalised from manifest."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = _make_manifest("postgres://user:pass@host:5432/db")
        result = resolve_database_url(manifest)
        assert result == "postgresql://user:pass@host:5432/db"


# ---------------------------------------------------------------------------
# _normalise_postgres_scheme tests
# ---------------------------------------------------------------------------


class TestNormalisePostgresScheme:
    def test_converts_postgres(self) -> None:
        assert _normalise_postgres_scheme("postgres://u:p@h/d") == "postgresql://u:p@h/d"

    def test_leaves_postgresql(self) -> None:
        assert _normalise_postgres_scheme("postgresql://u:p@h/d") == "postgresql://u:p@h/d"

    def test_leaves_other_schemes(self) -> None:
        assert _normalise_postgres_scheme("sqlite:///foo.db") == "sqlite:///foo.db"
