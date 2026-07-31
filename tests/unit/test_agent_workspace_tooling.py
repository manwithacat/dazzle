"""Unit tests for agent-loop reliability tooling (#1626 recapture path).

Covers:
* scripts/agent_workspace_health.py
* scripts/recapture_demo_fleet_1626.py helpers (no live serve)
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def health():
    return _load("agent_workspace_health", REPO / "scripts" / "agent_workspace_health.py")


@pytest.fixture(scope="module")
def recapture():
    return _load("recapture_demo_fleet_1626", REPO / "scripts" / "recapture_demo_fleet_1626.py")


def test_health_live_repo_passes(health) -> None:
    """Workspace preflight against this monorepo must be green (no postgres)."""
    report = health.check_workspace(REPO, ["invoice_ops"], require_postgres=False)
    assert report.ok, [c for c in report.checks if not c.ok]
    ids = {c.id for c in report.checks}
    assert "root" in ids
    assert "git" in ids or "git_config" in ids
    assert "dazzle_import" in ids or "venv" in ids


def test_health_missing_root_fails(health, tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    report = health.check_workspace(missing, [], require_postgres=False)
    assert not report.ok
    assert any(c.id == "root" and not c.ok for c in report.checks)


def test_health_cli_json(health, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_workspace_health.py",
            "--root",
            str(REPO),
            "--apps",
            "invoice_ops",
            "--json",
        ],
    )
    rc = health.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["checks"]


def test_recapture_wait_http_consecutive(recapture) -> None:
    """Readiness needs N consecutive successes, not a single fluke."""
    calls = {"n": 0}

    def fake_ok(url: str, *, timeout: float = 2.0) -> bool:
        calls["n"] += 1
        # fail, fail, ok, fail, ok, ok, ok → ready on 3 consecutive
        pattern = [False, False, True, False, True, True, True]
        idx = min(calls["n"] - 1, len(pattern) - 1)
        return pattern[idx]

    with patch.object(recapture, "_http_ok", side_effect=fake_ok):
        with patch.object(recapture.time, "sleep", return_value=None):
            assert recapture._wait_http("http://example", timeout=10.0, consecutive=3) is True
    assert calls["n"] >= 7


def test_recapture_wait_http_timeout(recapture) -> None:
    with patch.object(recapture, "_http_ok", return_value=False):
        with patch.object(recapture.time, "sleep", return_value=None):
            with patch.object(recapture.time, "time", side_effect=[0.0, 0.0, 100.0]):
                assert recapture._wait_http("http://example", timeout=1.0, consecutive=3) is False


def test_recapture_serve_log_not_pipe(recapture) -> None:
    """Regression: serve must log to a file path helper (never bare PIPE)."""
    project = REPO / "examples" / "invoice_ops"
    path = recapture._serve_log_path(project, "invoice_ops", "finance")
    assert path.parent.name == "recapture-logs"
    assert "invoice_ops" in path.name
    assert path.suffix == ".log"


def test_recapture_http_ok_handles_url_error(recapture) -> None:
    with patch.object(
        recapture.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("down"),
    ):
        assert recapture._http_ok("http://127.0.0.1:9/") is False


def test_recapture_preflight_invokes_health(recapture, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str]] = []

    def fake_call(cmd, cwd=None):  # noqa: ANN001
        called.append(list(cmd))
        return 0

    monkeypatch.setattr(recapture.subprocess, "call", fake_call)
    rc = recapture.run_preflight(["invoice_ops"], require_postgres=True)
    assert rc == 0
    assert called
    assert "agent_workspace_health.py" in called[0][1]
    assert "--require-postgres" in called[0]


def test_recapture_main_preflight_only(recapture, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        recapture,
        "run_preflight",
        lambda apps, require_postgres=True: 0,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["recapture_demo_fleet_1626.py", "--preflight-only", "--apps", "invoice_ops"],
    )
    rc = recapture.main()
    assert rc == 0
    assert "preflight PASS" in capsys.readouterr().out


def test_macos_script_exists_and_executable() -> None:
    script = REPO / "scripts" / "macos_agent_volume_access.sh"
    assert script.is_file()
    # executable bit set for owner
    assert script.stat().st_mode & 0o111


def test_recapture_docstring_mentions_pipe_deadlock(recapture) -> None:
    doc = recapture.__doc__ or ""
    assert "PIPE" in doc
    assert "preflight" in doc.lower()
