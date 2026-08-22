"""Conversation author suffix must not dump schema tokens (oral #181)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.primitives import RelatedTab
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.renderer._related_conversation import (
    conversation_channel_label,
    related_conversation_messages,
)

OPS = Path("examples/ops_dashboard/dsl")


def test_ops_dashboard_live_conversation_is_live() -> None:
    block = (OPS / "app.dsl").read_text()
    assert "entity IncidentNote" in block
    assert "page_channel: enum[bridge,slack,pager,status_page]=bridge" in block
    assert "display: conversation" in block
    assert "live_conversation:" in block
    seeds = (OPS / "seeds/demo_data/IncidentNote.jsonl").read_text()
    assert '"page_channel": "status_page"' in seeds


def test_clerk_conversation_channel_leftover_and_empty() -> None:
    assert conversation_channel_label("status_page") == "Status Page"
    assert conversation_channel_label("slack") == "Slack"
    assert conversation_channel_label("repro") == "Repro"
    assert conversation_channel_label("portal") == ""
    assert conversation_channel_label("bridge") == ""
    assert conversation_channel_label("note") == ""
    assert conversation_channel_label("zzz") == "zzz"
    assert conversation_channel_label("ghost") == "ghost"
    assert conversation_channel_label("") == ""
    assert conversation_channel_label(None) == ""  # type: ignore[arg-type]


def test_workspace_conversation_status_page_is_clerk_not_schema_token() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live", "title": "Live", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {
                "body": "Customer status page updated: intermittent cache miss.",
                "author": "admin",
                "page_channel": "status_page",
            },
            {
                "body": "Ack'd on the default bridge.",
                "author": "ops_engineer",
                "page_channel": "bridge",
            },
            {
                "body": "Leftover channel stays put.",
                "author": "admin",
                "page_channel": "zzz",
            },
        ],
        "status_entries": [],
        "empty_message": "none",
    }
    html = FragmentRenderer().render(_A()._build_conversation(region, ctx))
    assert "admin · Status Page" in html
    assert "status_page" not in html
    assert "ops_engineer · bridge" not in html
    assert "ops_engineer" in html
    assert "admin · zzz" in html
    assert "admin · Zzz" not in html


def test_related_conversation_status_page_is_clerk_not_schema_token() -> None:
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("body", "author", "page_channel", "created_at"),
        rows=(
            (
                "Customer status page updated.",
                "admin",
                "status_page",
                "2026-07-21T12:05:00",
            ),
            ("Ack on default path.", "ops_engineer", "bridge", "2026-07-21T12:06:00"),
            ("Leftover stays put.", "admin", "zzz", "2026-07-21T12:07:00"),
            ("Empty invents no suffix.", "admin", "", "2026-07-21T12:08:00"),
        ),
        row_drill=("", "", "", ""),
    )
    msgs = related_conversation_messages(tab)
    assert msgs[0].author == "admin · Status Page"
    assert msgs[1].author == "ops_engineer"
    assert msgs[2].author == "admin · zzz"
    assert msgs[3].author == "admin"
    assert "status_page" not in msgs[0].author
    assert "Zzz" not in msgs[2].author
