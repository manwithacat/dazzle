"""Related queue must title the walk, not the attempt number (oral #140)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.workspace_columns import build_entity_columns
from dazzle.http.runtime.workspace_region_render import (
    _entity_text_identity_key,
    _pick_display_key,
    _set_display_key,
)
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.cell_chrome import is_sequence_title_key, related_queue_title_and_meta
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer


def test_sequence_title_keys() -> None:
    assert is_sequence_title_key("attempt_number")
    assert is_sequence_title_key("Attempt")
    assert is_sequence_title_key("quantity")
    assert not is_sequence_title_key("failure_reason")
    assert not is_sequence_title_key("ticket_number")
    assert not is_sequence_title_key("zzz")


def test_related_queue_prefers_failure_reason_not_attempt() -> None:
    title, metas = related_queue_title_and_meta(
        ("1", "Failed", "card_declined", "12 May 2026"),
        ("Attempt", "Status", "Failure Reason", "Created At"),
    )
    assert title == "card_declined"
    assert ("Attempt", "1") in metas
    assert ("Status", "Failed") in metas
    assert "1" != title


def test_related_queue_leftover_failure_reason_stays_put() -> None:
    title, metas = related_queue_title_and_meta(
        ("2", "Failed", "zzz", "ghost"),
        ("Attempt", "Status", "Failure Reason", "Created At"),
    )
    assert title == "zzz"
    assert ("Attempt", "2") in metas
    assert "ghost" in {raw for _, raw in metas}


def test_related_queue_html_titles_failure_reason() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="payments",
            label="Payment attempts",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="payments",
                    label="Payment attempts",
                    headers=("Attempt", "Status", "Failure Reason", "Created At"),
                    rows=(("1", "Failed", "card_declined", "12 May 2026"),),
                    row_drill=("/app/paymentattempt/a-1",),
                ),
            ),
        )
    )
    assert "card_declined" in html
    assert "dz-queue-row" in html or "data-dz-queue-row" in html
    assert "Status: Failed" in html
    assert "Attempt: 1" in html


def test_related_queue_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="payments",
            label="Payment attempts",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="payments",
                    label="Payment attempts",
                    headers=("Attempt", "Status", "Failure Reason"),
                    rows=(("3", "Failed", "zzz"),),
                ),
            ),
        )
    )
    assert ">zzz<" in html or "zzz" in html
    assert "Attempt: 3" in html


def test_invoice_ops_payment_queue_columns_lead_with_attempt() -> None:
    spec = load_project(Path("examples/invoice_ops"))
    ctxs = compile_appspec_to_templates(spec)
    detail = ctxs["/invoice/{id}"].detail
    assert detail is not None
    group = next(g for g in detail.related_groups if g.group_id == "group-payments")
    assert group.display == "queue"
    keys = [c.key for c in group.tabs[0].columns]
    assert keys[0] == "attempt_number"
    assert "failure_reason" in keys


def test_pick_display_key_skips_attempt_prefers_failure_reason() -> None:
    columns = [
        {"key": "invoice", "type": "ref"},
        {"key": "attempt_number", "type": "text"},
        {"key": "status", "type": "badge"},
        {"key": "failure_reason", "type": "text"},
        {"key": "created_at", "type": "datetime"},
    ]
    assert _pick_display_key(columns) == "failure_reason"
    assert _pick_display_key(columns, preferred="failure_reason") == "failure_reason"


def test_payment_attempt_text_identity_is_failure_reason() -> None:
    spec = load_project(Path("examples/invoice_ops"))
    runtime = convert_entity(spec.get_entity("PaymentAttempt"))
    cols = build_entity_columns(runtime, spec.enums)
    ctx = SimpleNamespace(entity_spec=runtime)
    assert _entity_text_identity_key(ctx) == "failure_reason"
    adapter_ctx: dict[str, object] = {}
    _set_display_key(adapter_ctx, SimpleNamespace(columns=cols), ctx)
    assert adapter_ctx["display_key"] != "attempt_number"
    assert adapter_ctx["display_key"] in {"failure_reason", "provider_reference"}
