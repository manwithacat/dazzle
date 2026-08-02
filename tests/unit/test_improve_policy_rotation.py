"""Aggressive campaign rotation skips drained hyperpart_coherence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def test_hm_coherence_queue_depth_reads_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.improve_policy as pol

    monkeypatch.setattr(pol, "REPO", tmp_path)
    path = tmp_path / ".dazzle" / "hm-hyperpart-coherence" / "coherence.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"n_incoherent": 0, "results": []}', encoding="utf-8")
    assert pol.hm_coherence_queue_depth() == 0
    path.write_text('{"n_incoherent": 3, "results": []}', encoding="utf-8")
    assert pol.hm_coherence_queue_depth() == 3


def test_drained_hyperpart_skipped_under_require_mutation() -> None:
    import scripts.improve_policy as pol

    rotation = [
        {
            "force_args": "hm-convergence hyperpart_coherence",
            "lane": "hm-convergence",
            "strategy": "hyperpart_coherence",
        },
        {
            "force_args": "framework-ux",
            "lane": "framework-ux",
            "strategy": "framework-ux",
        },
    ]
    with (
        patch.object(pol, "dual_lock_queue_depth", return_value=0),
        patch.object(pol, "hm_coherence_queue_depth", return_value=0),
        patch.object(pol, "last_strategy_cycle", return_value=100),
        patch.object(pol, "recent_strategy_streak", return_value=0),
    ):
        picked = pol._pick_rotation(
            rotation,
            cur=200,
            campaign_id="aggressive-change",
            camp={"require_mutation": True, "max_consecutive_panels": 2},
            smoke_n=0,
        )
    assert picked is not None
    assert picked["force_args"] == "framework-ux"
    assert "skip_drained_hyperpart" in picked["reason"]
    assert picked["coherence_queue_depth"] == 0


def test_missing_coherence_keeps_hyperpart_eligible() -> None:
    """No coherence.json → investigate due; hyperpart stays in rotation."""
    import scripts.improve_policy as pol

    rotation = [
        {
            "force_args": "hm-convergence hyperpart_coherence",
            "lane": "hm-convergence",
            "strategy": "hyperpart_coherence",
        },
        {
            "force_args": "framework-ux",
            "lane": "framework-ux",
            "strategy": "framework-ux",
        },
    ]
    with (
        patch.object(pol, "dual_lock_queue_depth", return_value=0),
        patch.object(pol, "hm_coherence_queue_depth", return_value=None),
        patch.object(
            pol, "last_strategy_cycle", side_effect=lambda s: None if "hyperpart" in s else 50
        ),
        patch.object(pol, "recent_strategy_streak", return_value=0),
    ):
        picked = pol._pick_rotation(
            rotation,
            cur=200,
            campaign_id="aggressive-change",
            camp={"require_mutation": True},
            smoke_n=0,
        )
    assert picked is not None
    assert "hyperpart_coherence" in str(picked["force_args"])


def test_interesting_product_when_residual_green_and_open_hop_cap() -> None:
    """Post-5.8: residual=0 + open-hop streak ≥ cap → Goal B depth pack."""
    import scripts.improve_policy as pol

    policy = {
        "active_campaign": "aggressive-change",
        "steady_state": {"max_consecutive_open_hop": 5},
        "campaigns": {
            "aggressive-change": {
                "require_mutation": True,
                "interesting_product_when_green": True,
                "max_consecutive_open_hop": 5,
                "prefer_rotation": [
                    {
                        "force_args": "example-apps story_walk",
                        "lane": "example-apps",
                        "strategy": "story_walk",
                    }
                ],
            }
        },
    }
    with (
        patch.object(pol, "qa_smoke_residual", return_value=(0, None)),
        patch.object(pol, "product_residual_total", return_value=0),
        patch.object(pol, "consecutive_open_hop_streak", return_value=6),
        patch.object(pol, "current_cycle_hint", return_value=1600),
    ):
        d = pol.pick(policy)
    assert d["strategy"] == "interesting_product"
    assert "interesting_product" in (d["force_args"] or "")
    assert "open_hop_streak=6" in (d["reason"] or "")


def test_no_interesting_product_when_residual_hot() -> None:
    import scripts.improve_policy as pol

    policy = {
        "active_campaign": "aggressive-change",
        "steady_state": {"max_consecutive_open_hop": 5},
        "campaigns": {
            "aggressive-change": {
                "require_mutation": True,
                "interesting_product_when_green": True,
                "prefer_rotation": [
                    {
                        "force_args": "example-apps story_walk",
                        "lane": "example-apps",
                        "strategy": "story_walk",
                    }
                ],
            }
        },
    }
    with (
        patch.object(pol, "qa_smoke_residual", return_value=(0, None)),
        patch.object(pol, "product_residual_total", return_value=3),
        patch.object(pol, "consecutive_open_hop_streak", return_value=10),
        patch.object(pol, "current_cycle_hint", return_value=1600),
        patch.object(pol, "dual_lock_queue_depth", return_value=0),
        patch.object(pol, "hm_coherence_queue_depth", return_value=0),
        patch.object(pol, "last_strategy_cycle", return_value=100),
        patch.object(pol, "recent_strategy_streak", return_value=0),
    ):
        d = pol.pick(policy)
    assert d["strategy"] != "interesting_product"
