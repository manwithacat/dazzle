"""Tests for [database] config in dazzle.toml and resolve_database_url()."""

import textwrap
from pathlib import Path

import pytest

from dazzle.core.manifest import (
    _DEFAULT_DATABASE_URL,
    DatabaseConfig,
    EnvironmentProfile,
    ProjectManifest,
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
    """Resolution chain: explicit > env > manifest > default.

    Each row sets up env vars + manifest, then asserts the resolved URL.
    Sentinel ``_DEFAULT`` in the expected column means "the framework default".
    """

    @pytest.mark.parametrize(
        ("env_setup", "manifest_url", "explicit_url", "expected"),
        [
            # Precedence chain
            (
                {"DATABASE_URL": "postgresql://env:5432/envdb"},
                "postgresql://toml:5432/tomldb",
                "postgresql://cli:5432/clidb",
                "postgresql://cli:5432/clidb",  # explicit wins
            ),
            (
                {"DATABASE_URL": "postgresql://env:5432/envdb"},
                "postgresql://toml:5432/tomldb",
                None,
                "postgresql://env:5432/envdb",  # env wins over manifest
            ),
            ({}, "postgresql://toml:5433/tomldb", None, "postgresql://toml:5433/tomldb"),
            # env: indirection
            (
                {"MY_DB_URL": "postgresql://resolved:5432/db"},
                "env:MY_DB_URL",
                None,
                "postgresql://resolved:5432/db",
            ),
            # env: indirection with missing var → default
            ({}, "env:MY_DB_URL", None, "_DEFAULT"),
            # No config at all → default
            ({}, "_NO_MANIFEST", None, "_DEFAULT"),
            # Default manifest URL → default
            ({}, "_DEFAULT_MANIFEST", None, "_DEFAULT"),
            # Heroku-style postgres:// → postgresql:// (explicit)
            ({}, None, "postgres://user:pass@host:5432/db", "postgresql://user:pass@host:5432/db"),
            # Heroku-style postgres:// from env
            (
                {"DATABASE_URL": "postgres://user:pass@host:5432/db"},
                None,
                None,
                "postgresql://user:pass@host:5432/db",
            ),
            # Heroku-style postgres:// from manifest
            ({}, "postgres://user:pass@host:5432/db", None, "postgresql://user:pass@host:5432/db"),
        ],
        ids=[
            "explicit_wins",
            "env_wins_over_manifest",
            "manifest_direct_url",
            "manifest_env_prefix",
            "manifest_env_prefix_missing_var",
            "default_fallback_no_manifest",
            "default_fallback_default_manifest",
            "heroku_normalization_explicit",
            "heroku_normalization_env",
            "heroku_normalization_manifest",
        ],
    )
    def test_resolve(
        self,
        monkeypatch: pytest.MonkeyPatch,
        env_setup: dict,
        manifest_url: str | None,
        explicit_url: str | None,
        expected: str,
    ) -> None:
        # Clear DATABASE_URL by default; tests opt in via env_setup
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("MY_DB_URL", raising=False)
        for key, value in env_setup.items():
            monkeypatch.setenv(key, value)

        if manifest_url == "_NO_MANIFEST":
            manifest = None
        elif manifest_url == "_DEFAULT_MANIFEST":
            manifest = _make_manifest()
        else:
            manifest = _make_manifest(manifest_url) if manifest_url else None

        result = resolve_database_url(manifest, explicit_url=explicit_url)
        if expected == "_DEFAULT":
            assert result == _DEFAULT_DATABASE_URL
        else:
            assert result == expected


# ---------------------------------------------------------------------------
# [infra] and [stack] config parsing
# ---------------------------------------------------------------------------


class TestLoadManifestInfra:
    def test_infra_section_parsed(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [infra]
                backends = ["terraform"]

                [infra.terraform]
                cloud_provider = "gcp"
                region = "us-east1"
            """),
        )
        mf = load_manifest(toml_path)
        assert mf.infra is not None
        assert mf.infra.terraform.cloud_provider == "gcp"
        assert mf.infra.terraform.region == "us-east1"
        assert mf.infra.backends == ["terraform"]

    def test_no_infra_section(self, tmp_path: Path) -> None:
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.infra is None


class TestLoadManifestStack:
    def test_stack_section_parsed(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [stack]
                name = "my-stack"
                backends = ["fastapi", "postgres"]
                description = "Main stack"
            """),
        )
        mf = load_manifest(toml_path)
        assert mf.stack is not None
        assert mf.stack.name == "my-stack"
        assert mf.stack.backends == ["fastapi", "postgres"]
        assert mf.stack.description == "Main stack"

    def test_no_stack_section(self, tmp_path: Path) -> None:
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.stack is None


