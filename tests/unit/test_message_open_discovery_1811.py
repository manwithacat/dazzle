"""Cycle 1811 — conversation Message open-discovery hub drills.

Agents attr-read note/detail hops from ``display: conversation`` Message
chrome without scraping bubble text. Empty drill stays byte-stable
(no anchor) — gallery / static dogfood parity.
"""

from __future__ import annotations

from dazzle.render.fragment import Bubble, FragmentRenderer, Message
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.open_discovery import hub_open_discovery_attrs, open_hop_label


def test_message_emit_without_drill_stays_chrome_only() -> None:
    html = FragmentRenderer().render(
        Message(
            bubble=Bubble(text="Hold on PO match", from_="in"),
            author="Ava Chen",
            media_label="AC",
        )
    )
    assert 'class="dz-message"' in html
    assert "data-dz-message-drill" not in html
    assert "data-dz-open-chain" not in html
    assert "dz-message__hub" not in html
    assert "Hold on PO match" in html


def test_message_emit_stamps_open_discovery_on_drill() -> None:
    html = FragmentRenderer().render(
        Message(
            bubble=Bubble(text="Dual sign-off needed", from_="out"),
            author="You",
            media_label="You",
            drill_url="/app/invoice-note/n-9",
        )
    )
    assert "data-dz-message-drill" in html
    assert 'class="dz-message__hub"' in html
    assert 'href="/app/invoice-note/n-9"' in html
    assert 'data-dz-open-entity="Invoice Note"' in html
    assert 'data-dz-open-via="id"' in html
    assert "Open Invoice Note" in html
    assert 'data-dz-open-chain="/app/invoice-note/n-9"' in html
    assert 'data-dz-from="out"' in html
    link_attrs, host_attrs = hub_open_discovery_attrs("/app/invoice-note/n-9")
    assert link_attrs in html
    assert host_attrs.strip() in html or host_attrs in html


def test_message_open_hop_label_entity_from_slug() -> None:
    assert open_hop_label("Invoice Note") == "Open Invoice Note"


def test_build_conversation_live_items_resolve_detail_url_template() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live_conversation", "title": "Live", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {
                "id": "n-1",
                "body": "PO matched — ready for approver",
                "author": "Ava Chen",
                "is_internal": False,
            },
            {
                "id": "n-2",
                "body": "Holding for dual sign-off",
                "author": "You",
                "is_internal": True,
            },
        ],
        "status_entries": [],
        "detail_url_template": "/app/invoice-note/{id}",
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-message-scroller"' in html
    assert html.count("data-dz-message-drill") == 2
    assert 'href="/app/invoice-note/n-1"' in html
    assert 'href="/app/invoice-note/n-2"' in html
    assert 'data-dz-open-entity="Invoice Note"' in html
    assert "PO matched" in html
    assert "dual sign-off" in html


def test_build_conversation_without_template_no_drill() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live_conversation", "title": "Live", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {"id": "n-1", "body": "Note without drill", "author": "Ava"},
        ],
        "status_entries": [],
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "Note without drill" in html
    assert "data-dz-message-drill" not in html
    assert "data-dz-open-chain" not in html


def test_build_conversation_static_entries_honor_explicit_drill_url() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "sample", "title": "Sample", "empty_message": None})()
    ctx: RegionContext = {
        "items": [],
        "status_entries": [
            {
                "title": "in",
                "body": "Static with drill",
                "author": "Customer",
                "drill_url": "/app/comment/c-1",
            },
        ],
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "data-dz-message-drill" in html
    assert 'href="/app/comment/c-1"' in html
    assert 'data-dz-open-entity="Comment"' in html
