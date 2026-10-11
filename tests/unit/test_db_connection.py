"""Tests for dazzle.db.connection — database URL resolution and connection factory."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.db.connection import resolve_db_target, resolve_db_url


class TestResolveDbUrl:
    def test_explicit_url_wins(self) -> None:
        url = resolve_db_url(explicit_url="postgresql://localhost/mydb")
        assert url == "postgresql://localhost/mydb"

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://env/db"}, clear=False)
    def test_env_var_fallback(self) -> None:
        url = resolve_db_url()
        assert url == "postgresql://env/db"

    @patch("dazzle.db.connection.load_manifest")
    @patch("dazzle.db.connection.Path.exists", return_value=True)
    def test_manifest_fallback(self, mock_exists: MagicMock, mock_load: MagicMock) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict("os.environ", env, clear=True):
            manifest = MagicMock()
            manifest.database.url = "postgresql://manifest/db"
            mock_load.return_value = manifest
            url = resolve_db_url(project_root=Path("/fake/project"))
            assert url == "postgresql://manifest/db"

    def test_default_when_nothing_set(self) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict("os.environ", env, clear=True):
            url = resolve_db_url()
            assert "postgresql://" in url


@pytest.mark.parametrize(
    ("explicit", "env_url", "expected_db", "expected_source"),
    [
        ("", "postgresql://localhost/app_test", "app_test", "DATABASE_URL"),
        (
            "postgresql://localhost/app_flag",
            "postgresql://localhost/app_test",
            "app_flag",
            "--database-url",
        ),
        ("", "", "dazzle", "manifest"),
    ],
    ids=["env_beats_runtime_json", "flag_beats_env_and_runtime_json", "manifest_not_runtime_json"],
)
def test_runtime_json_never_supplies_db_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit: str,
    env_url: str,
    expected_db: str,
    expected_source: str,
) -> None:
    """#1775: a stale serve's runtime.json must not redirect `dazzle db` commands."""
    (tmp_path / ".dazzle").mkdir()
    (tmp_path / ".dazzle" / "runtime.json").write_text(
        json.dumps({"ui_port": 3000, "database_url": "postgresql://localhost/app_dev"})
    )
    if env_url:
        monkeypatch.setenv("DATABASE_URL", env_url)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)

    target = resolve_db_target(explicit_url=explicit, project_root=tmp_path)

    assert target.url.rsplit("/", 1)[-1] == expected_db
    assert target.source == expected_source
