"""Post-5.8 Goal B document — fieldtest_hub brief/protocol composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/fieldtest_hub/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/TestDocument.jsonl"


def _engineering_dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace engineering_dashboard "Engineering Dashboard":')
    end = text.index('workspace tester_dashboard "Tester Dashboard":', start)
    return text[start:end]


def _manager_ops_block() -> str:
    text = APP.read_text()
    start = text.index('workspace manager_ops "Manager Ops":')
    end = text.index("workspace issue_triage", start)
    return text[start:end]


def test_test_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity TestDocument "Test Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert (
        "doc_kind: enum[brief, protocol, acceptance_criteria, field_plan, decision]=brief" in text
    )
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_manager_ops_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Manager Ops before triage notes trail."""
    block = _manager_ops_block()
    assert "composition:" in block
    assert "source: TestDocument" in block
    assert "documents: count(TestDocument)" in block
    assert "action: test_document_detail" in block
    # Order: dual attention → documents → conversation
    assert block.index("device_attention:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: quality_strip, critical_issues, device_attention, composition, "
        "live_conversation" in block
    )


def test_engineering_dashboard_declares_composition_after_dual_attention() -> None:
    block = _engineering_dashboard_block()
    assert "composition:" in block
    assert "source: TestDocument" in block
    assert "documents: count(TestDocument)" in block
    assert block.index("triage_pressure:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")


def test_engineering_dashboard_exclusive_protocol_vs_acceptance() -> None:
    """Cycle 2088 document: recipe protocol_acceptance_split.

    Peer TestRail/qTest: run protocols vs ship-gate acceptance as exclusive
    queues — mixed composition stays below fold (not another brief dump).
    """
    block = _engineering_dashboard_block()
    assert "protocols:" in block
    assert "filter: doc_kind = protocol and status != archived" in block
    assert "acceptance_packets:" in block
    assert "filter: doc_kind = acceptance_criteria and status != archived" in block
    assert block.index("protocols:") < block.index("acceptance_packets:")
    assert block.index("acceptance_packets:") < block.index("device_attention:")
    assert "focus: fleet_overview, protocols, acceptance_packets, live_conversation" in block
    assert "limit: 4" in block  # device_attention capped so docs stay above fold


def test_test_document_list_dual_open_and_device_hub() -> None:
    text = APP.read_text()
    assert 'surface test_document_list "Test Documents"' in text
    assert "open: TestDocument via id | Device via device" in text
    assert 'surface test_document_detail "Test Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: TestDocument" in text


def test_test_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across devices"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["device"]).startswith("d1000000-")
        assert str(row["id"]).startswith("7f000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"brief", "protocol", "acceptance_criteria", "field_plan", "decision"}
    assert statuses >= {"draft", "published"}
