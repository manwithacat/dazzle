"""Audit-history must not dump ISO clocks / snake_case schema (oral #179)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.audit_history import HistoryChange, HistoryEntry
from dazzle.http.runtime.audit_region import _render_history_html
from dazzle.render.audit_history_cell import (
    clerk_audit_field_label,
    clerk_audit_op_display,
    clerk_audit_value_display,
    clerk_audit_when_attr,
    clerk_audit_when_display,
)

_WHEN = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
_ISO_BLOB = "2026-05-18 14:30:00+00:00"


def _invoice_dunning_field():
    spec = load_project(Path("examples/acme_billing"))
    invoice = spec.get_entity("Invoice")
    assert invoice is not None
    dunning = next(f for f in invoice.fields if f.name == "dunning_state")
    return spec, invoice, dunning


def test_acme_invoice_audit_history_is_live() -> None:
    spec, invoice, dunning = _invoice_dunning_field()
    del spec
    block = Path("examples/acme_billing/dsl/entities.dsl").read_text()
    assert "audit: all" in block
    assert invoice.name == "Invoice"
    surfaces = Path("examples/acme_billing/dsl/surfaces.dsl").read_text()
    hub = surfaces.split('surface invoice_detail "Invoice"', 1)[1].split("surface ", 1)[0]
    assert "show_history: true" in hub
    assert dunning.name == "dunning_state"


def test_clerk_audit_split_leftover_and_empty() -> None:
    assert clerk_audit_op_display("update") == "Update"
    assert clerk_audit_op_display("zzz") == "zzz"
    assert clerk_audit_op_display("ghost") == "ghost"
    assert clerk_audit_field_label("dunning_state") == "Dunning State"
    assert clerk_audit_field_label("zzz") == "zzz"
    assert clerk_audit_value_display(True) == "Yes"
    assert clerk_audit_value_display(False) == "No"
    assert clerk_audit_value_display("reminder_1") == "Reminder 1"
    assert clerk_audit_value_display("zzz") == "zzz"
    assert clerk_audit_value_display("1e2") == "1e2"
    assert clerk_audit_value_display("") == ""
    assert clerk_audit_value_display(None) == ""
    assert clerk_audit_value_display("Paid in full") == "Paid in full"
    shown = clerk_audit_when_display(_WHEN)
    assert shown
    assert _ISO_BLOB not in shown
    assert "2026-05-18 14:30:00" not in shown
    assert clerk_audit_when_display("zzz") == "zzz"
    assert clerk_audit_when_attr("zzz") == ""
    assert clerk_audit_when_attr(_WHEN).startswith("2026-05-18")


def test_history_html_does_not_dump_iso_or_schema_keys() -> None:
    change = HistoryChange(
        at=_WHEN,
        entity_type="Invoice",
        entity_id="inv-1",
        operation="update",
        by_user_id="user-1",
        fields=[
            HistoryEntry(
                at=_WHEN,
                entity_type="Invoice",
                entity_id="inv-1",
                field_name="dunning_state",
                operation="update",
                before="none",
                after="reminder_1",
                decoded_before="none",
                decoded_after="reminder_1",
                by_user_id="user-1",
            ),
            HistoryEntry(
                at=_WHEN,
                entity_type="Invoice",
                entity_id="inv-1",
                field_name="sensitive",
                operation="update",
                before="false",
                after="true",
                decoded_before=False,
                decoded_after=True,
                by_user_id="user-1",
            ),
        ],
    )
    html = _render_history_html([change])
    assert "Dunning State" in html
    assert "dunning_state" not in html
    assert ">Update<" in html
    assert ">update<" not in html
    assert "Reminder 1" in html
    assert "reminder_1" not in html
    assert ">Yes<" in html
    assert ">True<" not in html
    assert _ISO_BLOB not in html
    assert "datetime=" in html
    leftover = _render_history_html(
        [
            HistoryChange(
                at="zzz",
                entity_type="Invoice",
                entity_id="inv-1",
                operation="zzz",
                by_user_id="user-1",
                fields=[
                    HistoryEntry(
                        at="zzz",
                        entity_type="Invoice",
                        entity_id="inv-1",
                        field_name="zzz",
                        operation="zzz",
                        before="zzz",
                        after="ghost",
                        decoded_before="zzz",
                        decoded_after="ghost",
                        by_user_id="user-1",
                    )
                ],
            )
        ]
    )
    assert "zzz" in leftover
    assert "ghost" in leftover
    assert "Dunning State" not in leftover


def test_empty_history_does_not_invent_rows() -> None:
    html = _render_history_html([])
    assert "No history yet." in html
    assert "dz-audit-history__change" not in html
    html2 = _render_history_html(
        [
            HistoryChange(
                at=None,
                entity_type="Invoice",
                entity_id="inv-1",
                operation="create",
                by_user_id=None,
                fields=[],
            )
        ]
    )
    assert "Create" in html2
    assert "dz-audit-history__at" not in html2
