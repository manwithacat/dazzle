"""Entity-card stamps must not omit history when fields are omitted (oral #159)."""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.core.ir.workspaces import (
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections
from dazzle.i18n.display_locale import get_display_locale
from dazzle.render.fragment.region.workspace_card_bodies import clerk_stamp_chrono_fields


def _alert_row() -> dict[str, object]:
    return {
        "id": "a1",
        "message": "CPU spike on api-gateway",
        "severity": "critical",
        "status": "active",
        "triggered_at": datetime(2026, 5, 18, 14, 30, tzinfo=UTC),
        "zzz": "leftover",
    }


def _stamps_cfg(fields: list[str] | None = None) -> EntityCardConfig:
    return EntityCardConfig(
        sections=[
            EntityCardSection(
                name="history",
                mode=EntityCardSectionMode.STAMPS,
                source="Alert",
                fields=list(fields or []),
                limit=5,
            )
        ]
    )


def test_clerk_stamp_chrono_infers_triggered_at_and_message() -> None:
    ts, label, detail = clerk_stamp_chrono_fields([_alert_row()], [])
    assert ts == "triggered_at"
    assert label == "message"
    assert detail == ""


def test_clerk_stamp_chrono_declared_fields_win() -> None:
    ts, label, detail = clerk_stamp_chrono_fields(
        [_alert_row()], ["triggered_at", "message", "severity"]
    )
    assert ts == "triggered_at"
    assert label == "message"
    assert detail == "severity"


def test_clerk_stamp_chrono_leftover_field_stays_put() -> None:
    ts, label, detail = clerk_stamp_chrono_fields([_alert_row()], ["zzz"])
    assert ts == "zzz"
    assert label == ""
    assert detail == ""


def test_clerk_stamp_chrono_skips_leftover_keys_when_inferring() -> None:
    ts, label, _detail = clerk_stamp_chrono_fields([_alert_row()], [])
    assert ts != "zzz"
    assert label != "zzz"


def test_clerk_stamp_chrono_no_when_column_does_not_invent() -> None:
    ts, label, detail = clerk_stamp_chrono_fields(
        [{"id": "a1", "status": "active", "severity": "critical"}],
        [],
    )
    assert ts == ""
    assert label == ""
    assert detail == ""


def test_stamps_omitted_fields_render_history_not_empty() -> None:
    out = _build_entity_card_sections(
        items=[{"id": "a1"}],
        config=_stamps_cfg([]),
        rows_per_section={0: [_alert_row()]},
    )
    assert out[0]["is_omitted"] is False
    body = out[0]["body"]
    assert "CPU spike on api-gateway" in body
    shown = get_display_locale().format_datetime_value(datetime(2026, 5, 18, 14, 30, tzinfo=UTC))
    assert shown in body
    assert "2026-05-18 14:30:00" not in body


def test_stamps_leftover_field_does_not_invent_triggered_at() -> None:
    out = _build_entity_card_sections(
        items=[{"id": "a1"}],
        config=_stamps_cfg(["zzz"]),
        rows_per_section={0: [_alert_row()]},
    )
    body = out[0]["body"]
    assert "CPU spike on api-gateway" not in body
    shown = get_display_locale().format_datetime_value(datetime(2026, 5, 18, 14, 30, tzinfo=UTC))
    assert shown not in body
    assert "leftover" in body
    assert out[0]["is_omitted"] is False


def test_stamps_no_rows_still_omit() -> None:
    out = _build_entity_card_sections(
        items=[{"id": "a1"}],
        config=_stamps_cfg([]),
        rows_per_section={0: []},
    )
    assert out[0]["is_omitted"] is True
    assert out[0]["body"] == ""
