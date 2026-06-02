"""Regression gate for GitHub issue #1308 part 1.

`dazzle db upgrade` (and `current` / `history` / `status`) silently operated on
the WRONG database in development mode: the CLI session env (`get_active_env`)
defaults to ``""`` (no profile), so `resolve_database_url` skipped the
``[environments.*]`` profile branch and fell through to the hardcoded default
``postgresql://localhost:5432/dazzle`` — a different DB than the dev app uses.
On that already-at-head DB, ``upgrade head`` no-op'd while reporting success.

The fix (`db._default_db_env`): when no ``--env`` / ``DAZZLE_ENV`` is set,
target the SAME environment the app uses (`get_dazzle_env`, defaults to
``development``) — but only if ``dazzle.toml`` declares that profile. Projects
without environment profiles keep the legacy resolution (DATABASE_URL →
``[database].url`` → default).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.cli.db import _default_db_env

_TOML_HEAD = textwrap.dedent("""\
    [project]
    name = "test-app"
    version = "0.1.0"

    [modules]
    paths = ["./dsl"]
""")


def _write_toml(tmp_path: Path, extra: str = "") -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(_TOML_HEAD + extra, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _clear_dazzle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure DAZZLE_ENV and DATABASE_URL are unset so the #1308 tests exercise
    the implicit-default + no-DATABASE_URL path deterministically (the #1329
    tests opt back into DATABASE_URL explicitly)."""
    monkeypatch.delenv("DAZZLE_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


class TestDefaultDbEnv1308:
    def test_defaults_to_development_when_profile_declared(self, tmp_path: Path) -> None:
        """No DAZZLE_ENV + a declared [environments.development] → 'development'.

        This is the core fix: db commands now resolve to the dev profile's
        database, matching `dazzle serve`, instead of falling through to the
        hardcoded default DB.
        """
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://localhost:5432/myapp_dev"
            """),
        )
        assert _default_db_env(tmp_path) == "development"

    def test_honours_dazzle_env_over_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DAZZLE_ENV=production selects the production profile (the path that
        already worked — must keep working)."""
        monkeypatch.setenv("DAZZLE_ENV", "production")
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://localhost:5432/myapp_dev"

                [environments.production]
                database_url_env = "DATABASE_URL"
            """),
        )
        assert _default_db_env(tmp_path) == "production"

    def test_empty_when_profile_not_declared(self, tmp_path: Path) -> None:
        """A project with NO matching [environments.<app-env>] profile keeps the
        legacy profile-less resolution (returns '') so DATABASE_URL /
        [database].url / default still apply."""
        _write_toml(tmp_path)  # no [environments] at all
        assert _default_db_env(tmp_path) == ""

    def test_empty_when_no_dazzle_toml(self, tmp_path: Path) -> None:
        """No dazzle.toml → '' (fail-safe, preserves existing behaviour)."""
        assert _default_db_env(tmp_path) == ""

    def test_resolves_dev_db_not_hardcoded_default(self, tmp_path: Path) -> None:
        """End-to-end: the resolved URL is the dev profile's DB, NOT the
        hardcoded `postgresql://localhost:5432/dazzle` the bug fell through to."""
        from dazzle.core.manifest import _DEFAULT_DATABASE_URL, load_manifest, resolve_database_url

        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://localhost:5432/myapp_dev"
            """),
        )
        env_name = _default_db_env(tmp_path)
        manifest = load_manifest(tmp_path / "dazzle.toml")
        url = resolve_database_url(manifest, explicit_url="", env_name=env_name)
        assert "myapp_dev" in url
        assert url != _DEFAULT_DATABASE_URL


class TestDefaultDbEnv1329:
    """#1329: a bare DATABASE_URL must win over an *implicitly*-defaulted profile.

    #1308 made `db` commands auto-target the app's default environment so they
    match `serve`. But a profile's literal `database_url` resolves at priority 2,
    *before* the priority-3 DATABASE_URL env var — so on a Heroku dyno (no
    DAZZLE_ENV) the implicitly-selected development profile's localhost URL
    shadowed the dyno's DATABASE_URL, deploying migrations against the wrong DB.
    """

    def test_database_url_wins_over_implicit_default_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DATABASE_URL set + no DAZZLE_ENV + declared dev profile → '' so the
        profile-less path lets DATABASE_URL (priority 3) win."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://prod@dyno:5432/heroku_db")
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://james@localhost:5432/myapp_dev"
            """),
        )
        assert _default_db_env(tmp_path) == ""

    def test_explicit_dazzle_env_still_wins_over_database_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An *explicit* DAZZLE_ENV keeps its profile even when DATABASE_URL is
        set — the user asked for that profile."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://prod@dyno:5432/heroku_db")
        monkeypatch.setenv("DAZZLE_ENV", "development")
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://james@localhost:5432/myapp_dev"
            """),
        )
        assert _default_db_env(tmp_path) == "development"

    def test_no_database_url_keeps_1308_local_dev_parity(self, tmp_path: Path) -> None:
        """Without DATABASE_URL (the local-dev case) the #1308 behaviour stands:
        auto-select the development profile so `db` matches `serve`."""
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://james@localhost:5432/myapp_dev"
            """),
        )
        assert _default_db_env(tmp_path) == "development"

    def test_end_to_end_database_url_resolves_for_heroku(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: with DATABASE_URL set and no DAZZLE_ENV, the resolved URL
        is the dyno's DATABASE_URL — NOT the dev profile's localhost URL."""
        from dazzle.core.manifest import load_manifest, resolve_database_url

        monkeypatch.setenv("DATABASE_URL", "postgresql://prod@dyno:5432/heroku_db")
        _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://james@localhost:5432/myapp_dev"
            """),
        )
        env_name = _default_db_env(tmp_path)
        manifest = load_manifest(tmp_path / "dazzle.toml")
        url = resolve_database_url(manifest, explicit_url="", env_name=env_name)
        assert "heroku_db" in url
        assert "myapp_dev" not in url


class TestRedactUrl1308:
    """`dazzle db upgrade` now prints the (redacted) target DB so a misresolved
    connection is visible — the trap that made the bug easy to miss."""

    def test_password_is_masked(self) -> None:
        from dazzle.cli.db import _redact_url

        masked = _redact_url("postgresql+psycopg://user:s3cret@db.example.com:5432/app")
        assert "s3cret" not in masked
        assert "user:***@db.example.com" in masked

    def test_passwordless_url_unchanged(self) -> None:
        from dazzle.cli.db import _redact_url

        url = "postgresql://localhost:5432/myapp_dev"
        assert _redact_url(url) == url
