"""Backend regression gate for GitHub issue #1304.

Verifies that the ``agent_console`` workspace's ``context_selector`` correctly
scopes its region data when a ``context_id`` is supplied — for both a 1-hop and
a 2-hop dotted ``current_context`` filter.

Region endpoints under test (HTML render)::

    GET /api/workspaces/agent_console/regions/agent_tickets?context_id=<user>
    GET /api/workspaces/agent_console/regions/agent_ticket_comments?context_id=<user>

Filters (from examples/support_tickets/dsl/app.dsl)::

    agent_tickets:         filter: assigned_to = current_context        # 1-hop
    agent_ticket_comments: filter: ticket.assigned_to = current_context # 2-hop (the #1304 case)

Fixture (deterministic, distinct A-vs-B counts so scoping is unambiguous):

* AGENT_A: 3 tickets, 2 comments on those tickets.
* AGENT_B: 5 tickets, 0 comments.

The authenticated reader is a *manager* — Ticket/Comment ``scope:`` grants
``read/list: all`` to managers, so the only thing that narrows the region
response is the ``context_id`` substitution.  Any narrowing observed is
therefore attributable to ``current_context`` alone, which is the property
#1304 guards.

Assertions are on identifying content seeded into the rows (ticket numbers,
titles, comment bodies) rather than brittle full-body matches.
"""

from __future__ import annotations

import pytest

from tests.integration.support_tickets_harness import (
    M_A_COMMENTS,
    N_A_TICKETS,
    N_B_TICKETS,
    booted_support_tickets,
)

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_WS = "agent_console"


@pytest.fixture
async def app():
    async for a in booted_support_tickets():
        yield a


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _region_html(app, region: str, *, context_id: str | None) -> tuple[int, str]:
    """GET a region as the manager (broad reader) and return (status, body).

    Reads as the manager persona so the entity ``scope:`` rule never narrows
    the result — the region is then scoped purely by ``context_id``.
    """
    client = await app.client_as("manager")
    url = f"/api/workspaces/{_WS}/regions/{region}"
    if context_id is not None:
        url += f"?context_id={context_id}"
    resp = await client.get(url)
    return resp.status_code, resp.text


def _count_present(body: str, needles: list[str]) -> int:
    """Number of *needles* that appear in *body*."""
    return sum(1 for n in needles if n in body)


def _none_present(body: str, needles: list[str]) -> list[str]:
    """Subset of *needles* that (wrongly) appear in *body* — empty == clean."""
    return [n for n in needles if n in body]


# ---------------------------------------------------------------------------
# Test 1 — 1-hop region scopes to the selected agent (assigned_to = current_context)
# ---------------------------------------------------------------------------


async def test_agent_tickets_1hop_scopes_to_context(app) -> None:
    """``agent_tickets?context_id=A`` must show exactly A's 3 tickets, none of B's;
    ``context_id=B`` must show exactly B's 5 tickets, none of A's."""
    # --- context_id = AGENT_A ----------------------------------------------
    status_a, body_a = await _region_html(app, "agent_tickets", context_id=app.agent_a_id)
    assert status_a == 200, f"agent_tickets (A) returned {status_a}: {body_a[:400]!r}"

    a_present = _count_present(body_a, app.agent_a_ticket_numbers)
    assert a_present == N_A_TICKETS, (
        f"1-hop scope (context=A) should show all {N_A_TICKETS} of A's ticket "
        f"numbers; found {a_present} ({app.agent_a_ticket_numbers}). "
        f"Body snippet: {body_a[:600]!r}"
    )
    leaked_b = _none_present(body_a, app.agent_b_ticket_numbers)
    assert not leaked_b, (
        f"1-hop scope LEAK: context=A response contains B's ticket numbers "
        f"{leaked_b} — assigned_to = current_context is not filtering."
    )

    # --- context_id = AGENT_B ----------------------------------------------
    status_b, body_b = await _region_html(app, "agent_tickets", context_id=app.agent_b_id)
    assert status_b == 200, f"agent_tickets (B) returned {status_b}: {body_b[:400]!r}"

    b_present = _count_present(body_b, app.agent_b_ticket_numbers)
    assert b_present == N_B_TICKETS, (
        f"1-hop scope (context=B) should show all {N_B_TICKETS} of B's ticket "
        f"numbers; found {b_present} ({app.agent_b_ticket_numbers}). "
        f"Body snippet: {body_b[:600]!r}"
    )
    leaked_a = _none_present(body_b, app.agent_a_ticket_numbers)
    assert not leaked_a, (
        f"1-hop scope LEAK: context=B response contains A's ticket numbers "
        f"{leaked_a} — assigned_to = current_context is not filtering."
    )


# ---------------------------------------------------------------------------
# Test 2 — 2-hop dotted region (the #1304 core regression guard)
#          ticket.assigned_to = current_context
# ---------------------------------------------------------------------------


