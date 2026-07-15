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


def test_decide_regression_hot(sched):
    d = sched.decide(
        counts={"urgent": 1, "actionable": 1, "blocked": 0, "settled": 0},
        explore_used=100,
        current_cycle=647,
        last_self_audit=633,
        last_capability_sweep=629,
        result="PASS",
        deployed=False,
        force_stop=False,
    )
    assert d["action"] == "schedule"
    assert d["interval"] == "15m"
    assert "regression" in d["reason"]


def test_decide_fail_backoff(sched):
    d = sched.decide(
        counts={"urgent": 0, "actionable": 0, "blocked": 0, "settled": 10},
        explore_used=0,
        current_cycle=10,
        last_self_audit=1,
        last_capability_sweep=1,
        result="FAIL",
        deployed=False,
        force_stop=False,
    )
    assert d["interval"] == "30m"


def test_decide_explore_cap_slow_poll(sched):
    d = sched.decide(
        counts={"urgent": 0, "actionable": 0, "blocked": 0, "settled": 50},
        explore_used=100,
        current_cycle=647,
        last_self_audit=640,  # next 648 − 640 = 8 < 15
        last_capability_sweep=635,  # next 648 − 635 = 13 < 20
        result="PASS",
        deployed=False,
        force_stop=False,
    )
    assert d["action"] == "schedule"
    assert d["interval"] == "2h"
    assert "explore_cap" in d["reason"] or "all_clear" in d["reason"]


def test_decide_self_audit_due(sched):
    d = sched.decide(
        counts={"urgent": 0, "actionable": 0, "blocked": 0, "settled": 50},
        explore_used=100,
        current_cycle=647,
        last_self_audit=633,  # next 648 − 633 = 15 → due
        last_capability_sweep=629,
        result="PASS",
        deployed=False,
        force_stop=False,
    )
    assert d["interval"] == "15m"
    assert "self_audit_due" in d["reason"]


def test_decide_stop(sched):
    d = sched.decide(
        counts={"urgent": 0, "actionable": 5, "blocked": 0, "settled": 0},
        explore_used=0,
        current_cycle=1,
        last_self_audit=None,
        last_capability_sweep=None,
        result="PASS",
        deployed=False,
        force_stop=True,
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

    rc = sched.main(["--result", "PASS"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"action": "schedule"' in out
    assert state.exists()
    assert "scheduler_create" in state.read_text(encoding="utf-8")
