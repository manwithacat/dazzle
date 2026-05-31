"""Backend regression gate for GitHub issue #1305.

#1304 fixed multi-hop ``current_context`` region filters and gated it on the
**list** path. #1305 is the sibling defect: the same filter was *silently
ignored* on the ``bar_chart`` / ``group_by`` / ``aggregate`` region path — the
chart returned the same buckets regardless of ``?context_id`` because the
aggregate paths consumed only ``scope_only_filters`` (the pure scope slice),
never the ``current_context`` slice of the region ``filter:``.

Regions under test (``agent_console`` workspace, examples/support_tickets)::

    agent_category_chart:  source: Ticket,  filter: assigned_to = current_context        # 1-hop
                           display: bar_chart, group_by: category, aggregate: count(Ticket)
    agent_comment_chart:   source: Comment, filter: ticket.assigned_to = current_context  # 2-hop
                           display: bar_chart, group_by: is_internal, aggregate: count(Comment)

Fixture (deterministic, disjoint per agent so scoping is provable):

* AGENT_A: 3 tickets (all ``category: bug``), 2 comments on those tickets.
* AGENT_B: 5 tickets (all ``category: inquiry``), 0 comments.

The reader is a *manager* (Ticket/Comment ``scope:`` grants ``read/list: all``),
so the only thing that narrows the aggregate is the ``context_id`` substitution.

The discriminator is the chart's bucket-count total, parsed from the rendered
``dz-bar-chart-value`` spans:

* 1-hop: context=A ⇒ total 3 (one bucket), context=B ⇒ total 5; pre-fix BOTH
  return 8 (both category buckets), the exact #1305 symptom.
* 2-hop: context=A ⇒ total 2, context=B ⇒ EMPTY chart (0); pre-fix B leaks A's
  2 comments because ``ticket.assigned_to = current_context`` never reached the
  GROUP BY.
"""

from __future__ import annotations

import re

import pytest

from tests.integration.support_tickets_harness import (
    M_A_COMMENTS,
    N_A_TICKETS,
    N_B_TICKETS,
    booted_support_tickets,
)

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_WS = "agent_console"

# Bar-chart bucket value: `<span class="dz-bar-chart-value">N</span>`.
_BAR_VALUE_RE = re.compile(r'dz-bar-chart-value"[^>]*>\s*(\d+)\s*<')


@pytest.fixture
async def app():
    async for a in booted_support_tickets():
        yield a


async def _region_html(app, region: str, *, context_id: str | None) -> tuple[int, str]:
    """GET a region as the manager (broad reader) so only context_id narrows it."""
    client = await app.client_as("manager")
    try:
        url = f"/api/workspaces/{_WS}/regions/{region}"
        if context_id is not None:
            url += f"?context_id={context_id}"
        resp = await client.get(url)
        return resp.status_code, resp.text
    finally:
        await client.aclose()


def _bar_total(body: str) -> int:
    """Sum every bar-chart bucket count in the rendered region body.

    The aggregate total is context-invariant ONLY if current_context is being
    dropped (the #1305 bug); a correct fix makes it track the selected agent.
    """
    return sum(int(n) for n in _BAR_VALUE_RE.findall(body))


# ---------------------------------------------------------------------------
# Test 1 — 1-hop aggregate re-scopes by context (assigned_to = current_context)
# ---------------------------------------------------------------------------


async def test_agent_category_chart_1hop_aggregate_scopes_to_context(app) -> None:
    """``agent_category_chart`` bar_chart total must follow the selected agent:
    A ⇒ 3 tickets, B ⇒ 5. Pre-#1305 both returned 8 (context dropped)."""
    status_a, body_a = await _region_html(app, "agent_category_chart", context_id=app.agent_a_id)
    assert status_a == 200, f"agent_category_chart (A) returned {status_a}: {body_a[:400]!r}"
    total_a = _bar_total(body_a)
    assert total_a == N_A_TICKETS, (
        f"1-hop aggregate (context=A) should count A's {N_A_TICKETS} tickets; "
        f"got bucket total {total_a}. A total of {N_A_TICKETS + N_B_TICKETS} means "
        f"current_context was dropped from the GROUP BY (#1305). Body: {body_a[:600]!r}"
    )

    status_b, body_b = await _region_html(app, "agent_category_chart", context_id=app.agent_b_id)
    assert status_b == 200, f"agent_category_chart (B) returned {status_b}: {body_b[:400]!r}"
    total_b = _bar_total(body_b)
    assert total_b == N_B_TICKETS, (
        f"1-hop aggregate (context=B) should count B's {N_B_TICKETS} tickets; "
        f"got bucket total {total_b}. Body: {body_b[:600]!r}"
    )

    # The two scoped charts must differ — proves context_id discriminates and
    # the test isn't passing on a context-invariant total.
    assert total_a != total_b, (
        "context=A and context=B produced identical aggregate totals — the "
        "1-hop current_context filter is not reaching the GROUP BY (#1305)."
    )


# ---------------------------------------------------------------------------
# Test 2 — 2-hop dotted aggregate (the #1305 core; parallels #1304's 2-hop)
#          ticket.assigned_to = current_context on a bar_chart
# ---------------------------------------------------------------------------


async def test_agent_comment_chart_2hop_aggregate_scopes_to_context(app) -> None:
    """``agent_comment_chart`` counts the selected agent's ticket comments:
    A ⇒ 2, B ⇒ 0 (empty chart). Pre-#1305 B leaks A's 2 comments because the
    dotted FK-path context filter never reached the aggregate query."""
    status_a, body_a = await _region_html(app, "agent_comment_chart", context_id=app.agent_a_id)
    assert status_a == 200, f"agent_comment_chart (A) returned {status_a}: {body_a[:400]!r}"
    total_a = _bar_total(body_a)
    assert total_a == M_A_COMMENTS, (
        f"2-hop aggregate (context=A) should count A's {M_A_COMMENTS} comments; "
        f"got bucket total {total_a}. Body: {body_a[:600]!r}"
    )

    status_b, body_b = await _region_html(app, "agent_comment_chart", context_id=app.agent_b_id)
    assert status_b == 200, f"agent_comment_chart (B) returned {status_b}: {body_b[:400]!r}"
    total_b = _bar_total(body_b)
    assert total_b == 0, (
        f"2-hop aggregate (context=B) must be EMPTY — B's tickets have no "
        f"comments — but got bucket total {total_b}. A nonzero total means "
        f"ticket.assigned_to = current_context (dotted FK path) is not scoping "
        f"the GROUP BY: the exact #1305 regression. Body: {body_b[:600]!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — control: no context_id documents the unbound (both-agents) total
# ---------------------------------------------------------------------------


async def test_no_context_aggregate_control(app) -> None:
    """With no ``?context_id`` the 1-hop aggregate is unbound on the context
    axis and counts *all* agents' tickets (3 + 5 = 8). This is the value the
    bug returned for EVERY context — its presence here, contrasted with the
    scoped totals in test 1, is what proves context_id is the discriminator."""
    status, body = await _region_html(app, "agent_category_chart", context_id=None)
    assert status == 200, f"agent_category_chart (no context) returned {status}: {body[:400]!r}"
    total = _bar_total(body)
    assert total == N_A_TICKETS + N_B_TICKETS, (
        f"no-context aggregate should count all {N_A_TICKETS + N_B_TICKETS} "
        f"tickets; got {total}. Body: {body[:600]!r}"
    )
