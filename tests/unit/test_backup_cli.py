"""Tests for backup/restore CLI commands (#441)."""

from __future__ import annotations

import os
from unittest.mock import patch

from dazzle.cli.backup import (
    _build_pg_args,
    _build_pg_env,
    _parse_pg_url,
    _resolve_database_url,
)


class TestParsePgUrl:
    """URL parsing for pg_dump/pg_restore."""

    def test_full_url(self):
        result = _parse_pg_url("postgresql://user:pass@host:5432/mydb")
        assert result["host"] == "host"
        assert result["port"] == "5432"
        assert result["username"] == "user"
        assert result["password"] == "pass"
        assert result["dbname"] == "mydb"

    def test_minimal_url(self):
        result = _parse_pg_url("postgresql://localhost/mydb")
        assert result["host"] == "localhost"
        assert result["dbname"] == "mydb"
        assert "port" not in result
        assert "username" not in result

    def test_heroku_style_url(self):
        result = _parse_pg_url("postgresql://u:p@ec2-host:5432/d1234")
        assert result["host"] == "ec2-host"
        assert result["dbname"] == "d1234"


class TestBuildPgArgs:
    """Connection argument building."""

    def test_full_args(self):
        pg = {"host": "h", "port": "5432", "username": "u", "dbname": "db"}
        args = _build_pg_args(pg)
        assert "--host" in args
        assert "--port" in args
        assert "--username" in args
        assert "db" in args

    def test_empty_args(self):
        args = _build_pg_args({})
        assert args == []


class TestBuildPgEnv:
    """Environment variable building."""

    def test_sets_pgpassword(self):
        env = _build_pg_env({"password": "secret"})
        assert env["PGPASSWORD"] == "secret"

    def test_no_password(self):
        env = _build_pg_env({})
        assert "PGPASSWORD" not in env or env.get("PGPASSWORD") == os.environ.get("PGPASSWORD")


class TestResolveDbUrl:
    """Database URL resolution."""

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://from-env/db"})
    def test_env_var_takes_precedence(self, tmp_path):
        manifest = tmp_path / "dazzle.toml"
        manifest.write_text(
            '[project]\nname = "test"\nversion = "0.1.0"\nroot = "test"\n[modules]\npaths = ["./dsl"]\n'
        )
        assert _resolve_database_url(manifest) == "postgresql://from-env/db"

    @patch.dict("os.environ", {}, clear=False)
    def test_normalizes_postgres_scheme(self, tmp_path):
        os.environ.pop("DATABASE_URL", None)
        os.environ["DATABASE_URL"] = "postgres://host/db"
        result = _resolve_database_url(tmp_path / "dazzle.toml")
        assert result.startswith("postgresql://")
        os.environ.pop("DATABASE_URL", None)
