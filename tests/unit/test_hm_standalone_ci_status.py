"""Unit tests for scripts/hm_standalone_ci_status.py (fast-fail job poll)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.gate

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hm_standalone_ci_status.py"


def _load_mod() -> Any:
    spec = importlib.util.spec_from_file_location("hm_standalone_ci_status", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_first_failed_job_returns_failed() -> None:
    mod = _load_mod()
    payload = {
        "jobs": [
            {"name": "Contract", "conclusion": "success", "status": "completed"},
            {"name": "Visual regression", "conclusion": "failure", "status": "completed"},
            {"name": "Behaviour", "conclusion": None, "status": "in_progress"},
        ]
    }
    with patch.object(mod, "_get", return_value=payload):
        bad = mod.first_failed_job(12345)
    assert bad is not None
    assert bad["name"] == "Visual regression"
    assert bad["conclusion"] == "failure"


def test_first_failed_job_none_when_all_ok_or_running() -> None:
    mod = _load_mod()
    payload = {
        "jobs": [
            {"name": "Contract", "conclusion": "success", "status": "completed"},
            {"name": "Behaviour", "conclusion": None, "status": "in_progress"},
        ]
    }
    with patch.object(mod, "_get", return_value=payload):
        assert mod.first_failed_job(99) is None


def test_wait_early_exits_when_job_already_failed() -> None:
    """--wait must not hang after Visual is red while Behaviour still runs."""
    mod = _load_mod()
    run = {
        "id": 42,
        "status": "in_progress",
        "conclusion": None,
        "head_sha": "abc12345deadbeef",
        "html_url": "https://example.test/run/42",
    }
    with (
        patch.object(mod, "latest_runs", return_value=[run]),
        patch.object(
            mod,
            "first_failed_job",
            return_value={"name": "Visual regression", "conclusion": "failure"},
        ),
    ):
        code = mod.main(["--wait", "60", "--poll", "1", "--sha", "abc12345"])
    assert code == 1


def _run(
    *,
    run_id: int,
    status: str,
    conclusion: str | None,
    sha: str = "abc12345",
) -> dict[str, Any]:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "head_sha": sha,
        "html_url": f"https://example.test/run/{run_id}",
    }


def test_prefer_completed_skips_inflight_when_last_completed_is_green() -> None:
    mod = _load_mod()
    inflight = _run(run_id=2, status="in_progress", conclusion=None)
    green = _run(run_id=1, status="completed", conclusion="success")
    picked = mod.pick_run([inflight, green], sha=None, prefer_completed=True)
    assert picked is not None
    assert picked["id"] == 1


def test_prefer_completed_does_not_sample_stale_red_over_inflight() -> None:
    """Cycle 2136/2137: last completed red + newer tip running → pick tip."""
    mod = _load_mod()
    inflight = _run(run_id=2, status="in_progress", conclusion=None)
    red = _run(run_id=1, status="completed", conclusion="failure")
    picked = mod.pick_run([inflight, red], sha=None, prefer_completed=True)
    assert picked is not None
    assert picked["id"] == 2
    assert picked["status"] == "in_progress"


def test_prefer_completed_picks_newest_completed_even_when_red() -> None:
    mod = _load_mod()
    red = _run(run_id=2, status="completed", conclusion="failure")
    green = _run(run_id=1, status="completed", conclusion="success")
    picked = mod.pick_run([red, green], sha=None, prefer_completed=True)
    assert picked is not None
    assert picked["id"] == 2
    assert picked["conclusion"] == "failure"


def test_prefer_completed_wait_follows_tip_after_stale_red() -> None:
    """CI --wait must poll the in-flight tip, not exit 1 on stale red."""
    mod = _load_mod()
    inflight = _run(run_id=2, status="in_progress", conclusion=None)
    red = _run(run_id=1, status="completed", conclusion="failure")
    green = _run(run_id=2, status="completed", conclusion="success")
    with (
        patch.object(mod, "latest_runs", side_effect=[[inflight, red], [green, red]]),
        patch.object(mod, "first_failed_job", return_value=None),
        patch.object(mod.time, "sleep"),
    ):
        code = mod.main(["--prefer-completed", "--wait", "30", "--poll", "1"])
    assert code == 0


def test_wait_continues_when_no_failed_job_yet() -> None:
    mod = _load_mod()
    running = {
        "id": 7,
        "status": "in_progress",
        "conclusion": None,
        "head_sha": "fff111",
        "html_url": "https://example.test/run/7",
    }
    done = {
        **running,
        "status": "completed",
        "conclusion": "success",
    }
    # First poll: still running, no failed job → sleep path.
    # Second poll: completed success → 0.
    with (
        patch.object(mod, "latest_runs", side_effect=[[running], [done]]),
        patch.object(mod, "first_failed_job", return_value=None),
        patch.object(mod.time, "sleep"),  # don't actually sleep
    ):
        code = mod.main(["--wait", "30", "--poll", "1", "--sha", "fff111"])
    assert code == 0
