"""Dig contracts, divergence, receipts, process residual."""

from __future__ import annotations

import importlib.util
import json
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
    return _load("story_walk_bar_dc", "scripts/story_walk_bar.py")


@pytest.fixture(scope="module")
def receipt_mod():
    return _load("improve_dig_receipt_dc", "scripts/improve_dig_receipt.py")


@pytest.fixture(scope="module")
def trial_bar():
    return _load("trial_verdict_bar_dc", "scripts/trial_verdict_bar.py")


class TestDivergence:
    def test_support_walks_load(self, story_bar) -> None:
        row = story_bar.score_app("support_tickets")
        assert row.walk_count >= 2
        assert not any(i.startswith("diverge:unknown_story:") for i in row.issues)

    def test_weak_cues_on_generic_texts(self, story_bar) -> None:
        landings = story_bar.collect_landing_stories(_REPO / "examples" / "support_tickets")
        assert landings
        L = landings[0]
        from dazzle.testing.walk.models import SceneWalkSpec

        walk = SceneWalkSpec.model_validate(
            {
                "persona": L.persona,
                "home_workspace": L.home_workspace or "home",
                "scenes": [
                    {
                        "id": "s",
                        "story": L.story_id,
                        "entry": f"/app/workspaces/{L.home_workspace or 'home'}",
                        "actions": [
                            {"type": "navigate"},
                            {"type": "assert_any_text", "texts": ["Home"]},
                        ],
                    }
                ],
            }
        )
        walk.walk_id = "bad"
        div = story_bar._divergence_issues([L], [walk], {L.story_id})
        assert any("weak_cues" in i for i in div), div

    def test_entry_ws_mismatch(self, story_bar) -> None:
        landings = story_bar.collect_landing_stories(_REPO / "examples" / "support_tickets")
        L = next(x for x in landings if x.home_workspace)
        from dazzle.testing.walk.models import SceneWalkSpec

        walk = SceneWalkSpec.model_validate(
            {
                "persona": L.persona,
                "home_workspace": "wrong_ws",
                "scenes": [
                    {
                        "id": "s",
                        "story": L.story_id,
                        "entry": "/app/workspaces/wrong_ws",
                        "actions": [
                            {"type": "navigate"},
                            {"type": "assert_any_text", "texts": ["Ticket", "Queue"]},
                        ],
                    }
                ],
            }
        )
        walk.walk_id = "test"
        div = story_bar._divergence_issues([L], [walk], {L.story_id})
        assert any("entry_ws" in i for i in div), div


class TestReceipts:
    def test_write_and_check(self, receipt_mod, monkeypatch, tmp_path: Path) -> None:
        d = tmp_path / "digs"
        d.mkdir()
        monkeypatch.setattr(receipt_mod, "RECEIPT_DIR", d)
        monkeypatch.setattr(receipt_mod, "receipt_dir", lambda: d)

        r = receipt_mod.DigReceipt(
            app="contact_manager",
            strategy="story_walk",
            ts=receipt_mod._now_iso(),
            stories=["ST-004"],
            maps_cited=[{"path": "stems/x.md", "kind": "stem"}],
            walks_touched=["fixtures/scene_walks/a.yaml"],
            actuators={"walk_validate": 0, "walk_dry_run": 0, "live_skip_reason": "no_db"},
            outcome="PASS",
            epistemic=["live_unproven"],
        )
        path = receipt_mod.write_receipt(r)
        assert path.is_file()
        ok, reason, loaded = receipt_mod.check_latest("contact_manager", "story_walk")
        assert ok, reason
        assert loaded is not None
        assert loaded.stories == ["ST-004"]

    def test_incomplete_without_maps(self, receipt_mod, monkeypatch, tmp_path: Path) -> None:
        d = tmp_path / "digs2"
        d.mkdir()
        monkeypatch.setattr(receipt_mod, "RECEIPT_DIR", d)
        monkeypatch.setattr(receipt_mod, "receipt_dir", lambda: d)
        r = receipt_mod.DigReceipt(
            app="x",
            strategy="story_walk",
            stories=["ST-1"],
            maps_cited=[],
            actuators={"walk_validate": 0, "walk_dry_run": 0},
            outcome="PASS",
        )
        assert not r.contract_ok()
        path = receipt_mod.write_receipt(r)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["outcome"] == "contract_incomplete"

    def test_process_residual(self, receipt_mod, monkeypatch, tmp_path: Path) -> None:
        d = tmp_path / "digs3"
        d.mkdir()
        monkeypatch.setattr(receipt_mod, "RECEIPT_DIR", d)
        monkeypatch.setattr(receipt_mod, "receipt_dir", lambda: d)
        r = receipt_mod.DigReceipt(
            app="contact_manager",
            strategy="story_walk",
            stories=["ST-004"],
            maps_cited=[],
            actuators={},
            outcome="PASS",
        )
        receipt_mod.write_receipt(r)
        rows = receipt_mod.process_residual_apps()
        assert any(x["app"] == "contact_manager" for x in rows)


class TestTrialNoTrial:
    def test_showcase_trial_toml_present(self, trial_bar) -> None:
        for app in ("invoice_ops", "project_tracker", "hr_records"):
            assert (trial_bar.EXAMPLES / app / "trial.toml").is_file()
            row = trial_bar.score_app(app)
            assert "no_trial" not in row.issues
            assert row.has_trial_toml


class TestLiveGreen:
    def test_mark_live(self, receipt_mod, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(receipt_mod, "REPO", tmp_path)
        ex = tmp_path / "examples" / "myapp"
        (ex / "fixtures" / "scene_walks").mkdir(parents=True)
        path = receipt_mod.mark_live_green("myapp", ["land_and_see"])
        assert path.is_file()
        assert receipt_mod.is_walk_live_green(ex, "land_and_see")
        assert not receipt_mod.is_walk_live_green(ex, "other")


class TestProbesWire:
    def test_process_dig_in_status(self) -> None:
        mod = _load("improve_example_probes_dc", "scripts/improve_example_probes.py")
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = mod.main(["--status"])
        out = buf.getvalue()
        assert code == 0
        assert "process_dig" in out
        assert "story_walk" in out
