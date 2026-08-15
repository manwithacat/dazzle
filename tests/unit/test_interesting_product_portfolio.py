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


def test_ships_from_dig_receipts_structured_fields(tmp_path: Path) -> None:
    """Cycle 2047: dig contract fields depth_id/recipe without notes prose."""
    from scripts.interesting_product_portfolio import ships_from_dig_receipts

    digs = tmp_path / "digs"
    digs.mkdir()
    (digs / "20260814035000-invoice_ops-interesting_product.json").write_text(
        json.dumps(
            {
                "app": "invoice_ops",
                "cycle": 2046,
                "depth_id": "document",
                "recipe": "receipt_settle_rail_evidence",
                "outcome": "PASS",
            }
        ),
        encoding="utf-8",
    )
    ships = ships_from_dig_receipts(digs_dir=digs)
    assert len(ships) == 1
    assert ships[0].app == "invoice_ops"
    assert ships[0].depth_id == "document"
    assert ships[0].recipe == "receipt_settle_rail_evidence"
    assert ships[0].family == "document_rail_slice"


def test_matrix_full_pair_thrash_avoids_locked_icon_cell() -> None:
    """Alternating conversation/document must not re-lock invoice_ops/document."""
    from scripts.interesting_product_portfolio import GoalBShip, recommend_pick

    apps = ["invoice_ops", "support_tickets", "acme_billing", "design_studio"]
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
    }
    recent = [
        GoalBShip("invoice_ops", "document", "receipt_settle_rail_evidence"),
        GoalBShip("support_tickets", "conversation", "priority_awaiting_customer"),
        GoalBShip("invoice_ops", "document", "ach_settle_rail_evidence"),
        GoalBShip("support_tickets", "conversation", "priority_needs_reply"),
        GoalBShip("invoice_ops", "document", "wire_settle_rail_evidence"),
    ]
    rec, _, _, notes = recommend_pick(covered=covered, apps=apps, recent=recent)
    assert any("matrix full" in n or "saturated" in n for n in notes)
    if rec is not None:
        # Thrash / coat-family cells must not win
        assert not (rec["app"] == "invoice_ops" and rec["depth_id"] == "document")
        assert not (rec["app"] == "support_tickets" and rec["depth_id"] == "conversation")


def test_recipe_family_collapses_coat_synonyms() -> None:
    from scripts.interesting_product_portfolio import recipe_family

    assert recipe_family("medium_needs_reply_trail") == "conversation_filter_slice"
    assert recipe_family("thankful_awaiting_customer_trail") == "conversation_filter_slice"
    assert recipe_family("receipt_settle_rail_evidence") == "document_rail_slice"
    assert recipe_family("tax_certificate_watch") == "document_rail_slice"
    assert recipe_family("sla_stage_density") == "stage_queue_slice"
    assert recipe_family("headshot_shelf") == "headshot_shelf"
    assert recipe_family(None, "User.photo_url + media_shelf headshot") == "headshot_shelf"
    assert recipe_family("directory_work_first") == "directory_work_first"
    assert (
        recipe_family(
            "directory_work_first",
            "depth_id=empty_region_honesty recipe=directory_work_first",
        )
        == "directory_work_first"
    )
    assert (
        recipe_family(
            "identity_chip_not_schema",
            "depth_id=empty_region_honesty recipe=identity_chip_not_schema",
        )
        == "identity_chip_not_schema"
    )


def test_coat_family_ship_saturates_cell() -> None:
    from scripts.interesting_product_portfolio import GoalBShip, recommend_pick

    apps = ["support_tickets", "acme_billing"]
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
    }
    recent = [
        GoalBShip(
            "support_tickets",
            "conversation",
            recipe="medium_needs_reply_trail",
            family="conversation_filter_slice",
        )
    ]
    rec, _, _, notes = recommend_pick(covered=covered, apps=apps, recent=recent)
    assert any("saturated" in n for n in notes)
    if rec is not None:
        assert not (rec["app"] == "support_tickets" and rec["depth_id"] == "conversation")


def test_all_icon_cells_saturated_stops() -> None:
    from scripts.interesting_product_portfolio import (
        COAT_FAMILIES,
        ICON_APPS,
        GoalBShip,
        recommend_pick,
    )

    apps = sorted({a for icons in ICON_APPS.values() for a in icons})
    depths = (
        "conversation",
        "document",
        "media",
        "command_density",
        "org_structure",
        "empty_region_honesty",
    )
    covered = {(a, d) for a in apps for d in depths}
    # One coat-family ship on every icon cell → planner must stop.
    fam = next(iter(COAT_FAMILIES))
    recent = [
        GoalBShip(app, depth, recipe=fam, family=fam)
        for depth, icons in ICON_APPS.items()
        for app in icons
    ]
    rec, _, _, notes = recommend_pick(covered=covered, apps=apps, recent=recent)
    assert rec is None
    assert any("stop" in n for n in notes)


def test_live_portfolio_status_runs() -> None:
    """Smoke against the real repo matrix (no assert on recommend identity)."""
    from scripts.interesting_product_portfolio import format_status, snapshot

    text = format_status()
    assert "interesting_product_portfolio" in text
    snap = snapshot()
    assert len(snap.apps) >= 8
    # Digs/.git tip history may be empty in CI — still need a coherent matrix.
    assert len(snap.covered) > 0
    # Full + saturated matrix may recommend None (stop).
    assert snap.recommend is not None or len(snap.missing) == 0 or snap.saturated_cells
