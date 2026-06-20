"""Tests for #1194 — the approvals explorer route factory.

``create_approvals_routes`` exposes ``GET /_dazzle/approvals/pending``
which lists pending approvals per ``ApprovalSpec`` block. A row is
"pending" when its driving entity's ``trigger_field`` equals
``trigger_value``.

These tests cover:
* No approvals declared → empty list (the registration site decides
  whether to register the router at all, but the factory itself
  produces a sane empty response).
* N pending rows → response groups them correctly per ApprovalSpec.
* The ``limit`` query param caps ``sample_ids`` per approval block.
* Missing CRUD service for a declared entity is surfaced via the
  per-block ``error`` field rather than a 500.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.core.ir.approvals import ApprovalSpec
from dazzle.http.runtime.approvals_explorer import create_approvals_routes


def _row(row_id: str, **fields: Any) -> dict[str, Any]:
    return {"id": row_id, **fields}


class _FakeService:
    """Minimal CRUD-service stub satisfying EntityListService."""

    def __init__(self, entity_name: str, rows: list[dict[str, Any]]) -> None:
        self.entity_name = entity_name
        self._rows = rows

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
    ) -> dict[str, Any]:
        # Honour equality filters (mimics the real CRUDService behaviour).
        rows = list(self._rows)
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if r.get(key) == value]
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return {
            "items": page_rows,
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }


def _make_client(
    services: dict[str, _FakeService],
    approvals: list[ApprovalSpec],
) -> TestClient:
    app = FastAPI()
    app.include_router(create_approvals_routes(services, approvals))  # type: ignore[arg-type]
    return TestClient(app)


# ---------------------------------------------------------------------------
# Empty cases
# ---------------------------------------------------------------------------


def test_pending_no_approvals_declared() -> None:
    """Empty approvals list yields an empty pending response."""
    client = _make_client({}, [])
    resp = client.get("/_dazzle/approvals/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert body["approvals"] == []
    assert body["total_pending"] == 0
    assert body["limit"] == 20


def test_pending_no_matching_rows() -> None:
    """An ApprovalSpec with no matching rows reports count=0."""
    service = _FakeService(
        "Invoice",
        [_row("inv-1", status="draft"), _row("inv-2", status="approved")],
    )
    approval = ApprovalSpec(
        name="StandardApproval",
        entity="Invoice",
        trigger_field="status",
        trigger_value="submitted",
    )
    client = _make_client({"Invoice": service}, [approval])
    resp = client.get("/_dazzle/approvals/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["approvals"]) == 1
    summary = body["approvals"][0]
    assert summary["name"] == "StandardApproval"
    assert summary["entity"] == "Invoice"
    assert summary["count"] == 0
    assert summary["sample_ids"] == []
    assert body["total_pending"] == 0


# ---------------------------------------------------------------------------
# Populated cases
# ---------------------------------------------------------------------------


def test_pending_groups_per_approval_block() -> None:
    """Each ApprovalSpec gets its own summary keyed by block name."""
    invoice_rows = [
        _row("inv-1", status="submitted"),
        _row("inv-2", status="submitted"),
        _row("inv-3", status="approved"),
    ]
    purchase_rows = [
        _row("po-1", status="pending_approval"),
        _row("po-2", status="draft"),
    ]
    services = {
        "Invoice": _FakeService("Invoice", invoice_rows),
        "PurchaseOrder": _FakeService("PurchaseOrder", purchase_rows),
    }
    approvals = [
        ApprovalSpec(
            name="StandardApproval",
            entity="Invoice",
            trigger_field="status",
            trigger_value="submitted",
        ),
        ApprovalSpec(
            name="PurchaseApproval",
            entity="PurchaseOrder",
            trigger_field="status",
            trigger_value="pending_approval",
        ),
    ]
    client = _make_client(services, approvals)
    resp = client.get("/_dazzle/approvals/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["approvals"]) == 2

    invoice_summary = next(s for s in body["approvals"] if s["name"] == "StandardApproval")
    assert invoice_summary["count"] == 2
    assert set(invoice_summary["sample_ids"]) == {"inv-1", "inv-2"}

    po_summary = next(s for s in body["approvals"] if s["name"] == "PurchaseApproval")
    assert po_summary["count"] == 1
    assert po_summary["sample_ids"] == ["po-1"]

    assert body["total_pending"] == 3


def test_pending_sample_ids_honours_limit() -> None:
    """The limit query param caps sample_ids per approval block."""
    rows = [_row(f"inv-{i}", status="submitted") for i in range(10)]
    service = _FakeService("Invoice", rows)
    approval = ApprovalSpec(
        name="StandardApproval",
        entity="Invoice",
        trigger_field="status",
        trigger_value="submitted",
    )
    client = _make_client({"Invoice": service}, [approval])

    resp = client.get("/_dazzle/approvals/pending", params={"limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 3
    summary = body["approvals"][0]
    # All ten still counted, but only three sample ids returned.
    assert summary["count"] == 10
    assert len(summary["sample_ids"]) == 3


def test_pending_limit_out_of_range_rejected() -> None:
    """The limit query param is bounded 1..100."""
    client = _make_client({}, [])
    assert client.get("/_dazzle/approvals/pending", params={"limit": 0}).status_code == 422
    assert client.get("/_dazzle/approvals/pending", params={"limit": 999}).status_code == 422


# ---------------------------------------------------------------------------
# Defensive cases
# ---------------------------------------------------------------------------


def test_pending_missing_service_reports_error() -> None:
    """Declared ApprovalSpec on an unregistered entity surfaces the error."""
    approval = ApprovalSpec(
        name="GhostApproval",
        entity="DoesNotExist",
        trigger_field="status",
        trigger_value="pending",
    )
    client = _make_client({}, [approval])
    resp = client.get("/_dazzle/approvals/pending")
    assert resp.status_code == 200
    body = resp.json()
    summary = body["approvals"][0]
    assert summary["name"] == "GhostApproval"
    assert summary["count"] == 0
    assert summary["error"] is not None
    assert "DoesNotExist" in summary["error"]


@pytest.mark.parametrize(
    "trigger_field,trigger_value",
    [
        ("state", "needs_review"),
        ("approval_status", "open"),
    ],
)
def test_pending_honours_custom_trigger_field(trigger_field: str, trigger_value: str) -> None:
    """trigger_field can be any field — not hard-coded to 'status'."""
    rows = [
        _row("a", **{trigger_field: trigger_value}),
        _row("b", **{trigger_field: "other"}),
    ]
    service = _FakeService("Thing", rows)
    approval = ApprovalSpec(
        name="ThingApproval",
        entity="Thing",
        trigger_field=trigger_field,
        trigger_value=trigger_value,
    )
    client = _make_client({"Thing": service}, [approval])
    resp = client.get("/_dazzle/approvals/pending")
    body = resp.json()
    assert body["approvals"][0]["count"] == 1
    assert body["approvals"][0]["sample_ids"] == ["a"]
