"""Goal B depth pins for examples/simple_task, read from the parsed AppSpec.

Conversation, document, media, command density, org structure and
empty-region honesty, as one table per kind of fact: the exact ordered
regions of each desk (which also pins what was pruned), its focus, the
region clauses that carry the depth, entity and surface shape, and the
demo seeds. Facts come from ``load_project_appspec``, not the DSL text, so
formatting and comments can change freely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.appspec_loader import load_project_appspec

APP_ROOT = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
SEEDS = APP_ROOT / "dsl" / "seeds" / "demo_data"


@pytest.fixture(scope="module")
def appspec() -> Any:
    return load_project_appspec(APP_ROOT)


def _cond(c: Any) -> str:
    """Render a parsed condition back to DSL-shaped text."""
    if c.comparison is not None:
        value = c.comparison.value
        if value.date_expr is not None:
            val = str(value.date_expr)
        elif value.literal is None:
            val = "null"
        elif isinstance(value.literal, bool):
            val = str(value.literal).lower()
        else:
            val = str(value.literal)
        return f"{c.comparison.field} {c.comparison.operator.value} {val}"

    def side(child: Any) -> str:
        text = _cond(child)
        nested = child.comparison is None and child.operator not in (None, c.operator)
        return f"({text})" if nested else text

    return f"{side(c.left)} {c.operator.value} {side(c.right)}"


def _region_facts(region: Any) -> dict[str, Any]:
    return {
        "filter": _cond(region.filter) if region.filter is not None else None,
        "sort": ", ".join(f"{s.field} {s.direction}" for s in region.sort) or None,
        "limit": region.limit,
        "group_by": region.group_by,
        "aggregates": {
            key: f"{ref.func}({ref.entity}"
            + (f" where {_cond(ref.where)}" if ref.where is not None else "")
            + ")"
            for key, ref in region.aggregates.items()
        },
    }


def _workspace(appspec: Any, name: str) -> Any:
    return next(ws for ws in appspec.workspaces if ws.name == name)


def _field(entity: Any, name: str) -> str:
    """`<type>[ required][=default]` for one entity field."""
    field = next(f for f in entity.fields if f.name == name)
    ft = field.type
    kind = ft.kind.value
    if ft.enum_values:
        kind = f"enum[{','.join(ft.enum_values)}]"
    elif ft.max_length:
        kind = f"{kind}({ft.max_length})"
    required = " required" if any(m.value == "required" for m in field.modifiers) else ""
    default = f"={field.default}" if field.default is not None else ""
    return f"{kind}{required}{default}"


# (a) Exact ordered regions per desk: (name, display, source).
WORKSPACE_REGIONS = {
    "admin_dashboard": [
        ("open_questions", "conversation", "TaskComment"),
        ("media_shelf", "grid", "User"),
        ("metrics", "metrics", "Task"),
        ("team_metrics", "metrics", "User"),
        ("urgent_tasks", "queue", "Task"),
        ("overdue_tasks", "queue", "Task"),
        ("composition", "queue", "TaskBrief"),
        ("live_conversation", "conversation", "TaskComment"),
        ("sample_thread", "conversation", None),
        ("status_mix", "bar_chart", "Task"),
        ("priority_mix", "bar_chart", "Task"),
    ],
    "team_overview": [
        ("open_questions", "conversation", "TaskComment"),
        ("media_shelf", "grid", "User"),
        ("metrics", "metrics", "Task"),
        ("needs_review", "queue", "Task"),
        ("plate_by_person", "kanban", "Task"),
        ("composition", "queue", "TaskBrief"),
        ("live_conversation", "conversation", "TaskComment"),
        ("team_roster", "queue", "User"),
        ("lead_readiness", "status_list", None),
    ],
    "my_work": [
        ("my_summary", "metrics", "Task"),
        ("my_board", "kanban", "Task"),
        ("my_upcoming", "timeline", "Task"),
        ("composition", "queue", "TaskBrief"),
        ("live_conversation", "conversation", "TaskComment"),
        ("focus_hint", "status_list", None),
    ],
    "task_board": [
        ("board_pulse", "metrics", "Task"),
        ("tasks", "kanban", "Task"),
        ("by_assignee", "kanban", "Task"),
        ("upcoming_due", "timeline", "Task"),
        ("urgent_queue", "queue", "Task"),
    ],
    "comments_desk": [
        ("comment_pulse", "metrics", "TaskComment"),
        ("recent", "queue", "TaskComment"),
        ("comment_trail", "timeline", "TaskComment"),
        ("active_tasks", "queue", "Task"),
    ],
    "people_desk": [
        ("people_pulse", "metrics", "User"),
        ("by_role", "kanban", "User"),
        ("by_department", "queue", "User"),
        ("unassigned_work", "queue", "Task"),
        ("plate_by_person", "kanban", "Task"),
        ("in_flight_board", "kanban", "Task"),
    ],
}


@pytest.mark.parametrize("ws", list(WORKSPACE_REGIONS))
def test_workspace_regions(appspec: Any, ws: str) -> None:
    regions = [(r.name, str(r.display), r.source) for r in _workspace(appspec, ws).regions]
    assert regions == WORKSPACE_REGIONS[ws]


# (b) Focus per desk — every persona variant names the same eager regions.
FOCUS = {
    "admin_dashboard": ["open_questions", "media_shelf", "metrics"],
    "team_overview": ["open_questions", "media_shelf", "metrics"],
    "my_work": ["my_summary", "my_board", "my_upcoming", "composition", "live_conversation"],
    "task_board": ["board_pulse", "tasks", "by_assignee", "upcoming_due", "urgent_queue"],
    "comments_desk": ["comment_pulse", "recent", "comment_trail", "active_tasks"],
    "people_desk": [
        "people_pulse",
        "by_role",
        "by_department",
        "unassigned_work",
        "plate_by_person",
    ],
}


@pytest.mark.parametrize("ws", list(FOCUS))
def test_workspace_focus(appspec: Any, ws: str) -> None:
    variants = _workspace(appspec, ws).ux.persona_variants
    assert variants
    assert {tuple(v.focus) for v in variants} == {tuple(FOCUS[ws])}


# (c) Region clauses that carry each depth.
_HEADSHOTS = {"filter": "is_active = true and photo_url != null", "sort": "created_at desc"}
_TRAIL = {"sort": "created_at desc", "limit": 4}
REGION_CLAUSES = [
    ("admin_dashboard", "open_questions", {"filter": "note_kind = question", "limit": 4}),
    ("admin_dashboard", "media_shelf", _HEADSHOTS),
    ("team_overview", "media_shelf", _HEADSHOTS),
    ("admin_dashboard", "urgent_tasks", {"limit": 4}),
    ("admin_dashboard", "overdue_tasks", {"limit": 4}),
    ("team_overview", "needs_review", {"limit": 4}),
    ("my_work", "my_upcoming", {"limit": 4}),
    ("admin_dashboard", "live_conversation", _TRAIL),
    ("team_overview", "live_conversation", _TRAIL),
    ("my_work", "live_conversation", _TRAIL),
    ("people_desk", "by_role", {"group_by": "role"}),
    (
        "admin_dashboard",
        "metrics",
        {
            "aggregates": {
                "total_tasks": "count(Task)",
                "todo": "count(Task where status = todo)",
                "in_progress": "count(Task where status = in_progress)",
                "in_review": "count(Task where status = review)",
                "documents": "count(TaskBrief)",
                "conversation": "count(TaskComment)",
                "questions": "count(TaskComment where note_kind = question)",
            }
        },
    ),
]


@pytest.mark.parametrize(
    ("ws", "region", "expected"),
    REGION_CLAUSES,
    ids=[f"{ws}.{region}" for ws, region, _ in REGION_CLAUSES],
)
def test_region_clauses(appspec: Any, ws: str, region: str, expected: dict[str, Any]) -> None:
    facts = _region_facts(next(r for r in _workspace(appspec, ws).regions if r.name == region))
    assert {key: facts[key] for key in expected} == expected


# (d) Entity shape: title, display field, card repr and the depth-bearing fields.
ENTITIES = {
    "TaskComment": (
        "Task Comment",
        "content",
        ["task", "author", "content", "note_kind"],
        {"content": "text required", "note_kind": "enum[note,blocker,question,decision]=note"},
    ),
    "TaskBrief": (
        "Task Brief",
        "headline",
        ["task", "headline", "doc_kind", "author"],
        {"doc_kind": "enum[brief,acceptance,runbook,checklist]=brief"},
    ),
    # Identity chips, not a schema dump: photo_url / email / is_active stay off cards.
    "User": ("Team Member", "name", ["name", "role", "department"], {"photo_url": "url"}),
}


@pytest.mark.parametrize("name", list(ENTITIES))
def test_entity_shape(appspec: Any, name: str) -> None:
    title, display_field, repr_fields, fields = ENTITIES[name]
    entity = next(e for e in appspec.domain.entities if e.name == name)
    assert (entity.title, entity.display_field, entity.fitness.repr_fields) == (
        title,
        display_field,
        repr_fields,
    )
    assert {f: _field(entity, f) for f in fields} == fields


# (e) Surfaces: the task hub's discussion is conversation chrome; briefs open two ways.
def test_task_detail_related_groups(appspec: Any) -> None:
    detail = next(s for s in appspec.surfaces if s.name == "task_detail")
    groups = [(g.name, str(g.display), g.show, g.columns) for g in detail.related_groups]
    assert groups == [
        ("briefs", "queue", ["TaskBrief"], ["headline", "doc_kind", "author"]),
        (
            "discussion",
            "conversation",
            ["TaskComment"],
            ["content", "author", "note_kind", "created_at"],
        ),
    ]


def test_brief_surfaces_dual_open(appspec: Any) -> None:
    surfaces = {s.name: s for s in appspec.surfaces}
    assert (surfaces["brief_list"].title, surfaces["brief_detail"].title) == (
        "Briefs",
        "Brief Detail",
    )
    targets = [(t.via, t.entity) for t in surfaces["brief_list"].open_via_targets]
    assert targets == [("id", "TaskBrief"), ("task", "Task")]


# (f) Demo seeds carry domain-true copy for each depth.
def _rows(name: str) -> list[dict[str, Any]]:
    lines = (SEEDS / f"{name}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _comments(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 10
    kinds = [r.get("note_kind") for r in rows]
    assert set(kinds) == {"note", "blocker", "question", "decision"}
    assert all(kinds.count(k) >= 2 for k in ("blocker", "question", "decision"))
    assert all(len(r["content"]) >= 24 and " " in r["content"] for r in rows)


def _briefs(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 12
    assert all(len(r["headline"]) >= 16 and " " in r["headline"] for r in rows)
    assert all(r["task"].startswith("b2000000-") and r["id"].startswith("d5000000-") for r in rows)
    assert {r["doc_kind"] for r in rows} >= {"brief", "acceptance", "runbook", "checklist"}


def _users(rows: list[dict[str, Any]]) -> None:
    photos = [r["photo_url"] for r in rows if r.get("photo_url")]
    assert len(photos) >= 8
    assert all(u.startswith("https://") and "placehold.co" in u for u in photos)
    assert all(r.get("name") and r.get("department") for r in rows)
    assert {r["department"] for r in rows} >= {"Engineering", "Design", "Product", "Ops"}
    # Extra ICs use non-STABLE UUIDs (a100… is reserved for personas).
    assert sum(str(r["id"]).startswith("b2000000") for r in rows) >= 2


SEED_RULES = {"TaskComment": _comments, "TaskBrief": _briefs, "User": _users}


@pytest.mark.parametrize("seed", list(SEED_RULES))
def test_seed_rows(seed: str) -> None:
    SEED_RULES[seed](_rows(seed))