async def test_agent_ticket_comments_2hop_scopes_to_context(app) -> None:
    """``agent_ticket_comments?context_id=A`` must show A's 2 comments;
    ``context_id=B`` must show 0 (B's tickets have no comments).

    This is the dotted FK-path case (Comment -> ticket -> assigned_to) that
    #1304's backend fix targets.
    """
    # --- context_id = AGENT_A → 2 comments expected ------------------------
    status_a, body_a = await _region_html(app, "agent_ticket_comments", context_id=app.agent_a_id)
    assert status_a == 200, f"agent_ticket_comments (A) returned {status_a}: {body_a[:400]!r}"

    a_present = _count_present(body_a, app.agent_a_comment_contents)
    assert a_present == M_A_COMMENTS, (
        f"2-hop scope (context=A) should show all {M_A_COMMENTS} comments on A's "
        f"tickets; found {a_present} ({app.agent_a_comment_contents}). "
        f"Body snippet: {body_a[:600]!r}"
    )

    # --- context_id = AGENT_B → 0 comments expected ------------------------
    status_b, body_b = await _region_html(app, "agent_ticket_comments", context_id=app.agent_b_id)
    assert status_b == 200, f"agent_ticket_comments (B) returned {status_b}: {body_b[:400]!r}"

    # B's tickets have zero comments, so NONE of A's comment bodies may appear
    # (A's comments belong to A's tickets, not B's). A leak here means the
    # 2-hop ticket.assigned_to filter is not being applied at all.
    leaked = _none_present(body_b, app.agent_a_comment_contents)
    assert not leaked, (
        f"2-hop scope LEAK (#1304): context=B response contains A's comments "
        f"{leaked} — ticket.assigned_to = current_context (dotted FK path) is "
        f"not filtering. This is the exact regression #1304 fixes."
    )


# ---------------------------------------------------------------------------
# Test 3 — control: no context_id documents the no-context behaviour
# ---------------------------------------------------------------------------


async def test_no_context_id_control(app) -> None:
    """Document the behaviour with NO ``?context_id``.

    With ``current_context`` unbound the runtime returns 200 (the region still
    renders).  We don't pin the exact unbound-filter row set — the load-bearing
    property is the *narrowing* proven in tests 1 and 2.  This control's job is
    to (a) confirm the endpoint is reachable without a context (no 4xx/5xx) and
    (b) confirm that supplying a context_id is what discriminates A from B:
    the no-context body for the 1-hop region must NOT equal either scoped body
    (otherwise context_id would be a no-op and tests 1/2 could pass trivially).
    """
    status, body = await _region_html(app, "agent_tickets", context_id=None)
    assert status == 200, f"agent_tickets (no context) returned {status}: {body[:400]!r}"

    # Fetch the two scoped bodies for comparison.
    _, body_a = await _region_html(app, "agent_tickets", context_id=app.agent_a_id)
    _, body_b = await _region_html(app, "agent_tickets", context_id=app.agent_b_id)

    # Supplying a context_id must change the rendered region — if the no-context
    # body matched a scoped one, context_id would be inert (a #1304-class bug).
    assert body != body_a or body != body_b, (
        "Supplying context_id had NO effect on the agent_tickets region "
        "(no-context body identical to both scoped bodies) — context_selector "
        "is inert; tests 1/2 would pass trivially."
    )
    # And the two scoped bodies must themselves differ (A's 3 vs B's 5 tickets).
    assert body_a != body_b, (
        "context_id=A and context_id=B produced identical agent_tickets bodies "
        "— the 1-hop current_context filter is not discriminating."
    )


# ---------------------------------------------------------------------------
# context-options robustness (#1304 Defect A root cause)
# ---------------------------------------------------------------------------


async def test_context_options_survives_out_of_enum_row(app) -> None:
    """The context_selector's options endpoint must populate even when a
    context-entity row holds a value outside the entity's current enum.

    Pre-fix, ``context-options`` listed Users through the full entity Pydantic
    model (``_row_to_model``); a single row whose ``role`` was outside the
    ``customer/agent/manager`` enum (e.g. ``role_staff`` from demo data, or an
    ``admin`` persona the enum doesn't include) raised a 422 and the WHOLE
    endpoint failed — so the ``<select>`` stayed empty and "selecting did
    nothing". The fix projects only ``id`` + ``display_field`` (raw dicts), so
    one non-conforming row can't take down the selector.
    """
    import datetime as _dt
    import uuid as _uuid

    import psycopg

    from tests.integration.support_tickets_harness import _sql_insert

    bad_id = str(_uuid.uuid4())
    bad_label = "Wanda OutOfEnum"
    with psycopg.connect(app._db_url, autocommit=True) as conn:
        _sql_insert(
            conn,
            "User",
            {
                "id": bad_id,
                "email": f"wanda-{bad_id[:8]}@demo.test",
                "name": bad_label,
                "role": "role_staff",  # NOT in the customer/agent/manager enum
                "is_active": True,
                "created_at": _dt.datetime.now(_dt.UTC),
            },
        )

    client = await app.client_as("manager")
    try:
        resp = await client.get(f"/api/workspaces/{_WS}/context-options")
    finally:
        await client.aclose()

    assert resp.status_code == 200, (
        f"context-options 422'd on an out-of-enum row (pre-#1304-fix behaviour): "
        f"{resp.status_code} {resp.text[:300]!r}"
    )
    options = resp.json().get("options", [])
    # The selector must be populated (not empty) AND must include the
    # non-conforming row — the projection returns it by id+label regardless of
    # its enum-invalid role.
    assert len(options) >= 1, (
        f"selector options empty — selector would be inert: {resp.text[:300]!r}"
    )
    labels = {o.get("label") for o in options}
    assert bad_label in labels, (
        f"the out-of-enum User is missing from options ({sorted(labels)}); "
        "the projection should surface every row by id+label."
    )
