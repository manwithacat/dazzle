"""Unit tests for the MCP e2e handler dispatch."""

import json
from pathlib import Path

import pytest

from dazzle.mcp.server.handlers.e2e import (
    e2e_describe_mode_handler,
    e2e_list_baselines_handler,
    e2e_list_modes_handler,
    e2e_status_handler,
)


@pytest.fixture(autouse=True)
def mock_pg_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend pg_dump/pg_restore are on PATH.

    e2e_list_baselines_handler instantiates a BaselineManager, which
    constructs a Snapshotter, which probes for pg_dump. Mock it so this
    test runs on CI without postgresql-client-16 installed.
    """
    monkeypatch.setattr(
        "dazzle.e2e.snapshot.shutil.which",
        lambda name: f"/usr/local/bin/{name}",
    )


def test_list_modes_returns_mode_a_entry(tmp_path: Path) -> None:
    result = json.loads(e2e_list_modes_handler(tmp_path, {}))
    assert "modes" in result
    assert len(result["modes"]) >= 1
    names = [m["name"] for m in result["modes"]]
    assert "a" in names


def test_describe_mode_returns_mode_a_fields(tmp_path: Path) -> None:
    result = json.loads(e2e_describe_mode_handler(tmp_path, {"name": "a"}))
    assert result["name"] == "a"
    assert "description" in result
    assert "db_policy_default" in result
    assert "db_policies_allowed" in result
    assert result["db_policy_default"] == "preserve"


def test_describe_mode_returns_error_on_unknown(tmp_path: Path) -> None:
    result = json.loads(e2e_describe_mode_handler(tmp_path, {"name": "z"}))
    assert "error" in result


def test_status_scans_examples_dir_when_no_project_root(tmp_path: Path) -> None:
    # Create a fake project layout
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    fake_example = examples_dir / "fake"
    fake_example.mkdir()
    (fake_example / "dazzle.toml").write_text("[project]\nname='fake'\n")
    (fake_example / ".dazzle").mkdir()

    result = json.loads(e2e_status_handler(tmp_path, {}))
    assert "examples" in result
    assert len(result["examples"]) == 1
    assert result["examples"][0]["name"] == "fake"
    assert result["examples"][0]["lock_file"] is None


def test_status_explicit_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    result = json.loads(e2e_status_handler(tmp_path, {"project_root": str(project)}))
    assert result["project_root"] == str(project)
    assert result["lock_file"] is None
    assert result["runtime_file"] is None


def test_list_baselines_empty_when_no_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    result = json.loads(e2e_list_baselines_handler(tmp_path, {"project_root": str(project)}))
    assert result == {"baselines": []}


def test_list_baselines_lists_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    baselines_dir = project / ".dazzle" / "baselines"
    baselines_dir.mkdir(parents=True)
    (baselines_dir / "baseline-abc123-def456789012.sql.gz").write_bytes(b"fake")
    (baselines_dir / "baseline-xyz789-012345678901.sql.gz").write_bytes(b"fake")

    result = json.loads(e2e_list_baselines_handler(tmp_path, {"project_root": str(project)}))
    assert len(result["baselines"]) == 2
    filenames = [b["filename"] for b in result["baselines"]]
    assert "baseline-abc123-def456789012.sql.gz" in filenames
    assert "baseline-xyz789-012345678901.sql.gz" in filenames
    # alembic_rev and fixture_hash_prefix should be extracted
    for entry in result["baselines"]:
        assert "alembic_rev" in entry
        assert "fixture_hash_prefix" in entry
        assert "size_bytes" in entry
        assert "mtime" in entry
