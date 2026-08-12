"""Post-5.8 Goal B media — fieldtest_hub IssueReport photo evidence."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.http.runtime.workspace_columns import _media_col_type_for_field_name
from dazzle.render.cell_chrome import _safe_media_image_url

ROOT = Path(__file__).resolve().parents[2]
ISSUE_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/IssueReport.jsonl"
APP_DSL = ROOT / "examples/fieldtest_hub/dsl/app.dsl"


def test_photo_url_is_image_col_type() -> None:
    assert _media_col_type_for_field_name("photo_url") == "image"


def test_issue_seeds_have_safe_https_photo_urls() -> None:
    rows = [json.loads(line) for line in ISSUE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 5
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 5, "Goal B media expects field photo evidence on open issues"
    for row in with_photo:
        url = str(row["photo_url"])
        assert _safe_media_image_url(url) == url, url
        assert "placehold.co" in url


def test_tester_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1935: Tester Roster/media cards skip Email/Active schema dump."""
    text = APP_DSL.read_text()
    start = text.index('entity Tester "Tester"')
    block = text[start : text.index('entity IssueReport "Issue Report"')]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "name" in line and "location" in line and "skill_level" in line
    assert "email" not in line
    assert "active" not in line


def test_issue_triage_declares_field_evidence_grid() -> None:
    text = APP_DSL.read_text()
    assert "workspace issue_triage" in text
    assert "field_evidence:" in text
    assert "display: grid" in text
    # photo_url typed as url for media chrome
    assert "photo_url: url" in text


def test_pick_display_key_skips_image_columns() -> None:
    """Media thumbs must not become grid card titles (URL-as-title bug)."""
    from dazzle.http.runtime.workspace_region_render import _pick_display_key

    cols = [
        {"key": "device", "type": "ref"},
        {"key": "category", "type": "badge"},
        {"key": "photo_url", "type": "image"},
        {"key": "description", "type": "text"},
        {"key": "status", "type": "badge"},
    ]
    assert _pick_display_key(cols) == "description"
    assert _pick_display_key(cols, preferred="description") == "description"
    # preferred still wins even when not in columns
    assert _pick_display_key(cols[:3], preferred="description") == "description"


def test_field_kit_declares_field_evidence_media_first() -> None:
    """Cycle 1944: road kit puts field photo grid before assignment queues."""
    text = APP_DSL.read_text()
    start = text.index('workspace field_kit "Field Kit":')
    end = text.find("\nworkspace ", start + 1)
    block = text[start:] if end < 0 else text[start:end]
    assert "field_evidence:" in block
    assert "source: IssueReport" in block
    assert "photo_url != null" in block
    assert "display: grid" in block
    assert "reported_by_id = current_user" in block
    assert "evidence: count(IssueReport" in block
    assert block.index("kit_pulse:") < block.index("field_evidence:")
    assert block.index("field_evidence:") < block.index("assigned_devices:")
    assert (
        "focus: kit_pulse, field_evidence, assigned_devices, recent_sessions, my_open_tasks"
        in block
    )
