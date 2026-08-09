"""message-scroller hyperpart emitter — unit pins (cycle 1773).

``display: conversation`` → ``MessageScroller`` / ``.dz-message-scroller``
wrapping ``Message`` / ``.dz-message`` (nested Bubble).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import Bubble, FragmentRenderer, Message, MessageScroller
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"
SUPPORT = ROOT / "examples" / "support_tickets"


def test_message_scroller_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        MessageScroller(
            messages=(
                Message(
                    bubble=Bubble(text="Can we reschedule?", from_="in"),
                    author="Maya Reyes",
                    time_label="10:02",
                    media_label="MR",
                ),
                Message(
                    bubble=Bubble(text="Thursday works.", from_="out"),
                    author="You",
                    media_label="You",
                ),
            ),
            label="Conversation",
        )
    )
    assert 'class="dz-message-scroller"' in html
    assert "data-dz-message-scroller" in html
    assert 'role="log"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-label="Conversation"' in html
    assert 'tabindex="0"' in html
    assert html.count('class="dz-message"') == 2
    assert html.count('class="dz-bubble"') == 2
    assert "Can we reschedule?" in html
    assert "Thursday works." in html


def test_message_scroller_empty_affordance() -> None:
    html = FragmentRenderer().render(MessageScroller(messages=(), empty_message="No messages yet."))
    assert 'class="dz-message-scroller"' in html
    assert 'class="dz-message-scroller__empty"' in html
    assert "No messages yet." in html
    assert 'class="dz-message"' not in html


def test_message_scroller_size_attr() -> None:
    html = FragmentRenderer().render(
        MessageScroller(
            messages=(Message(bubble=Bubble(text="Hi", from_="in")),),
            size="sm",
        )
    )
    assert 'data-dz-size="sm"' in html


def test_build_conversation_wraps_in_message_scroller() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "sample_thread", "title": "Sample", "empty_message": None})()
    ctx: RegionContext = {
        "status_entries": [
            {"title": "in", "body": "Inbound note", "author": "Customer"},
            {"title": "out", "caption": "Outbound reply", "author": "Agent"},
        ],
        "items": [],
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-message-scroller"' in html
    assert "data-dz-message-scroller" in html
    assert html.count('class="dz-message"') >= 2
    assert 'class="dz-bubble"' in html
    assert "Inbound note" in html
    assert "Outbound reply" in html


def test_build_conversation_empty_still_mounts_scroller() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live", "title": "Live thread", "empty_message": None})()
    ctx: RegionContext = {
        "items": [],
        "status_entries": [],
        "empty_message": "Quiet channel.",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-message-scroller"' in html
    assert "Quiet channel." in html
    assert 'aria-label="Live thread"' in html


def test_build_conversation_from_comment_items_scroller() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live", "title": "Live", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {"content": "Customer: site down", "is_internal": False, "author": "Maya"},
            {"content": "Agent: investigating", "is_internal": True, "author": "You"},
        ],
        "status_entries": [],
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-message-scroller"' in html
    assert "Customer: site down" in html
    assert "Agent: investigating" in html
    assert 'data-dz-from="in"' in html
    assert 'data-dz-from="out"' in html


def test_simple_task_sample_thread_is_conversation() -> None:
    appspec = load_project_appspec(SIMPLE)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    admin = next((w for w in workspaces if getattr(w, "name", None) == "admin_dashboard"), None)
    assert admin is not None
    regions = list(getattr(admin, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("sample_thread")
    assert region is not None, f"sample_thread missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "conversation"


def test_support_tickets_live_conversation_is_conversation() -> None:
    text = (SUPPORT / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "display: conversation" in text
    appspec = load_project_appspec(SUPPORT)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    tq = next((w for w in workspaces if getattr(w, "name", None) == "ticket_queue"), None)
    assert tq is not None
    regions = {getattr(r, "name", None): r for r in list(getattr(tq, "regions", None) or [])}
    live = regions.get("live_conversation")
    assert live is not None
    display = getattr(live, "display", None)
    assert getattr(display, "value", display) == "conversation"


def test_dsl_shapes_message_scroller_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "message-scroller" not in planned
    assert snap["next_planned"] != "message-scroller"
    assert snap["live"] >= 75
