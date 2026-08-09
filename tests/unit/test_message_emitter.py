"""message hyperpart emitter — unit pins (cycle 1770).

``display: conversation`` → stack of ``Message`` / ``.dz-message`` (nested Bubble).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import Bubble, FragmentRenderer, Message, Stack
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"
SUPPORT = ROOT / "examples" / "support_tickets"


def test_message_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Message(
            bubble=Bubble(text="Can we reschedule?", from_="in"),
            author="Maya Reyes",
            time_label="10:02",
            media_label="MR",
        )
    )
    assert 'class="dz-message"' in html
    assert 'data-dz-from="in"' in html
    assert 'class="dz-message__media"' in html
    assert "MR" in html
    assert 'class="dz-message__author"' in html
    assert "Maya Reyes" in html
    assert 'class="dz-message__time"' in html
    assert "10:02" in html
    assert 'class="dz-bubble"' in html
    assert "Can we reschedule?" in html


def test_message_outbound_reverses_orientation() -> None:
    html = FragmentRenderer().render(
        Message(
            bubble=Bubble(text="Hold sent.", from_="out", tone="danger"),
            author="You",
            media_label="You",
        )
    )
    assert 'class="dz-message"' in html
    assert 'data-dz-from="out"' in html
    assert 'data-dz-tone="danger"' in html
    assert "Hold sent." in html


def test_message_inherits_bubble_orientation_when_from_omitted() -> None:
    html = FragmentRenderer().render(Message(bubble=Bubble(text="Inbound", from_="in")))
    assert 'data-dz-from="in"' in html
    # No meta/media when empty
    assert "dz-message__meta" not in html
    assert "dz-message__media" not in html


def test_conversation_stack_emits_message_rows() -> None:
    html = FragmentRenderer().render(
        Stack(
            children=(
                Message(bubble=Bubble(text="Hello", from_="in"), author="C"),
                Message(bubble=Bubble(text="Hi back", from_="out"), author="A"),
            ),
            gap="sm",
        )
    )
    assert html.count('class="dz-message"') == 2
    assert html.count('class="dz-bubble"') == 2
    assert 'data-dz-from="in"' in html
    assert 'data-dz-from="out"' in html


def test_build_conversation_wraps_static_entries_in_message() -> None:
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
    assert 'class="dz-message"' in html
    assert html.count('class="dz-message"') >= 2
    assert 'class="dz-bubble"' in html
    assert "Inbound note" in html
    assert "Outbound reply" in html
    assert "Customer" in html
    assert "Agent" in html


def test_build_conversation_from_comment_items_message_rows() -> None:
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
    assert 'class="dz-message"' in html
    assert "Customer: site down" in html
    assert "Agent: investigating" in html
    assert 'data-dz-from="in"' in html
    assert 'data-dz-from="out"' in html
    # media initials derived from author
    assert "MR" in html or "M" in html


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


def test_dsl_shapes_message_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "message" not in planned
    assert snap["next_planned"] != "message"
    assert snap["live"] >= 74
