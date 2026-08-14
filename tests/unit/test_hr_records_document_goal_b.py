"""Post-5.8 Goal B document — hr_records employment letter composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/hr_records/demo_data/HrDocument.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_hr_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity HrDocument "HR Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert "doc_kind: enum[offer, policy, promo, contract, onboarding]=offer" in text
    assert "status: enum[draft, issued, signed, archived]=draft" in text
    assert "draft -> issued:" in text
    assert "issued -> signed:" in text
    assert "signed -> archived:" in text


def test_hero_desks_declare_composition_queue() -> None:
    """Goal B document: composition on staff_directory + my_team (not only list)."""
    text = APP.read_text()
    assert "workspace staff_directory" in text
    assert "workspace my_team" in text
    assert "composition:" in text
    assert "source: HrDocument" in text
    assert "documents: count(HrDocument)" in text
    assert 'related documents "Documents"' in text
    assert "show: HrDocument" in text

    staff = _workspace_block("staff_directory")
    assert "composition:" in staff
    assert "source: HrDocument" in staff
    assert "documents: count(HrDocument)" in staff
    assert staff.index("recent_starters:") < staff.index("composition:")
    assert staff.index("composition:") < staff.index("live_conversation:")
    # Cycle 1950: composition stays on desk after dual attention; not all focus-eager.
    assert "focus: media_shelf, headcount, current_staff, recent_starters" in staff

    team = _workspace_block("my_team")
    assert "composition:" in team
    assert "source: HrDocument" in team
    assert "documents: count(HrDocument)" in team
    assert team.index("\n  reporting_lines:") < team.index("composition:")
    assert team.index("composition:") < team.index("live_conversation:")
    assert "focus: career_pulse, ic_track, manager_track, by_department" in team


def test_hr_document_list_dual_open_declared() -> None:
    text = APP.read_text()
    assert 'surface hr_document_list "HR Documents"' in text
    assert "open: HrDocument via id | Person via person" in text
    assert 'surface hr_document_detail "HR Document"' in text


def test_hr_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across people"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["person"])
        assert str(row["id"]).startswith("c2000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"offer", "policy", "promo", "contract", "onboarding"}
    assert statuses >= {"draft", "issued", "signed"}
