"""Post-5.8 Goal B media — hr_records staff headshot shelf (cycle 1879)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"
PERSON_SEEDS = ROOT / "examples/hr_records/dsl/seeds/demo_data/Person.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_person_entity_declares_photo_url() -> None:
    text = APP.read_text()
    assert 'entity Person "Person"' in text
    assert "photo_url: url" in text


def test_person_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1935: staff media/people cards skip Email schema dump."""
    text = APP.read_text()
    start = text.index('entity Person "Person":')
    block = text[start : text.index('entity PersonNote "Person Note":')]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "legal_name" in line and "preferred_name" in line
    assert "work_location" in line and "started_at" in line
    assert "email" not in line
    assert "photo_url" not in line


def test_staff_directory_media_shelf_first() -> None:
    block = _workspace_block("staff_directory")
    assert "media_shelf:" in block
    assert "source: Person" in block
    assert "display: grid" in block
    assert block.index("media_shelf:") < block.index("headcount:")
    assert block.index("media_shelf:") < block.index("current_staff:")
    assert (
        "focus: media_shelf, headcount, current_staff, recent_starters, "
        "composition, live_conversation" in block
    )


def test_person_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in PERSON_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 8
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
