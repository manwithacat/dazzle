"""Transition-RBAC tests for examples/invoice_ops.

Exercises the ``transitions:`` role guards declared on the Invoice entity:
  draft -> submitted:  role(requester)
  submitted -> approved: role(approver)
  submitted -> rejected: role(approver) requires rejection_reason
  approved -> paid:    role(finance)
  approved -> disputed: role(finance) requires dispute_reason

Tests confirm:
  1. A requester cannot drive the submitted->approved transition (approver-only).
  2. An approver cannot drive the approved->paid transition (finance-only).
  3. An approver CAN drive the submitted->approved transition (positive control).

Important caveats
-----------------
* ``dazzle validate`` reports ``[Preview] approval gates are not yet enforced at
  runtime``.  The two-approver quorum (StandardApproval / HighValueApproval) is
  therefore NOT tested here.
* Whether the ``transitions: role()`` guards are runtime-enforced on the PUT route
  is UNKNOWN ahead of this test run — the tests will discover it.  If a negative
  control (tests 1 or 2) passes when it should fail, the test is left asserting
  correct behaviour so the failure surfaces as a real framework gap.

Confirmed route paths (via ``dazzle inspect routes --runtime``):
  /invoices/{id:uuid}   GET  PUT  DELETE
"""

from __future__ import annotations

import pytest

from tests.integration.invoice_ops_harness import (
    _csrf_put,
    booted_invoice_ops,
)

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


@pytest.fixture
async def app():
    async for a in booted_invoice_ops():
        yield a


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_invoice_json(app, role: str, tenant: str, invoice_id: str) -> dict:
    """GET an invoice as *role*/*tenant* and return the JSON body.

    Reads as a role that has broad read access (finance has read on all
    in-scope invoices) to maximise the chance of getting the full record.
    Falls back to returning an empty dict on non-200 so callers can handle it.
    """
    client = await app.client_as(role, tenant)
    resp = await client.get(f"/invoices/{invoice_id}")
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            # Response may be HTML (the UI runtime renders forms, not JSON).
            # Return a minimal synthetic body so callers can still build a PUT.
            return {}
    return {}


def _flatten_for_put(data: dict) -> dict:
    """Flatten a GET-response body into a form suitable for PUT.

    The GET endpoint returns nested FK objects (e.g. ``supplier`` is the full
    Supplier row dict).  The PUT route expects plain UUID strings for FK fields.
    This helper replaces any value that is a dict with its ``id`` sub-key, and
    drops read-only server-managed fields (``created_at``, ``updated_at``,
    ``tenant``) that the runtime rejects on write.

    Also drops ``tenant_id`` when supplied as a nested dict — same pattern.
    """
    _DROP = {"created_at", "updated_at", "tenant"}
    flat: dict = {}
    for k, v in data.items():
        if k in _DROP:
            continue
        if isinstance(v, dict):
            # FK reference — use the id sub-key.
            flat[k] = v.get("id", v)
        else:
            flat[k] = v
    return flat


def _build_put_body(base: dict, **overrides: object) -> dict:
    """Flatten *base* (from a GET response) and merge *overrides* for a PUT."""
    body = _flatten_for_put(base)
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Test 1 — requester CANNOT approve (submitted -> approved is approver-only)
# ---------------------------------------------------------------------------


async def test_requester_cannot_approve(app) -> None:
    """A requester attempting submitted->approved must be denied (403/404/422).

    The ``submitted -> approved: role(approver)`` guard should prevent any
    other role from performing this transition.  If the PUT succeeds (200/204)
    the runtime is NOT enforcing transition role-guards — the test fails so
    the gap is visible.
    """
    invoice_id = app.northwind_submitted_invoice_id
    assert invoice_id, "harness must provide northwind_submitted_invoice_id"

    # Read the current invoice as finance (broad reader) to get a valid base body.
    base = await _get_invoice_json(app, "finance", "northwind", invoice_id)

    # Build the PUT body: change status to approved.
    body = _build_put_body(base, status="approved")

    client = await app.client_as("requester", "northwind")
    resp = await _csrf_put(client, f"/invoices/{invoice_id}", body)

    assert resp.status_code in (403, 404, 422), (
        f"Transition role-guard NOT enforced: requester successfully changed "
        f"submitted->approved (status {resp.status_code}). "
        f"Expected denial (403/404/422). "
        f"Response body snippet: {resp.text[:400]!r}. "
        f"This indicates the runtime does not enforce transition role() guards on "
        f"the PUT /invoices/{{id}} route — a real framework gap."
    )