class TestLoadManifestCdn:
    def test_cdn_defaults_false(self, tmp_path: Path) -> None:
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.cdn is False

    def test_cdn_disabled(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [ui]
                cdn = false
            """),
        )
        mf = load_manifest(toml_path)
        assert mf.cdn is False


class TestLoadManifestEnvironments:
    def test_no_environments_section(self, tmp_path: Path) -> None:
        """Backward compat: no [environments] → empty dict."""
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.environments == {}

    def test_single_environment(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://localhost:5432/myapp_dev"
            """),
        )
        mf = load_manifest(toml_path)
        assert "development" in mf.environments
        profile = mf.environments["development"]
        assert isinstance(profile, EnvironmentProfile)
        assert profile.database_url == "postgresql://localhost:5432/myapp_dev"
        assert profile.database_url_env == ""
        assert profile.heroku_app == ""

    def test_multiple_environments(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.staging]
                database_url_env = "STAGING_DB_URL"
                heroku_app = "myapp-staging"

                [environments.production]
                database_url_env = "PROD_DB_URL"
                heroku_app = "myapp-prod"
            """),
        )
        mf = load_manifest(toml_path)
        assert len(mf.environments) == 2
        assert mf.environments["staging"].database_url_env == "STAGING_DB_URL"
        assert mf.environments["staging"].heroku_app == "myapp-staging"
        assert mf.environments["production"].heroku_app == "myapp-prod"

    def test_freeform_environment_names(self, tmp_path: Path) -> None:
        """Environment names are freeform — blue/green, demo, etc."""
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.blue]
                database_url_env = "BLUE_DB"

                [environments.green]
                database_url_env = "GREEN_DB"

                [environments.demo]
                database_url = "postgresql://localhost:5432/demo"
            """),
        )
        mf = load_manifest(toml_path)
        assert set(mf.environments.keys()) == {"blue", "green", "demo"}


class TestResolveDatabaseUrlWithEnv:
    """Tests for the env_name parameter in resolve_database_url()."""

    def _make_manifest_with_envs(self) -> ProjectManifest:
        return ProjectManifest(
            name="test",
            version="0.1.0",
            project_root=".",
            module_paths=["./dsl"],
            database=DatabaseConfig(url="postgresql://toml:5432/tomldb"),
            environments={
                "staging": EnvironmentProfile(
                    database_url_env="STAGING_DB_URL",
                    heroku_app="myapp-staging",
                ),
                "development": EnvironmentProfile(
                    database_url="postgresql://localhost:5432/devdb",
                ),
                "both": EnvironmentProfile(
                    database_url="postgresql://direct:5432/db",
                    database_url_env="INDIRECT_DB_URL",
                ),
            },
        )

    @pytest.mark.parametrize(
        ("env_sets", "env_deletes", "env_name", "explicit_url", "expected"),
        [
            # Explicit URL beats env profile — explicit_url wins regardless of env_name.
            (
                {},
                ["DATABASE_URL"],
                "development",
                "postgresql://cli:5432/clidb",
                "postgresql://cli:5432/clidb",
            ),
            # Env profile with direct database_url is used.
            ({}, ["DATABASE_URL"], "development", None, "postgresql://localhost:5432/devdb"),
            # Env profile with env var indirection resolves when var is set.
            (
                {"STAGING_DB_URL": "postgresql://staging:5432/stgdb"},
                ["DATABASE_URL"],
                "staging",
                None,
                "postgresql://staging:5432/stgdb",
            ),
            # Env profile env var unset — falls through to manifest database URL.
            (
                {},
                ["DATABASE_URL", "STAGING_DB_URL"],
                "staging",
                None,
                "postgresql://toml:5432/tomldb",
            ),
            # direct_url beats env_var when both are set in the profile.
            (
                {"INDIRECT_DB_URL": "postgresql://indirect:5432/db"},
                ["DATABASE_URL"],
                "both",
                None,
                "postgresql://direct:5432/db",
            ),
            # Env profile beats ambient DATABASE_URL env var.
            (
                {"DATABASE_URL": "postgresql://ambient:5432/ambientdb"},
                [],
                "development",
                None,
                "postgresql://localhost:5432/devdb",
            ),
            # Empty env_name uses existing fallback chain (manifest direct URL).
            ({}, ["DATABASE_URL"], "", None, "postgresql://toml:5432/tomldb"),
        ],
        ids=[
            "test_explicit_url_beats_env_profile",
            "test_env_profile_direct_url",
            "test_env_profile_env_var_indirection",
            "test_env_profile_env_var_unset_falls_through",
            "test_env_profile_direct_beats_env_var",
            "test_env_profile_beats_database_url_env",
            "test_no_env_name_uses_existing_chain",
        ],
    )
    def test_resolve_with_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        env_sets: dict,
        env_deletes: list,
        env_name: str,
        explicit_url: str | None,
        expected: str,
    ) -> None:
        """resolve_database_url() selects the correct URL from env profile, env vars, and manifest."""
        for key in env_deletes:
            monkeypatch.delenv(key, raising=False)
        for key, value in env_sets.items():
            monkeypatch.setenv(key, value)
        manifest = self._make_manifest_with_envs()
        kwargs: dict = {"env_name": env_name}
        if explicit_url is not None:
            kwargs["explicit_url"] = explicit_url
        result = resolve_database_url(manifest, **kwargs)
        assert result == expected

    def test_unknown_env_name_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        with pytest.raises(SystemExit, match="Unknown environment 'nonexistent'"):
            resolve_database_url(manifest, env_name="nonexistent")

    def test_unknown_env_lists_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        with pytest.raises(SystemExit, match="staging"):
            resolve_database_url(manifest, env_name="nonexistent")

    def test_env_profile_normalises_postgres_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = ProjectManifest(
            name="test",
            version="0.1.0",
            project_root=".",
            module_paths=["./dsl"],
            environments={
                "heroku": EnvironmentProfile(database_url="postgres://u:p@h:5432/d"),
            },
        )
        result = resolve_database_url(manifest, env_name="heroku")
        assert result == "postgresql://u:p@h:5432/d"
