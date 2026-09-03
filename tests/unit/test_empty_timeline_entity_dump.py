"""Timeline/activity empty must not dump generic 'No events yet' (oral #222)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_activity_title,
    clerk_empty_timeline_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin

SIMPLE = Path("examples/simple_task")
SUPPORT = Path("examples/support_tickets")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"
SUPPORT_DSL = SUPPORT / "dsl" / "app.dsl"


class _A(_BuildersTimelineMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "upcoming_due",
        "title": "Upcoming due",
        "empty_message": None,
        "source": "Task",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_timeline(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_timeline(region, ctx or {}))


def _render_activity(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_activity_feed(region, ctx or {}))


def test_simple_task_upcoming_due_timeline_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    region = block.split("  upcoming_due:", 1)[1].split("  urgent_queue:", 1)[0]
    assert "display: timeline" in region
    assert "source: Task" in region
    assert 'empty: "No upcoming due dates"' in region


def test_support_agent_comment_activity_feed_is_live() -> None:
    block = SUPPORT_DSL.read_text()
    region = block.split("  agent_comment_activity:", 1)[1].split("  agent_status_funnel:", 1)[0]
    assert "display: activity_feed" in region
    assert "source: Comment" in region
    assert 'empty: "No comments for this agent"' in region


def test_clerk_empty_timeline_title_splits_pascal_and_catalog() -> None:
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Task", labels) == "Task"
    assert clerk_entity_confirm_noun("Task", labels) == "task"
    assert clerk_empty_timeline_title("Task", labels) == "No tasks yet."
    assert clerk_empty_timeline_title("Task") == "No tasks yet."
    assert clerk_empty_activity_title("Comment") == "No comments yet"


def test_clerk_empty_timeline_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_timeline_title(junk) == "No events yet."
        assert clerk_empty_activity_title(junk) == "No activity yet"


def test_timeline_empty_is_tasks_not_no_events() -> None:
    html = _render_timeline(_region())
    assert "No tasks yet." in html
    assert "No events yet." not in html
    assert "No taskss" not in html


def test_timeline_empty_ctx_source_entity_still_splits() -> None:
    html = _render_timeline(_region(source=""), {"source_entity": "Task"})
    assert "No tasks yet." in html
    assert "No events yet." not in html


def test_timeline_empty_authored_empty_still_wins() -> None:
    html = _render_timeline(_region(empty_message="No upcoming due dates"))
    assert "No upcoming due dates" in html
    assert "No tasks yet." not in html
    assert "No events yet." not in html


def test_timeline_empty_missing_entity_stays_no_events() -> None:
    html = _render_timeline(_region(source=""))
    assert "No events yet." in html
    assert "No tasks yet." not in html


def test_timeline_empty_leftover_invents_no_collection() -> None:
    html = _render_timeline(_region(source="zzz"))
    assert "No events yet." in html
    assert "No zzz" not in html


def test_activity_empty_is_comments_not_no_activity() -> None:
    html = _render_activity(_region(name="agent_comment_activity", source="Comment"))
    assert "No comments yet" in html
    assert "No activity yet" not in html
    assert "No commentss" not in html


def test_activity_empty_authored_empty_still_wins() -> None:
    html = _render_activity(
        _region(
            name="agent_comment_activity",
            source="Comment",
            empty_message="No comments for this agent",
        )
    )
    assert "No comments for this agent" in html
    assert "No comments yet" not in html
    assert "No activity yet" not in html


def test_activity_empty_leftover_invents_no_collection() -> None:
    html = _render_activity(_region(source="zzz"))
    assert "No activity yet" in html
    assert "No zzz" not in html
