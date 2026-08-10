"""Goal B portfolio planner — anti-wave, anti-recipe, stacking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def test_covered_from_unit_pins_parses_goal_b_names(tmp_path: Path) -> None:
    from scripts.interesting_product_portfolio import covered_from_unit_pins

    unit = tmp_path / "unit"
    unit.mkdir()
    (unit / "test_simple_task_media_goal_b.py").write_text("# pin\n", encoding="utf-8")
    (unit / "test_hr_records_empty_region_goal_b.py").write_text("# pin\n", encoding="utf-8")
    (unit / "test_llm_classifier_document_goal_b.py").write_text("# pin\n", encoding="utf-8")
    (unit / "test_media_thumb_goal_b.py").write_text("# framework\n", encoding="utf-8")
    covered = covered_from_unit_pins(unit_dir=unit)
    assert ("simple_task", "media") in covered
    assert ("hr_records", "empty_region_honesty") in covered
    assert ("llm_ticket_classifier", "document") in covered
    assert not any(a == "media_thumb" for a, _ in covered)


def test_depth_wave_bans_and_recommends_novel_media_fill(tmp_path: Path) -> None:
    from scripts.interesting_product_portfolio import (
        GoalBShip,
        recommend_pick,
    )

    apps = ["acme_billing", "design_studio", "ops_dashboard"]
    # Full except acme media
    covered = {
        (a, d)
        for a in apps
        for d in (
            "conversation",
            "document",
            "media",
            "command_density",
            "org_structure",
            "empty_region_honesty",
        )
        if not (a == "acme_billing" and d == "media")
    }
    recent = [
        GoalBShip("simple_task", "media", "headshot_shelf"),
        GoalBShip("invoice_ops", "media", "headshot_shelf"),
        GoalBShip("project_tracker", "media", "headshot_shelf"),
    ]
    rec, banned_d, banned_r, notes = recommend_pick(
        covered=covered,
        apps=apps,
        recent=recent,
        max_same_depth=3,
        max_same_recipe=3,
    )
    assert "media" in banned_d
    assert "headshot_shelf" in banned_r
    assert rec is not None
    assert rec["depth_id"] == "media"
    assert rec["app"] == "acme_billing"
    assert rec.get("must_novel_recipe") is True
    assert any("novel" in n or "banned-depth" in n for n in notes)


def test_anti_wave_prefers_other_depth_when_available() -> None:
    from scripts.interesting_product_portfolio import GoalBShip, recommend_pick

    apps = ["support_tickets", "invoice_ops"]
    covered = {("support_tickets", "media"), ("invoice_ops", "media")}
    recent = [
        GoalBShip("a", "media", "headshot_shelf"),
        GoalBShip("b", "media", "headshot_shelf"),
        GoalBShip("c", "media", "headshot_shelf"),
    ]
    rec, banned_d, _, _ = recommend_pick(
        covered=covered, apps=apps, recent=recent, max_same_depth=3
    )
    assert "media" in banned_d
    assert rec is not None
    assert rec["depth_id"] != "media"


def test_ships_from_dig_receipts(tmp_path: Path) -> None:
    from scripts.interesting_product_portfolio import ships_from_dig_receipts

    digs = tmp_path / "digs"
    digs.mkdir()
    (digs / "20260810174012-simple_task-interesting_product.json").write_text(
        json.dumps(
            {
                "app": "simple_task",
                "cycle": 1884,
                "notes": "depth_id=media User.photo_url + media_shelf headshot",
            }
        ),
        encoding="utf-8",
    )
    ships = ships_from_dig_receipts(digs_dir=digs)
    assert len(ships) == 1
    assert ships[0].app == "simple_task"
    assert ships[0].depth_id == "media"
    assert ships[0].recipe == "headshot_shelf"


def test_live_portfolio_status_runs() -> None:
    """Smoke against the real repo matrix (no assert on recommend identity)."""
    from scripts.interesting_product_portfolio import format_status, snapshot

    text = format_status()
    assert "interesting_product_portfolio" in text
    snap = snapshot()
    assert len(snap.apps) >= 8
    assert snap.depth_streak >= 1
    # Current tip wave is media headshots — ban should fire.
    assert snap.depth_streak_id == "media" or snap.recommend is not None
