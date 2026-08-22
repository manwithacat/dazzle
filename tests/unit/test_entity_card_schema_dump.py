"""Entity-card halo/flags must not dump schema keys or raw storage (oral #157)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dazzle.core.ir.workspaces import (
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections
from dazzle.i18n.display_locale import get_display_locale
from dazzle.render.filters import (
    clerk_entity_card_field_display,
    clerk_entity_card_field_label,
)
from dazzle.render.fragment.format_cell import format_cell


def _halo(fields: list[str]) -> EntityCardConfig:
    return EntityCardConfig(
        sections=[
            EntityCardSection(
                name="halo",
                mode=EntityCardSectionMode.HALO,
                fields=fields,
            )
        ]
    )


def test_ops_dashboard_alert_360_halo_flags_are_schema_fields() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    found = False
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name != "alert_360":
                continue
            found = True
            cfg = region.entity_card_config
            assert cfg is not None
            names = [s.name for s in (cfg.sections or [])]
            assert "halo" in names
            assert "meta" in names
            halo = next(s for s in cfg.sections if s.name == "halo")
            flags = next(s for s in cfg.sections if s.name == "meta")
            assert "severity" in list(halo.fields or [])
            assert "status" in list(flags.fields or [])
    assert found


def test_entity_card_field_label_humanizes_schema_key() -> None:
    assert clerk_entity_card_field_label("acknowledged_by") == "Acknowledged By"
    assert clerk_entity_card_field_label("severity") == "Severity"
    assert clerk_entity_card_field_label("zzz") == "zzz"


def test_entity_card_field_display_enum_not_schema_token() -> None:
    assert clerk_entity_card_field_display("critical", "severity") == "Critical"
    assert clerk_entity_card_field_display("active", "status") == "Active"
    assert clerk_entity_card_field_display("in_progress", "status") == "In Progress"


def test_entity_card_field_display_leftover_stays_put() -> None:
    assert clerk_entity_card_field_display("zzz", "severity") == "zzz"
    assert clerk_entity_card_field_display("2abc", "status") == "2abc"
    assert clerk_entity_card_field_label("ghost") == "ghost"


def test_entity_card_field_display_free_text_not_title_cased() -> None:
    msg = "CPU spike on api-gateway"
    assert clerk_entity_card_field_display(msg, "message") == msg


def test_entity_card_field_display_datetime_not_iso() -> None:
    triggered = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    shown = clerk_entity_card_field_display(triggered, "triggered_at")
    assert shown == format_cell(triggered, "datetime")
    assert "2026-05-18 14:30:00" not in shown
    assert shown == get_display_locale().format_datetime_value(triggered)


def test_halo_html_uses_clerk_labels_and_values() -> None:
    out = _build_entity_card_sections(
        items=[
            {
                "id": "a1",
                "message": "CPU spike on api-gateway",
                "severity": "critical",
                "status": "active",
                "acknowledged_by": "zzz",
                "triggered_at": datetime(2026, 5, 18, 14, 30, tzinfo=UTC),
            }
        ],
        config=_halo(["message", "severity", "status", "acknowledged_by", "triggered_at"]),
    )
    body = out[0]["body"]
    assert "<dt>Severity</dt>" in body
    assert "<dd>Critical</dd>" in body
    assert "<dt>Status</dt>" in body
    assert "<dd>Active</dd>" in body
    assert "<dt>Acknowledged By</dt>" in body
    assert "<dd>zzz</dd>" in body
    assert "<dt>severity</dt>" not in body
    assert "<dd>critical</dd>" not in body
    assert "<dd>active</dd>" not in body
    assert "2026-05-18 14:30:00" not in body
    assert "CPU spike on api-gateway" in body
