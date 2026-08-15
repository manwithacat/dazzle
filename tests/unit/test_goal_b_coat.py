"""Freeze ratchet + honest-grain scanner for Goal B coat theatre."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.goal_b_coat import (
    FREEZE,
    HONEST_CONVERSATION_SITES,
    HONEST_FOCUS,
    coat_residual,
    freeze_breaches,
    live_saturated_cells,
    measure,
    photo_grid_entities,
    stamp_pair_media,
)

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"


def test_support_tickets_conversation_freeze() -> None:
    m = measure("support_tickets")
    caps = FREEZE["support_tickets"]
    assert m.conversation_sites <= caps["conversation_sites"]
    assert m.conversation_names <= caps["conversation_names"]
    assert m.max_focus <= caps["max_focus"]
    assert m.metric_keys <= caps["metric_keys"]


def test_simple_task_conversation_freeze() -> None:
    m = measure("simple_task")
    caps = FREEZE["simple_task"]
    assert m.conversation_sites <= caps["conversation_sites"]
    assert m.conversation_names <= caps["conversation_names"]
    assert m.max_focus <= caps["max_focus"]
    assert m.metric_keys <= caps["metric_keys"]
    assert m.conv_siblings <= 2
    assert m.coat_flag == 0


def test_invoice_ops_document_freeze() -> None:
    m = measure("invoice_ops")
    caps = FREEZE["invoice_ops"]
    assert m.document_rails <= caps["document_rails"]
    assert m.max_focus <= caps["max_focus"]
    assert m.metric_keys <= caps["metric_keys"]
    assert m.conversation_sites <= caps["conversation_sites"]


def test_freeze_breaches_empty_at_current_counts() -> None:
    assert freeze_breaches() == []


def test_honest_grain_saturates_icon_coats() -> None:
    apps = ["support_tickets", "invoice_ops", "simple_task", "acme_billing"]
    sat = live_saturated_cells(apps)
    # Cycle 2077 distilled support_tickets; 2079 distilled invoice_ops rails.
    assert ("support_tickets", "conversation") not in sat
    assert ("invoice_ops", "document") not in sat
    assert ("support_tickets", "media") not in sat
    assert ("invoice_ops", "command_density") not in sat
    st = measure("support_tickets")
    assert st.conversation_sites <= HONEST_CONVERSATION_SITES
    assert st.max_focus <= HONEST_FOCUS
    inv = measure("invoice_ops")
    assert inv.document_rails <= 8
    assert inv.max_focus <= HONEST_FOCUS


def test_support_tickets_signature_is_siblings_and_cartesian() -> None:
    m = measure("support_tickets")
    assert m.conv_siblings <= 2
    assert m.slice_cartesian == 0
    assert m.coat_flag == 0
    n, nxt = coat_residual()
    assert n == 0
    assert nxt is None


def test_invoice_ops_flagged_on_rails_and_focus() -> None:
    m = measure("invoice_ops")
    assert m.document_rails <= 8
    assert m.max_focus <= 12
    assert m.coat_flag == 0


def test_acme_billing_not_flagged_as_conversation_coat() -> None:
    m = measure("acme_billing")
    assert m.conv_siblings <= 2
    assert m.slice_cartesian == 0
    assert m.coat_flag == 0


def test_two_entity_photo_grids_saturate_media(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace fleet:\n"
        "  hardware:\n"
        "    source: Device\n"
        "    filter: photo_url != null\n"
        "    display: grid\n"
        "workspace triage:\n"
        "  evidence:\n"
        "    source: IssueReport\n"
        "    filter: photo_url != null\n"
        "    display: grid\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "media") in sat
    text = (dsl / "app.dsl").read_text(encoding="utf-8")
    assert photo_grid_entities(text) == {"Device", "IssueReport"}


def test_single_photo_entity_does_not_saturate_media(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace fleet:\n"
        "  hardware:\n"
        "    source: Device\n"
        "    filter: photo_url != null\n"
        "    display: grid\n"
        "  also_devices:\n"
        "    source: Device\n"
        "    filter: status = active and photo_url != null\n"
        "    display: grid\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "media") not in sat


def test_fieldtest_two_desk_media_saturates() -> None:
    sat = live_saturated_cells(["fieldtest_hub", "support_tickets"])
    assert ("fieldtest_hub", "media") in sat
    assert ("support_tickets", "media") not in sat


def test_stamp_pair_grids_saturate_media(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace review_desk:\n"
        "  review_pixels:\n"
        "    source: Asset\n"
        "    filter: status = review\n"
        "    display: grid\n"
        "  approved_pixels:\n"
        "    source: Asset\n"
        "    filter: status = approved\n"
        "    display: grid\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "media") in sat
    text = (dsl / "app.dsl").read_text(encoding="utf-8")
    assert stamp_pair_media(text) is True


def test_design_studio_stamp_pair_media_saturates() -> None:
    sat = live_saturated_cells(["design_studio", "support_tickets"])
    assert ("design_studio", "media") in sat
    assert ("support_tickets", "media") not in sat


def test_freeze_detects_growth(tmp_path: Path) -> None:
    app = tmp_path / "support_tickets"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace ticket_queue:\n"
        "  ux:\n"
        "    as agent:\n"
        "      focus: a, b, c\n"
        "  live:\n"
        "    display: conversation\n",
        encoding="utf-8",
    )
    # Tiny desk is under freeze; bump a synthetic cap to 0 to prove the compare.
    breaches = freeze_breaches(
        examples=tmp_path,
        freeze={"support_tickets": {"conversation_sites": 0, "max_focus": 10}},
    )
    assert any("conversation_sites" in b for b in breaches)
