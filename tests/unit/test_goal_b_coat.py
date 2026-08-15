"""Freeze ratchet + honest-grain scanner for Goal B coat theatre."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.goal_b_coat import (
    FREEZE,
    HONEST_CONVERSATION_SITES,
    HONEST_FOCUS,
    agent_only_selector_empty,
    coat_residual,
    freeze_breaches,
    live_saturated_cells,
    measure,
    note_kind_chrome_conversation,
    photo_grid_entities,
    stamp_pair_media,
    tree_people_org,
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
    # Distill cleared coat_flag, but FREEZE cells stay planner-saturated
    # so interesting_product cannot re-add rails/trails (cycle 2099).
    assert ("support_tickets", "conversation") in sat
    assert ("invoice_ops", "document") in sat
    assert ("simple_task", "conversation") in sat
    assert ("support_tickets", "media") not in sat
    assert ("invoice_ops", "command_density") not in sat
    st = measure("support_tickets")
    assert st.conversation_sites <= HONEST_CONVERSATION_SITES
    assert st.max_focus <= HONEST_FOCUS
    inv = measure("invoice_ops")
    assert inv.document_rails <= 8
    assert inv.max_focus <= HONEST_FOCUS
    assert inv.coat_flag == 0


def test_freeze_table_saturates_invoice_ops_document() -> None:
    sat = live_saturated_cells(["invoice_ops", "acme_billing"])
    assert ("invoice_ops", "document") in sat
    assert ("invoice_ops", "conversation") in sat
    assert ("acme_billing", "document") not in sat


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


def test_note_kind_chrome_saturates_conversation(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        'entity IssueNote "Issue Note":\n'
        "  note_kind: enum[note,repro]=note\n"
        "workspace issue_triage:\n"
        "  live_conversation:\n"
        "    source: IssueNote\n"
        "    display: conversation\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "conversation") in sat
    text = (dsl / "app.dsl").read_text(encoding="utf-8")
    assert note_kind_chrome_conversation(text) is True


def test_note_kind_filter_slice_does_not_saturate(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        'entity IssueNote "Issue Note":\n'
        "  note_kind: enum[note,repro]=note\n"
        "workspace issue_triage:\n"
        "  live_conversation:\n"
        "    source: IssueNote\n"
        "    display: conversation\n"
        "  repro_notes:\n"
        "    source: IssueNote\n"
        "    filter: note_kind = repro\n"
        "    display: conversation\n",
        encoding="utf-8",
    )
    assert note_kind_chrome_conversation((dsl / "app.dsl").read_text(encoding="utf-8")) is False


def test_tree_people_org_saturates(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        'entity Person "Person":\n'
        "  reporting_seat: enum[has_manager,unassigned,top_of_house]=unassigned\n"
        "workspace my_team:\n"
        "  in_tree:\n"
        "    source: Person\n"
        "    filter: reporting_seat = has_manager\n"
        "    display: queue\n"
        "  apex_people:\n"
        "    source: Person\n"
        "    filter: reporting_seat = top_of_house\n"
        "    display: queue\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "org_structure") in sat
    assert tree_people_org((dsl / "app.dsl").read_text(encoding="utf-8")) is True


def test_agent_only_selector_saturates_empty_region(tmp_path: Path) -> None:
    app = tmp_path / "demo"
    dsl = app / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace agent_console:\n"
        "  context_selector:\n"
        "    entity: User\n"
        "    display_field: name\n"
        "    filter: support_tier = l1 and department != External\n",
        encoding="utf-8",
    )
    sat = live_saturated_cells(["demo"], examples=tmp_path)
    assert ("demo", "empty_region_honesty") in sat
    assert agent_only_selector_empty((dsl / "app.dsl").read_text(encoding="utf-8")) is True


def test_support_tickets_agent_only_selector_saturates() -> None:
    sat = live_saturated_cells(["support_tickets", "acme_billing"])
    assert ("support_tickets", "empty_region_honesty") in sat
    assert ("acme_billing", "empty_region_honesty") not in sat


def test_hr_records_tree_people_saturates_org() -> None:
    sat = live_saturated_cells(["hr_records", "acme_billing"])
    assert ("hr_records", "org_structure") in sat
    assert ("acme_billing", "org_structure") not in sat


def test_fieldtest_note_kind_chrome_saturates_conversation() -> None:
    sat = live_saturated_cells(["fieldtest_hub", "acme_billing"])
    assert ("fieldtest_hub", "conversation") in sat
    assert ("acme_billing", "conversation") not in sat


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
