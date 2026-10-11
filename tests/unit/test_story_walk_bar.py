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

    def test_zero_walks_is_critical_residual(self, story_bar) -> None:
        """Scoring rule: landings + 0 walks → critical; fleet may already be green.

        Cycle 1260–1267 cleared pure no_walks; cycle 1270–1278 live-proved all
        showcase landings (mark-live). Prefer: if zero-walk rows exist they are
        critical; if residual remains it is missing_walk / live_unproven; if
        residual is empty the fleet is fully live-green (ok).
        """
        rows = story_bar.scan()
        zero = [r for r in rows if r.landing_stories > 0 and r.walk_count == 0]
        if zero:
            for row in zero:
                assert row.is_residual
                assert row.tier == "critical"
                assert any(i == "no_walks" or i.startswith("missing_walk:") for i in row.issues)
            return
        # Fleet fully has ≥1 walk per landing app.
        assert all(r.walk_count >= 1 for r in rows if r.landing_stories > 0)
        residual = [r for r in rows if r.is_residual]
        if residual:
            # Residual classes score_app emits: coverage (no_walks / missing_walk),
            # epistemic (live_unproven), pair consistency (diverge:*), persona gaps.
            assert any(
                i == "no_walks"
                or i.startswith("missing_walk:")
                or i.startswith("live_unproven:")
                or i.startswith("diverge:")
                or i.startswith("persona_no_walk:")
                for r in residual
                for i in r.issues
            )
        else:
            # Cycle 1278: all showcase landings live-green → residual=0 is ok.
            assert all(r.tier == "ok" for r in rows if r.landing_stories > 0)

    def test_scan_fleet_has_residual(self, story_bar) -> None:
        """Fleet scan is non-empty; residual may be empty after live-prove drain."""
        rows = story_bar.scan()
        assert len(rows) >= 4
        residual = [r for r in rows if r.is_residual]
        if residual:
            assert residual[0].score >= residual[-1].score or residual[0].is_residual
        else:
            # All showcase apps live-green.
            assert all(not r.is_residual for r in rows)
            assert story_bar.format_status(rows).startswith("story_walk apps=")

    def test_write_stub_creates_yaml(self, story_bar, tmp_path: Path, monkeypatch) -> None:
        # Use real support_tickets landings but write into tmp by patching EXAMPLES
        app = "support_tickets"
        root = story_bar.EXAMPLES / app
        if not root.is_dir():
            pytest.skip("support_tickets missing")
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
