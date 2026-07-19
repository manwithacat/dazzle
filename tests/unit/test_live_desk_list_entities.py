"""live_desk should try list/queue sources, not only first region (#1626 hygiene)."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.demo_data.test_mode_load import _default_workspace_list_entities


def test_prefers_list_queue_over_chart_and_orders_invoice_before_attempts() -> None:
    appspec = SimpleNamespace(
        workspaces=[
            SimpleNamespace(
                name="audit_review",
                regions=[
                    SimpleNamespace(name="trail_metrics", display="metrics", source="Invoice"),
                    SimpleNamespace(
                        name="payment_attempts", display="queue", source="PaymentAttempt"
                    ),
                    SimpleNamespace(name="settled_invoices", display="queue", source="Invoice"),
                ],
            )
        ]
    )
    entities = _default_workspace_list_entities(appspec, "audit_review")
    assert entities[0] == "PaymentAttempt"
    assert "Invoice" in entities
    # metrics source not listed alone as preferred path if only metrics —
    # Invoice appears via settled queue
    assert entities == ["PaymentAttempt", "Invoice"]


def test_skips_chart_displays() -> None:
    appspec = SimpleNamespace(
        workspaces=[
            SimpleNamespace(
                name="ops",
                regions=[
                    SimpleNamespace(name="funnel", display="funnel_chart", source="Ticket"),
                    SimpleNamespace(name="queue", display="list", source="Ticket"),
                ],
            )
        ]
    )
    assert _default_workspace_list_entities(appspec, "ops") == ["Ticket"]
