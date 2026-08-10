"""Post-5.8 Goal B document — domain_join_co brief/handbook composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"
DOC_SEEDS = ROOT / "examples/domain_join_co/dsl/seeds/demo_data/WorkspaceDocument.jsonl"


def _workspace_block(name: str) -> str:
    text = DOMAIN.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_workspace_document_entity_is_document_composition() -> None:
    text = DOMAIN.read_text()
    assert 'entity WorkspaceDocument "Workspace Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert "doc_kind: enum[brief, onboarding_guide, join_playbook, policy, decision]=brief" in text
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_home_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Home before discussion trail."""
    block = _workspace_block("home")
    assert "composition:" in block
    assert "source: WorkspaceDocument" in block
    assert "documents: count(WorkspaceDocument)" in block
    assert "action: workspace_document_detail" in block
    # Order: dual attention → documents → conversation
    assert block.index("join_readiness:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: handbook_covers, team_pulse, announcement_queue, join_readiness, "
        "composition, live_conversation" in block
    )


def test_announce_declares_composition_after_dual_attention() -> None:
    block = _workspace_block("announce")
    assert "composition:" in block
    assert "source: WorkspaceDocument" in block
    assert "documents: count(WorkspaceDocument)" in block
    assert block.index("join_context:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: handbook_covers, board_pulse, feed_queue, join_context, "
        "composition, live_conversation" in block
    )


def test_workspace_document_list_dual_open_and_workspace_hub() -> None:
    text = DOMAIN.read_text()
    assert 'surface workspace_document_list "Workspace Documents"' in text
    assert "open: WorkspaceDocument via id | Workspace via workspace" in text
    assert 'surface workspace_document_detail "Workspace Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: WorkspaceDocument" in text


def test_workspace_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across workspaces"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["workspace"]).startswith("d1000000-")
        assert str(row["id"]).startswith("d4000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"brief", "onboarding_guide", "join_playbook", "policy", "decision"}
    assert statuses >= {"draft", "published"}
