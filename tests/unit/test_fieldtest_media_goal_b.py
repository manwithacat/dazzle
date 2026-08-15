"""Post-5.8 Goal B media — fieldtest_hub IssueReport photo evidence."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.http.runtime.workspace_columns import _media_col_type_for_field_name
from dazzle.render.cell_chrome import _safe_media_image_url

ROOT = Path(__file__).resolve().parents[2]
ISSUE_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/IssueReport.jsonl"
DEVICE_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/Device.jsonl"
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


def _issue_triage_block() -> str:
    text = APP_DSL.read_text()
    start = text.index('workspace issue_triage "Issue Triage":')
    end = text.find("\nworkspace ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_issue_triage_declares_severity_evidence_density() -> None:
    """Cycle 2059: dual critical vs high photo grids (not one mixed evidence dump)."""
    block = _issue_triage_block()
    assert "critical_evidence:" in block
    assert "high_evidence:" in block
    assert "severity = critical and photo_url != null" in block
    assert "severity = high and photo_url != null" in block
    assert "display: grid" in block
    assert "critical_photos: count(IssueReport" in block
    assert "high_photos: count(IssueReport" in block
    assert block.index("open_pressure:") < block.index("critical_evidence:")
    assert block.index("critical_evidence:") < block.index("high_evidence:")
    assert block.index("high_evidence:") < block.index("live_conversation:")
    assert "focus: open_pressure, repro_notes, critical_evidence, high_evidence" in block
    assert "severity_evidence_density" in block.lower() or "critical vs high" in block.lower()
    # Mixed field_evidence remains under fold (not focus twin of dual shelves)
    assert "field_evidence:" in block
    assert "field_evidence" not in block.split("focus:")[1].split("\n")[0]
    # photo_url typed as url for media chrome
    assert "photo_url: url" in APP_DSL.read_text()


def test_issue_seeds_span_critical_and_high_photos() -> None:
    rows = [json.loads(line) for line in ISSUE_SEEDS.read_text().splitlines() if line.strip()]
    crit = [r for r in rows if r.get("severity") == "critical" and r.get("photo_url")]
    high = [r for r in rows if r.get("severity") == "high" and r.get("photo_url")]
    assert len(crit) >= 2
    assert len(high) >= 1


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


def _device_fleet_block() -> str:
    text = APP_DSL.read_text()
    start = text.index('workspace device_fleet "Device Fleet":')
    end = text.find("\nworkspace ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_device_entity_declares_unit_photo_url() -> None:
    """Cycle 2080: Device.photo_url is hardware identity, not defect evidence."""
    text = APP_DSL.read_text()
    start = text.index('entity Device "Device"')
    block = text[start : text.index('entity Tester "Tester"')]
    assert "photo_url: url" in block
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "photo_url" in line
    assert "serial_number" in line


def test_device_fleet_declares_hardware_identity_wall() -> None:
    """Cycle 2080: unit photos first on fleet — not another IssueReport filter."""
    block = _device_fleet_block()
    assert "hardware_identity:" in block
    assert "source: Device" in block
    assert "photo_url != null" in block
    assert "display: grid" in block
    assert "identified: count(Device where photo_url != null)" in block
    assert block.index("fleet_metrics:") < block.index("hardware_identity:")
    assert block.index("hardware_identity:") < block.index("by_status:")
    assert block.index("by_status:") < block.index("by_model:")
    assert "focus: fleet_metrics, hardware_identity, by_status, by_model" in block
    assert "device_identity_wall" in block.lower() or "hardware identity" in block.lower()
    assert "media_shelf:" not in block
    # Org boards remain; capacity queues stay under the fold.
    assert "unassigned_devices:" in block
    assert "active_devices:" in block
    # Surfaces expose the unit photo (list/detail/create/edit).
    text = APP_DSL.read_text()
    assert 'field photo_url "Unit Photo"' in text


def test_device_seeds_have_safe_https_unit_photos() -> None:
    rows = [json.loads(line) for line in DEVICE_SEEDS.read_text().splitlines() if line.strip()]
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 12, "Goal B media expects bench photos on fleet units"
    models = {str(r.get("model") or "") for r in with_photo}
    assert len(models) >= 4
    for row in with_photo:
        url = str(row["photo_url"])
        assert _safe_media_image_url(url) == url, url
        assert "placehold.co" in url