# ---------------------------------------------------------------------------
# Test 2 — approver CANNOT pay (approved -> paid is finance-only)
# ---------------------------------------------------------------------------


async def test_approver_cannot_pay(app) -> None:
    """An approver attempting approved->paid must be denied (403/404/422).

    The ``approved -> paid: role(finance)`` guard should prevent an approver
    (who only holds the approver role) from paying an invoice.  If the PUT
    succeeds the runtime is NOT enforcing the transition guard.
    """
    invoice_id = app.northwind_approved_invoice_id
    assert invoice_id, "harness must provide northwind_approved_invoice_id"

    # Read the current invoice as finance to get a valid base body.
    base = await _get_invoice_json(app, "finance", "northwind", invoice_id)

    body = _build_put_body(base, status="paid")

    client = await app.client_as("approver", "northwind")
    resp = await _csrf_put(client, f"/invoices/{invoice_id}", body)

    assert resp.status_code in (403, 404, 422), (
        f"Transition role-guard NOT enforced: approver successfully changed "
        f"approved->paid (status {resp.status_code}). "
        f"Expected denial (403/404/422). "
        f"Response body snippet: {resp.text[:400]!r}. "
        f"This indicates the runtime does not enforce transition role() guards on "
        f"the PUT /invoices/{{id}} route — a real framework gap."
    )


# ---------------------------------------------------------------------------
# Test 3 — approver CAN approve (positive control: submitted -> approved)
# ---------------------------------------------------------------------------


async def test_approver_can_approve(app) -> None:
    """Positive control: approver driving submitted->approved must succeed (200).

    This guards against a false-green in tests 1 and 2: if every PUT returns
    404 (e.g. because the PUT route is not wired or the harness seed is broken)
    tests 1 and 2 would pass trivially without proving anything.

    If this test fails with 403/404/422, the most likely causes are:
      a) The PUT route is not enforcing transitions at all — but the *scope*
         gate is blocking the request (e.g. wrong role on the update permit).
      b) The invoice_edit surface's PUT route requires a different body shape.
      c) The runtime does not parse the Content-Type: application/json body.

    The failure message includes the response body to aid diagnosis.
    """
    invoice_id = app.northwind_submitted_invoice_id
    assert invoice_id, "harness must provide northwind_submitted_invoice_id"

    # Read as finance (broad reader) to get the full record.
    base = await _get_invoice_json(app, "finance", "northwind", invoice_id)

    body = _build_put_body(base, status="approved", approval_exception="Released for settlement")

    client = await app.client_as("approver", "northwind")
    resp = await _csrf_put(client, f"/invoices/{invoice_id}", body)

    if resp.status_code not in (200, 204, 302):
        # Diagnose — read the invoice directly to confirm it is visible.
        check = await app.client_as("approver", "northwind")
        read_resp = await check.get(f"/invoices/{invoice_id}")
        pytest.fail(
            f"Positive control FAILED: approver cannot drive submitted->approved. "
            f"PUT status: {resp.status_code}. "
            f"Response body snippet: {resp.text[:400]!r}. "
            f"Direct GET of same invoice as approver: {read_resp.status_code}. "
            f"Base body used for PUT: {body!r}. "
            f"Possible causes: (a) runtime does not enforce transition role-guards at "
            f"all AND scope/permit gate also blocks approver from PUTing; "
            f"(b) body shape mismatch (runtime expects form data not JSON); "
            f"(c) transition role-guards ARE enforced and something else is wrong."
        )
