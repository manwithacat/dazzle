"""Unit tests for scripts/hm_standalone_ci_status.py (fast-fail job poll)."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
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
    updated_at: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "head_sha": sha,
        "html_url": f"https://example.test/run/{run_id}",
    }
    if updated_at is not None:
        payload["updated_at"] = updated_at
    return payload


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


def test_completed_run_age_seconds_parses_github_iso() -> None:
    mod = _load_mod()
    run = _run(
        run_id=1,
        status="completed",
        conclusion="failure",
        updated_at="2026-08-15T22:50:17Z",
    )
    now = datetime(2026, 8, 15, 23, 11, 14, tzinfo=UTC)
    age = mod.completed_run_age_seconds(run, now=now)
    assert age is not None
    assert 1250 <= age <= 1270  # ~21 minutes (2141 sample)


def test_prefer_completed_wait_follows_newer_after_stale_completed_red() -> None:
    """Cycle 2141: Dazzle CI started before the sibling HM run was listed."""
    mod = _load_mod()
    stale = _run(
        run_id=31912865017,
        status="completed",
        conclusion="failure",
        sha="c0b09eb6",
        updated_at="2026-08-15T22:50:17Z",
    )
    green = _run(
        run_id=31914122384,
        status="completed",
        conclusion="success",
        sha="d2e51bf1",
        updated_at="2026-08-15T23:23:54Z",
    )
    with (
        patch.object(mod, "latest_runs", side_effect=[[stale], [green, stale]]),
        patch.object(mod, "first_failed_job", return_value=None),
        patch.object(mod.time, "sleep"),
    ):
        code = mod.main(["--prefer-completed", "--wait", "30", "--poll", "1"])
    assert code == 0


def test_prefer_completed_wait_fails_immediately_on_fresh_completed_red() -> None:
    """A tip that just went red is not the 2141 sync race — fail now."""
    mod = _load_mod()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    red = _run(
        run_id=9,
        status="completed",
        conclusion="failure",
        updated_at=now,
    )
    with (
        patch.object(mod, "latest_runs", return_value=[red]),
        patch.object(mod.time, "sleep") as slept,
    ):
        code = mod.main(["--prefer-completed", "--wait", "30", "--poll", "1"])
    assert code == 1
    slept.assert_not_called()


def test_prefer_completed_wait_grace_zero_fails_stale_red() -> None:
    mod = _load_mod()
    red = _run(
        run_id=1,
        status="completed",
        conclusion="failure",
        updated_at="2026-08-15T20:00:00Z",
    )
    with (
        patch.object(mod, "latest_runs", return_value=[red]),
        patch.object(mod.time, "sleep") as slept,
    ):
        code = mod.main(
            [
                "--prefer-completed",
                "--wait",
                "30",
                "--poll",
                "1",
                "--stale-red-grace",
                "0",
            ]
        )
    assert code == 1
    slept.assert_not_called()


def test_completed_red_without_wait_fails_immediately() -> None:
    """Local push_gate has no --wait; a completed red is still red."""
    mod = _load_mod()
    red = _run(
        run_id=1,
        status="completed",
        conclusion="failure",
        updated_at="2026-08-15T20:00:00Z",
    )
    with (
        patch.object(mod, "latest_runs", return_value=[red]),
        patch.object(mod.time, "sleep") as slept,
    ):
        code = mod.main(["--prefer-completed"])
    assert code == 1
    slept.assert_not_called()


def test_maybe_reset_wait_deadline_on_new_inflight_tip() -> None:
    """Cycle 2146: switching from stale red to a new tip restarts --wait."""
    mod = _load_mod()
    reset_at, tracked = mod.maybe_reset_wait_deadline(
        wait=900,
        run_id=31920607365,
        status="in_progress",
        tracked_id=31919355191,
        now_mono=80.0,
    )
    assert reset_at == 980.0
    assert tracked == 31920607365


def test_maybe_reset_wait_deadline_skips_same_run_and_first_pick() -> None:
    mod = _load_mod()
    reset_at, tracked = mod.maybe_reset_wait_deadline(
        wait=900,
        run_id=2,
        status="in_progress",
        tracked_id=2,
        now_mono=80.0,
    )
    assert reset_at is None
    assert tracked == 2
    reset_at, tracked = mod.maybe_reset_wait_deadline(
        wait=900,
        run_id=2,
        status="in_progress",
        tracked_id=None,
        now_mono=0.0,
    )
    assert reset_at is None
    assert tracked == 2
    reset_at, tracked = mod.maybe_reset_wait_deadline(
        wait=900,
        run_id=2,
        status="completed",
        tracked_id=1,
        now_mono=80.0,
    )
    assert reset_at is None
    assert tracked == 2


def test_wait_resets_deadline_when_new_tip_appears_after_stale_red() -> None:
    """Stale-red hunt must not expire the budget for the sibling visual run."""
    mod = _load_mod()
    stale = _run(
        run_id=31919355191,
        status="completed",
        conclusion="failure",
        sha="0e151cfb",
        updated_at="2026-08-16T01:27:18Z",
    )
    inflight = _run(
        run_id=31920607365,
        status="in_progress",
        conclusion=None,
        sha="ed9a6fd5",
    )
    green = _run(
        run_id=31920607365,
        status="completed",
        conclusion="success",
        sha="ed9a6fd5",
    )
    polls = [
        [stale],
        [inflight, stale],
        [inflight, stale],
        [inflight, stale],
        [green, stale],
    ]
    clock = {"t": 0.0}

    def mono() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += float(seconds)

    with (
        patch.object(mod, "latest_runs", side_effect=polls),
        patch.object(mod, "first_failed_job", return_value=None),
        patch.object(mod.time, "monotonic", side_effect=mono),
        patch.object(mod.time, "sleep", side_effect=sleep),
    ):
        # wait=50 / poll=20: without reset, inflight at t=60 expires the
        # original deadline (50). Reset at t=20 extends to 70, then green.
        code = mod.main(["--prefer-completed", "--wait", "50", "--poll", "20"])
    assert code == 0


def test_ci_yml_hm_mirror_wait_covers_visual_suite() -> None:
    """Cycle 2146: HM visual ~15m + sync; --wait 900 expired 46s early."""
    import re

    repo = Path(__file__).resolve().parents[2]
    texts = [
        (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        (repo / ".github/workflows/sync-hatchi-maxchi.yml").read_text(encoding="utf-8"),
    ]
    waits: list[int] = []
    for text in texts:
        waits.extend(
            int(n) for n in re.findall(r"hm_standalone_ci_status\.py[^\n]*--wait (\d+)", text)
        )
    assert waits, "expected --wait on hm_standalone_ci_status in CI workflows"
    floor = int(getattr(_load_mod(), "_MIN_CI_WAIT_SECONDS", 1200))
    assert all(w >= floor for w in waits), waits


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
