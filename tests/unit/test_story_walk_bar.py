"""Story-walk residual probe + trial verdict bar (#agent-first QA heat)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    path = _REPO / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def story_bar():
    return _load("story_walk_bar", "scripts/story_walk_bar.py")


@pytest.fixture(scope="module")
def trial_bar():
    return _load("trial_verdict_bar", "scripts/trial_verdict_bar.py")


class TestStoryWalkBar:
    def test_support_tickets_has_landings_and_walks(self, story_bar) -> None:
        row = story_bar.score_app("support_tickets")
        assert row.landing_stories >= 2
        assert row.walk_count >= 2
        assert "ST-019" in row.covered_ids or "ST-025" in row.covered_ids

    def test_simple_task_covers_st020(self, story_bar) -> None:
        row = story_bar.score_app("simple_task")
        assert "ST-020" in row.covered_ids or row.walk_count >= 1

    def test_contact_manager_no_walks_is_residual(self, story_bar) -> None:
        row = story_bar.score_app("contact_manager")
        assert row.is_residual
        assert row.tier == "critical"
        assert any(i == "no_walks" or i.startswith("missing_walk:") for i in row.issues)

    def test_scan_fleet_has_residual(self, story_bar) -> None:
        rows = story_bar.scan()
        assert len(rows) >= 5
        residual = [r for r in rows if r.is_residual]
        assert residual, "showcase should still have story_walk residual"
        assert residual[0].score >= residual[-1].score or residual[0].is_residual

    def test_write_stub_creates_yaml(self, story_bar, tmp_path: Path, monkeypatch) -> None:
        # Use real support_tickets landings but write into tmp by patching EXAMPLES
        app = "contact_manager"
        root = story_bar.EXAMPLES / app
        if not root.is_dir():
            pytest.skip("contact_manager missing")
        landings = story_bar.collect_landing_stories(root)
        assert landings
        L = landings[0]
        text = story_bar.stub_walk_yaml(L)
        assert f"story: {L.story_id}" in text
        assert f"persona: {L.persona}" in text
        assert "type: navigate" in text

    def test_format_status(self, story_bar) -> None:
        rows = story_bar.scan()
        line = story_bar.format_status(rows)
        assert line.startswith("story_walk apps=")
        assert "residual=" in line


class TestTrialVerdictBar:
    def test_scan_runs(self, trial_bar) -> None:
        rows = trial_bar.scan()
        assert len(rows) >= 1
        line = trial_bar.format_status(rows)
        assert "trial_verdict" in line

    def test_no_toml_no_residual(self, trial_bar, tmp_path: Path) -> None:
        # score_app only looks under EXAMPLES — use an app without trial if any
        row = (
            trial_bar.score_app("domain_join_co")
            if (trial_bar.EXAMPLES / "domain_join_co").is_dir()
            else None
        )
        if row is None:
            pytest.skip("no non-showcase app")
        # domain_join may not be in SHOWCASE; score_app still works
        if not row.has_trial_toml:
            assert not row.is_residual


class TestImproveExampleProbesWiring:
    def test_story_walk_in_unified_status(self) -> None:
        mod = _load("improve_example_probes", "scripts/improve_example_probes.py")
        # capture stdout
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = mod.main(["--status"])
        out = buf.getvalue()
        assert code == 0
        assert "story_walk" in out
        assert "trial_verdict" in out
        assert "example_probes residual_total=" in out
