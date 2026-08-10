"""Post-5.8 Goal B empty_region_honesty — contact_manager Home / Contacts / Companies."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_home_omits_company_chart_theater() -> None:
    """Peer CRM home: notes + letters, not company bar chart / twin dumps."""
    block = _workspace_block("home")
    assert "live_conversation:" in block
    assert "composition:" in block
    assert "practice_context:" in block
    assert "company_mix:" not in block
    assert "company_contacts:" not in block
    assert "bar_chart" not in block
    assert (
        "focus: media_shelf, directory_stats, engagement_docs, favourite_contacts, composition, "
        "live_conversation, practice_context" in block
    )


def test_contacts_drops_favorite_kanban_theater() -> None:
    block = _workspace_block("contacts")
    assert "favourites_queue:" in block
    assert "contact_list:" in block
    assert "favorite_board:" not in block
    assert "display: kanban" not in block
    # Goal B media (cycle 1882): headshot shelf first, then favourites + dual-pane
    assert "focus: media_shelf, favourites_queue, contact_list, contact_detail" in block


def test_companies_drops_empty_bar_chart() -> None:
    """Companies stays org-first (title board + company queue) without bar theater."""
    block = _workspace_block("companies")
    assert "company_pulse:" in block
    assert "by_title:" in block
    assert "by_company:" in block
    assert "company_context:" in block
    assert "company_chart:" not in block
    assert "bar_chart" not in block
    # Goal B org_structure: role board before company placement before recents
    assert "focus: company_pulse, by_title, by_company, recent_people" in block
