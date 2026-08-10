"""Post-5.8 Goal B media — ops_dashboard runbook cover wall (novel vs headshot)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/ops_dashboard/dsl/seeds/demo_data/OpsDocument.jsonl"


def _workspace_block(name: str, end_marker: str) -> str:
    text = APP.read_text()
    start = text.index(f'workspace {name} "')
    end = text.index(end_marker, start + 1)
    return text[start:end]


def test_ops_document_declares_preview_url() -> None:
    text = APP.read_text()
    block = text.split('entity OpsDocument "Ops Document"')[1].split("entity ")[0]
    assert "preview_url: url" in block
    assert "photo_url" not in block
    assert "preview_url" in block.split("fitness:")[1]


def test_command_center_runbook_covers_first() -> None:
    """Novel media: runbook document thumbs win fold — not people headshots."""
    block = _workspace_block(
        "command_center",
        'workspace incident_review "Incident Review":',
    )
    assert "runbook_covers:" in block
    assert "source: OpsDocument" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert "photo_url" not in block
    assert block.index("runbook_covers:") < block.index("health_summary:")
    assert (
        "focus: runbook_covers, health_summary, systems_attention, active_alerts, "
        "composition, live_conversation" in block
    )


def test_incident_review_runbook_covers_first() -> None:
    block = _workspace_block(
        "incident_review",
        'workspace systems_desk "Systems":',
    )
    assert "runbook_covers:" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert block.index("runbook_covers:") < block.index("alert_summary:")
    assert (
        "focus: runbook_covers, alert_summary, live_conversation, recent_alerts, "
        "system_overview, review_checklist" in block
    )


def test_ops_document_seeds_have_preview_urls() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    with_preview = [r for r in rows if r.get("preview_url")]
    assert len(with_preview) >= 10, "Goal B media expects cover previews on runbooks"
    assert all("placehold.co" in r["preview_url"] for r in with_preview)
