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
        patch.object(pol, "coat_residual_total", return_value=(0, None)),
        patch.object(pol, "consecutive_open_hop_streak", return_value=6),
        patch.object(pol, "current_cycle_hint", return_value=1600),
    ):
        d = pol.pick(policy)
    assert "open_hop_streak=6" in (d["reason"] or "")
    # Saturated live matrix yields framework-ux + require_mutation=0.
    if d.get("interesting_product_saturated"):
        assert d["strategy"] == "framework-ux"
        assert d.get("require_mutation") is False
    else:
        assert d["strategy"] == "interesting_product"
        assert "interesting_product" in (d["force_args"] or "")


def test_coat_residual_forces_distill_over_goal_b() -> None:
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
                        "force_args": "example-apps interesting_product",
                        "lane": "example-apps",
                        "strategy": "interesting_product",
                    }
                ],
            }
        },
    }
    with (
        patch.object(pol, "qa_smoke_residual", return_value=(0, None)),
        patch.object(pol, "product_residual_total", return_value=0),
        patch.object(pol, "coat_residual_total", return_value=(2, "support_tickets")),
        patch.object(pol, "consecutive_open_hop_streak", return_value=6),
        patch.object(pol, "current_cycle_hint", return_value=1600),
    ):
        d = pol.pick(policy)
    assert d["strategy"] == "distill"
    assert d["force_args"] == "example-apps distill support_tickets"
    assert d.get("require_mutation") is True
    assert "coat_residual=2" in (d["reason"] or "")


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


# --- W3: the smoke campaign rotates on findings, not on stamp age --------------
# `land-l25-smoke` exists to find gross bugs. It was selected by
# `smoke_residual=9` where all nine were *stale measurement stamps* — so the
# campaign re-measured already-clean apps and reported nine units of residual
# without having observed a single finding.


def test_stale_stamps_alone_do_not_arm_the_smoke_campaign() -> None:
    """The live state right now: seven stale stamps, zero findings."""
    import scripts.improve_policy as pol

    findings, nxt = pol.qa_smoke_residual()

    assert findings == 0, (
        "a smoke report is carrying product work (auto_seed or a dead crawl) — this "
        "test's premise changed; update it rather than loosening the assertion"
    )
    assert nxt is None


def test_a_seeded_smoke_finding_arms_the_campaign(tmp_path: Path) -> None:
    """And the other direction: a real finding must still rotate the campaign, or
    the fix above would have blinded the loop rather than sharpened it."""
    import json

    import scripts.improve_policy as pol

    # A synthetic report, newest in the tree, in an example that already has one.
    app = REPO / "examples" / "invoice_ops" / "dev_docs"
    assert app.is_dir(), "example layout changed — pick another app"
    probe = app / "qa-smoke-manager-29991231-235959.json"
    probe.write_text(json.dumps({"auto_seed": [{"id": "synthetic-probe"}]}), encoding="utf-8")
    try:
        findings, nxt = pol.qa_smoke_residual()
    finally:
        probe.unlink()

    assert findings >= 1
    assert nxt == "invoice_ops"
