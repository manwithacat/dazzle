"""`scripts/repo_reconcile.py` — the record-vs-code reconciler.

The reconciler answers "does the repository's own record still describe it?" in
one command. These tests cover the judgement calls it makes, because a
reconciler that over-reports gets ignored the same way a gate that cries wolf
does:

* an issue cited by a merged commit is a **review queue**, not a closure — the
  common case is a commit that cites the issue as a *residual* tracker;
* a stopped loop must read as stopped, not as quiet;
* an unreachable `gh` must read as "could not tell", never as "clean" — the same
  three-state distinction `scripts/pip_audit.py` makes.

No network: `gh` is stubbed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "repo_reconcile.py"


def _load() -> Any:
    name = "dazzle_scripts_repo_reconcile"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rr = _load()


# ---------------------------------------------------------------------------
# stale issues
# ---------------------------------------------------------------------------


def test_issue_cited_by_a_merged_commit_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    report = rr.Report()
    monkeypatch.setattr(rr, "_gh_json", lambda *a: [{"number": 1746, "title": "dedup shipped"}])
    monkeypatch.setattr(rr, "merged_commit_messages", lambda limit=400: ["refactor: dedup (#1746)"])

    rr.check_stale_issues(report)

    assert [f.kind for f in report.findings] == ["stale-issue"]
    assert "1746" in report.findings[0].ref
    assert report.facts["open_issues"] == 1


def test_an_uncited_issue_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    report = rr.Report()
    monkeypatch.setattr(rr, "_gh_json", lambda *a: [{"number": 1742, "title": "still open"}])
    monkeypatch.setattr(rr, "merged_commit_messages", lambda limit=400: ["refactor: dedup (#1746)"])

    rr.check_stale_issues(report)

    assert report.findings == []


def test_issue_numbers_do_not_match_as_substrings(monkeypatch: pytest.MonkeyPatch) -> None:
    """`#174` must not match a commit citing `#1746`."""
    report = rr.Report()
    monkeypatch.setattr(rr, "_gh_json", lambda *a: [{"number": 174, "title": "x"}])
    monkeypatch.setattr(rr, "merged_commit_messages", lambda limit=400: ["fix: thing (#1746)"])

    rr.check_stale_issues(report)

    assert report.findings == []


def test_a_merge_commit_body_counts_not_just_the_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """Squash merges put the issue reference in the body, not the subject."""
    report = rr.Report()
    monkeypatch.setattr(rr, "_gh_json", lambda *a: [{"number": 1720, "title": "shims"}])
    monkeypatch.setattr(
        rr, "merged_commit_messages", lambda limit=400: ["chore: cleanup", "", "Refs #1720"]
    )

    rr.check_stale_issues(report)

    assert [f.kind for f in report.findings] == ["stale-issue"]


def test_unreachable_gh_is_could_not_tell_not_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """The #1745 lesson: no verdict must never read as clean."""
    report = rr.Report()
    monkeypatch.setattr(rr, "_gh_json", lambda *a: None)

    rr.check_stale_issues(report)

    assert [f.severity for f in report.findings] == ["notice"]
    assert "could not read" in report.findings[0].detail
    assert "open_issues" not in report.facts


# ---------------------------------------------------------------------------
# loop state
# ---------------------------------------------------------------------------


def test_a_stopped_loop_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    report = rr.Report()
    monkeypatch.setattr(rr, "_age_days", lambda path: 29.0)
    monkeypatch.setattr(rr, "_backlog_kb", lambda: 50.0)

    rr.check_loop_state(report)

    kinds = [f.kind for f in report.findings]
    assert "improve-loop" in kinds
    assert "improve-state" not in kinds, "a 50 KB backlog is under the threshold"


def test_a_backlog_over_its_own_threshold_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    report = rr.Report()
    monkeypatch.setattr(rr, "_age_days", lambda path: 0.0)
    monkeypatch.setattr(rr, "_backlog_kb", lambda: 202.0)

    rr.check_loop_state(report)

    assert [f.kind for f in report.findings] == ["improve-state"]
    assert "improve_compact.py" in report.findings[0].detail


def test_healthy_loop_and_backlog_report_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    report = rr.Report()
    monkeypatch.setattr(rr, "_age_days", lambda path: 0.2)
    monkeypatch.setattr(rr, "_backlog_kb", lambda: 80.0)

    rr.check_loop_state(report)

    assert report.findings == []
    assert report.facts["backlog_kb"] == 80.0


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def test_render_states_that_a_stale_hit_is_a_queue_not_a_closure() -> None:
    report = rr.Report()
    report.add("stale-issue", "#1 is open but cited", "action", "https://x/1")

    out = rr.render(report)

    assert "review queue" in out or "residual" in out
    assert "#1 is open but cited" in out


def test_a_coherent_record_says_so() -> None:
    out = rr.render(rr.Report())

    assert "coherent" in out


def test_json_output_carries_the_facts(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(rr, "build_report", lambda **kw: rr.Report(facts={"open_issues": 3}))

    assert rr.main(["--json"]) == 0

    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["coherent"] is True
    assert payload["facts"]["open_issues"] == 3


def test_findings_do_not_fail_the_build() -> None:
    """Advisory by design: the reconciler is a reading, not a gate."""
    assert rr.main(["--skip-github", "--skip-harness"]) == 0
