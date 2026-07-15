"""Unit tests for scripts/improve_schedule_next.py decision engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "improve_schedule_next.py"

pytestmark = pytest.mark.gate


def _load():
    spec = importlib.util.spec_from_file_location("improve_schedule_next", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sched():
    return _load()


def _base(**kwargs):
    d = {
        "counts": {"urgent": 0, "actionable": 0, "blocked": 0, "settled": 50},
        "explore_used": 100,
        "current_cycle": 647,
        "last_self_audit": 640,
        "last_capability_sweep": 635,
        "result": "PASS",
        "deployed": False,
        "force_stop": False,
        "ci": "unavailable",
        # Isolate from live .dazzle/improve-github-inbox.json on the machine
        "github_heat": "",
    }
    d.update(kwargs)
    return d


def test_parse_backlog_counts_actionable_and_urgent(sched):
    text = """
## Lane: framework-ux
| id | status |
| F-1 | REGRESSION |
| F-2 | PENDING |
| F-3 | DONE |

## Lane: trials
| TR-1 | bug | high | app | desc | 1 | 1 | OPEN_FRAMEWORK |
| TR-2 | bug | low | app | desc | 1 | 1 | OPEN_UNKNOWN |
"""
    counts = sched.parse_backlog_counts(text)
    assert counts["urgent"] >= 1
    assert counts["actionable"] >= 3  # REGRESSION + PENDING + OPEN_FRAMEWORK
    assert "REGRESSION" in counts["by_status"]
    assert "OPEN_FRAMEWORK" in counts["by_status"]


def test_parse_log_meta(sched):
    text = """
## Cycle 630 — 2026-07-14 — lane: capability-sweep — outcome: PASS
## Cycle 633 — 2026-07-14 — lane: self-audit — outcome: PASS
## Cycle 647 — 2026-07-15 — lane: hm-convergence — outcome: HOUSEKEEPING
"""
    meta = sched.parse_log_meta(text)
    assert meta["current_cycle"] == 647
    assert meta["last_self_audit"] == 633
    assert meta["last_capability_sweep"] == 630


def test_decide_regression_hot_immediate(sched):
    d = sched.decide(
        **_base(
            counts={"urgent": 1, "actionable": 1, "blocked": 0, "settled": 0},
        )
    )
    assert d["action"] == "schedule"
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "regression" in d["reason"]


def test_decide_fail_backoff(sched):
    d = sched.decide(**_base(result="FAIL", explore_used=0))
    assert d["interval"] == "10m"
    assert d["fire_immediately"] is False


def test_decide_ci_waiting_after_deploy(sched):
    d = sched.decide(
        **_base(
            deployed=True,
            ci="in_progress",
            explore_used=2,
            counts={"urgent": 0, "actionable": 1, "blocked": 0, "settled": 0},
        )
    )
    assert d["interval"] == "3m"
    assert d["fire_immediately"] is False
    assert "ci_waiting" in d["reason"]


def test_decide_ci_green_opportunistic_immediate(sched):
    d = sched.decide(
        **_base(
            deployed=True,
            ci="green",
            explore_used=2,
            counts={"urgent": 0, "actionable": 3, "blocked": 0, "settled": 0},
        )
    )
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "ci_green" in d["reason"]


def test_decide_ci_red_repair_soon(sched):
    d = sched.decide(
        **_base(
            deployed=True,
            ci="red",
            counts={"urgent": 0, "actionable": 0, "blocked": 0, "settled": 10},
            explore_used=50,
        )
    )
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "ci_red" in d["reason"]


def test_decide_explore_cap_inbox_reprobe(sched):
    """Quiet product state still re-polls GitHub regularly (not a multi-hour wait)."""
    d = sched.decide(**_base(ci="unavailable"))
    assert d["action"] == "schedule"
    assert d["interval"] == "15m"
    assert "inbox_reprobe" in d["reason"]


def test_decide_self_audit_due_work_interval(sched):
    d = sched.decide(
        **_base(
            last_self_audit=633,  # next 648 − 633 = 15 → due
            last_capability_sweep=629,
            ci="unavailable",
        )
    )
    assert d["interval"] == "5m"
    assert "self_audit_due" in d["reason"]


def test_decide_work_remaining_no_ci(sched):
    d = sched.decide(
        **_base(
            counts={"urgent": 0, "actionable": 4, "blocked": 0, "settled": 0},
            explore_used=10,
            ci="unavailable",
        )
    )
    assert d["interval"] == "5m"
    assert "work_remaining" in d["reason"]


def test_decide_github_dependabot_heat(sched):
    d = sched.decide(**_base(github_heat="dependabot_merge", explore_used=100))
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "dependabot" in d["reason"]


def test_decide_github_owner_bug_heat(sched):
    d = sched.decide(**_base(github_heat="owner_bug", explore_used=100))
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "owner_bug" in d["reason"]


def test_decide_github_consumer_bug_heat(sched):
    d = sched.decide(**_base(github_heat="consumer_bug", explore_used=100))
    assert d["interval"] == "2m"
    assert d["fire_immediately"] is True
    assert "consumer_bug" in d["reason"]


def test_decide_stop(sched):
    d = sched.decide(
        **_base(
            counts={"urgent": 0, "actionable": 5, "blocked": 0, "settled": 0},
            explore_used=0,
            force_stop=True,
        )
    )
    assert d["action"] == "stop"
    assert d["interval"] is None


def test_main_smoke(sched, tmp_path, monkeypatch, capsys):
    backlog = tmp_path / "improve-backlog.md"
    backlog.write_text("| x | PENDING |\n", encoding="utf-8")
    log = tmp_path / "improve-log.md"
    log.write_text(
        "## Cycle 10 — 2026-07-15 — lane: self-audit — outcome: PASS\n",
        encoding="utf-8",
    )
    explore = tmp_path / "improve-explore-count"
    explore.write_text("3\n", encoding="utf-8")
    state = tmp_path / "improve-schedule-state.json"

    monkeypatch.setattr(sched, "BACKLOG", backlog)
    monkeypatch.setattr(sched, "LOG", log)
    monkeypatch.setattr(sched, "EXPLORE_COUNT", explore)
    monkeypatch.setattr(sched, "STATE", state)
    monkeypatch.setattr(
        sched,
        "probe_ci_main",
        lambda: {"ci": "green", "detail": "test"},
    )

    rc = sched.main(["--result", "PASS", "--ci", "green"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"action": "schedule"' in out
    assert state.exists()
    body = state.read_text(encoding="utf-8")
    assert "scheduler_create" in body
    assert "fire_immediately" in body
