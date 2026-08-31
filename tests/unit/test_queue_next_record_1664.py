"""#1664: after: next — land on the next matching record, not the pile."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.http.runtime.next_record import (
    after_next_redirect,
    leftover_honest_origin,
    pick_next_id,
    resolve_after_next_url,
    stamp_queue_after_next,
    workspace_from_region_endpoint,
)

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"

_SRC = """module ops
app t "T"

entity Ticket "Ticket":
  id: uuid pk

workspace desk "Desk":
  q:
    source: Ticket
    display: queue
{extra}
"""


def _parse_after(extra: str) -> object:
    return parse_dsl(_SRC.format(extra=extra), "t.dsl")[5].workspaces[0].regions[0].after


def test_after_keyword_parses() -> None:
    assert _parse_after("    after: next") == "next"
    assert _parse_after("") is None


def test_after_invalid_value_rejected() -> None:
    with pytest.raises(ParseError, match="after"):
        _parse_after("    after: stack")


def test_pick_next_id_skips_the_row_just_left() -> None:
    assert pick_next_id(["a", "b", "c"], "a") == "b"
    assert pick_next_id(["a", "b", "c"], "b") == "a"
    assert pick_next_id(["a"], "a") is None
    assert pick_next_id([], "a") is None


def test_after_next_redirect_detail_or_workspace() -> None:
    assert (
        after_next_redirect(
            next_id="inv-2",
            entity_slug="invoice",
            workspace="approval_desk",
            drill_none=False,
            has_view=True,
        )
        == "/app/invoice/inv-2"
    )
    assert (
        after_next_redirect(
            next_id=None,
            entity_slug="invoice",
            workspace="approval_desk",
            drill_none=False,
            has_view=True,
        )
        == "/app/workspaces/approval_desk"
    )
    assert (
        after_next_redirect(
            next_id="inv-2",
            entity_slug="invoice",
            workspace="approval_desk",
            drill_none=True,
            has_view=True,
        )
        == "/app/workspaces/approval_desk"
    )


def test_leftover_origin_stays_put() -> None:
    assert leftover_honest_origin("awaiting_approval") == "awaiting_approval"
    assert leftover_honest_origin("Approval Desk") is None
    assert leftover_honest_origin("zzz!") is None
    assert leftover_honest_origin("") is None


def test_workspace_from_region_endpoint() -> None:
    assert (
        workspace_from_region_endpoint("/api/workspaces/approval_desk/regions/awaiting_approval")
        == "approval_desk"
    )
    assert workspace_from_region_endpoint("/elsewhere") == ""


def test_invoice_ops_dogfoods_after_next() -> None:
    text = SURFACES.read_text()
    desk = text[text.index('workspace approval_desk "Approval Desk":') :]
    awaiting = desk.split("\n  awaiting_approval:", 1)[1].split("\n  live_conversation:", 1)[0]
    assert "after: next" in awaiting
    assert "transitions: none" in awaiting
    pay = text[text.index('workspace pay_desk "Pay Desk":') :]
    assert "after: next" in pay.split("\n  ready_to_pay:", 1)[1].split("\n  past_due:", 1)[0]
    assert "after: next" in pay.split("\n  past_due:", 1)[1].split("\n  disputed_queue:", 1)[0]


def test_find_region_requires_after_next() -> None:
    from dazzle.http.runtime.next_record import find_region

    region = SimpleNamespace(name="q", after="next", drill=None)
    ws = SimpleNamespace(name="desk", regions=[region])
    appspec = SimpleNamespace(workspaces=[ws])
    assert find_region(appspec, "desk", "q") is region
    assert find_region(appspec, "desk", "nope") is None


def test_stamp_queue_after_next_origin_and_query() -> None:
    ctx = SimpleNamespace(
        ir_region=SimpleNamespace(after="next", name="awaiting_approval"),
        ctx_region=SimpleNamespace(
            endpoint="/api/workspaces/approval_desk/regions/awaiting_approval"
        ),
    )
    adapter: dict[str, object] = {"detail_url_template": "/app/invoice/{id}"}
    stamp_queue_after_next(adapter, ctx)
    assert adapter["after_workspace"] == "approval_desk"
    assert adapter["after_region"] == "awaiting_approval"
    assert adapter["detail_url_template"] == (
        "/app/invoice/{id}?from_ws=approval_desk&from_rg=awaiting_approval"
    )


def test_stamp_queue_after_next_noop_without_flag() -> None:
    ctx = SimpleNamespace(
        ir_region=SimpleNamespace(after=None, name="q"),
        ctx_region=SimpleNamespace(endpoint="/api/workspaces/desk/regions/q"),
    )
    adapter: dict[str, object] = {"detail_url_template": "/app/invoice/{id}"}
    stamp_queue_after_next(adapter, ctx)
    assert "after_workspace" not in adapter
    assert adapter["detail_url_template"] == "/app/invoice/{id}"


class _ListService:
    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = items

    async def list(self, **_kwargs: object) -> dict[str, object]:
        return {"items": self.items}


def _appspec(*, after: str | None = "next", drill: str | None = None) -> SimpleNamespace:
    region = SimpleNamespace(name="q", after=after, drill=drill, filter=None, sort=None, limit=50)
    return SimpleNamespace(workspaces=[SimpleNamespace(name="desk", regions=[region])])


@pytest.mark.asyncio
async def test_resolve_after_next_url_lands_on_next_id() -> None:
    url = await resolve_after_next_url(
        service=_ListService([{"id": "a"}, {"id": "b"}]),
        appspec=_appspec(),
        workspace="desk",
        region="q",
        skip_id="a",
        entity_slug="invoice",
    )
    assert url == "/app/invoice/b"


@pytest.mark.asyncio
async def test_resolve_after_next_url_empty_goes_to_workspace() -> None:
    url = await resolve_after_next_url(
        service=_ListService([{"id": "a"}]),
        appspec=_appspec(),
        workspace="desk",
        region="q",
        skip_id="a",
        entity_slug="invoice",
    )
    assert url == "/app/workspaces/desk"


@pytest.mark.asyncio
async def test_resolve_after_next_url_leftover_origin_stays_put() -> None:
    url = await resolve_after_next_url(
        service=_ListService([{"id": "a"}, {"id": "b"}]),
        appspec=_appspec(),
        workspace="Approval Desk",
        region="q",
        skip_id="a",
        entity_slug="invoice",
    )
    assert url is None


@pytest.mark.asyncio
async def test_resolve_after_next_url_unset_flag_is_none() -> None:
    url = await resolve_after_next_url(
        service=_ListService([{"id": "a"}, {"id": "b"}]),
        appspec=_appspec(after=None),
        workspace="desk",
        region="q",
        skip_id="a",
        entity_slug="invoice",
    )
    assert url is None
