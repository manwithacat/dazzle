"""Goal B depth pins for examples/hr_records, read from the parsed AppSpec.

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

APP_ROOT = Path(__file__).resolve().parents[2] / "examples" / "hr_records"
DSL_SEEDS = APP_ROOT / "dsl" / "seeds" / "demo_data"
DEMO_DATA = APP_ROOT / "demo_data"


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
        "limit": region.limit,
        "group_by": region.group_by,
        "action": region.action,
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
    # Roster leads; onboarding lives on New Starters; shelf after the notes trail.
    "staff_directory": [
        ("current_staff", "queue", "Person"),
        ("headcount", "metrics", "Person"),
        ("composition", "queue", "HrDocument"),
        ("live_conversation", "queue", "PersonNote"),
        ("media_shelf", "grid", "Person"),
        ("department_context", "queue", "Department"),
        ("role_context", "queue", "Role"),
        ("directory_readiness", "status_list", None),
    ],
    # In-tree vs apex people, career tracks, office/remote, kanban org boards.
    "my_team": [
        ("team_pulse", "metrics", "Person"),
        ("career_pulse", "metrics", "Role"),
        ("in_tree", "queue", "Person"),
        ("apex_people", "queue", "Person"),
        ("ic_track", "queue", "Role"),
        ("manager_track", "queue", "Role"),
        ("office_sites", "queue", "Person"),
        ("remote_flex", "queue", "Person"),
        ("by_level", "kanban", "Role"),
        ("by_department", "kanban", "Employment"),
        ("by_location", "kanban", "Person"),
        ("reporting_lines", "queue", "ManagerLink"),
        ("composition", "queue", "HrDocument"),
        ("live_conversation", "queue", "PersonNote"),
        ("reports", "queue", "Person"),
        ("team_readiness", "status_list", None),
    ],
    "starters_desk": [
        ("starter_pulse", "metrics", "Person"),
        ("recent_people", "queue", "Person"),
        ("employment_trail", "timeline", "Employment"),
        ("salary_mix", "bar_chart", "Salary"),
    ],
    "active_staff": [
        ("headcount_pulse", "metrics", "Person"),
        ("active_queue", "queue", "Person"),
        ("hire_trail", "timeline", "Person"),
        ("level_mix", "bar_chart", "Role"),
    ],
    # Unassigned vs top-of-house seats, then a filled span queue (not an empty kanban).
    "reporting_desk": [
        ("reporting_pulse", "metrics", "ManagerLink"),
        ("unassigned", "queue", "Person"),
        ("top_of_house", "queue", "Person"),
        ("span_of_control", "queue", "ManagerLink"),
        ("by_department", "kanban", "Employment"),
        ("by_location", "kanban", "Person"),
        ("link_trail", "timeline", "ManagerLink"),
        ("org_readiness", "status_list", None),
    ],
    # One employment timeline (the employment_trail twin was pruned).
    "career_desk": [
        ("career_pulse", "metrics", "Employment"),
        ("employment_history", "timeline", "Employment"),
        ("salary_history", "timeline", "Salary"),
        ("reporting_history", "timeline", "ManagerLink"),
        ("org_context", "queue", "Department"),
        ("record_hint", "status_list", None),
        ("salary_mix", "bar_chart", "Salary"),
    ],
}


@pytest.mark.parametrize("ws", list(WORKSPACE_REGIONS))
def test_workspace_regions(appspec: Any, ws: str) -> None:
    regions = [(r.name, str(r.display), r.source) for r in _workspace(appspec, ws).regions]
    assert regions == WORKSPACE_REGIONS[ws]


# (b) Distinct focus lists across each desk's persona variants.
FOCUS = {
    "staff_directory": {("current_staff", "headcount", "composition")},
    "my_team": {("in_tree", "apex_people", "reporting_lines", "career_pulse")},
    "starters_desk": {("starter_pulse", "recent_people", "employment_trail")},
    "active_staff": {("headcount_pulse", "active_queue", "hire_trail")},
    "reporting_desk": {
        ("reporting_pulse", "unassigned", "top_of_house", "span_of_control"),
        ("reporting_pulse", "span_of_control"),
    },
    "career_desk": {("career_pulse", "employment_history", "salary_history", "reporting_history")},
}


@pytest.mark.parametrize("ws", list(FOCUS))
def test_workspace_focus(appspec: Any, ws: str) -> None:
    variants = _workspace(appspec, ws).ux.persona_variants
    assert {tuple(v.focus) for v in variants} == FOCUS[ws]


# (c) Region clauses that carry each depth.
_OFFICE = (
    "ended_at = null and (work_location = london_hq or work_location = manchester "
    "or work_location = client_site)"
)
_REMOTE = "ended_at = null and (work_location = remote_uk or work_location = hybrid)"
_SEAT = "ended_at = null and reporting_seat = "
REGION_CLAUSES = [
    ("staff_directory", "current_staff", {"filter": "ended_at = null", "limit": 4}),
    ("staff_directory", "media_shelf", {"limit": 8}),
    ("my_team", "in_tree", {"filter": _SEAT + "has_manager", "action": "person_detail"}),
    ("my_team", "apex_people", {"filter": _SEAT + "top_of_house"}),
    ("my_team", "office_sites", {"filter": _OFFICE, "limit": 4}),
    ("my_team", "remote_flex", {"filter": _REMOTE, "limit": 4}),
    ("my_team", "by_level", {"group_by": "level"}),
    ("my_team", "by_department", {"group_by": "department", "filter": "end_date = null"}),
    ("my_team", "by_location", {"group_by": "work_location"}),
    ("my_team", "reporting_lines", {"limit": 4, "action": "managerlink_detail"}),
    ("reporting_desk", "unassigned", {"filter": _SEAT + "unassigned", "action": "person_detail"}),
    ("reporting_desk", "top_of_house", {"filter": _SEAT + "top_of_house"}),
    (
        "reporting_desk",
        "span_of_control",
        {"filter": "end_date = null", "group_by": None, "action": "managerlink_detail"},
    ),
    ("reporting_desk", "by_department", {"group_by": "department"}),
    ("reporting_desk", "by_location", {"group_by": "work_location"}),
]
# Metric keys that carry a depth (subset of each region's aggregates).
METRICS = [
    (
        "staff_directory",
        "headcount",
        {"documents": "count(HrDocument)", "conversation": "count(PersonNote)"},
    ),
    (
        "my_team",
        "team_pulse",
        {
            "documents": "count(HrDocument)",
            "conversation": "count(PersonNote)",
            "office_sites": f"count(Person where {_OFFICE})",
            "remote_flex": f"count(Person where {_REMOTE})",
        },
    ),
    (
        "my_team",
        "career_pulse",
        {
            "ic_roles": "count(Role where level = ic1 or level = ic2 or level = ic3 "
            "or level = ic4 or level = ic5 or level = ic6)",
            "manager_roles": "count(Role where level = m1 or level = m2 or level = m3 or level = m4)",
        },
    ),
    (
        "reporting_desk",
        "reporting_pulse",
        {
            "unassigned": "count(Person where reporting_seat = unassigned and ended_at = null)",
            "top_of_house": "count(Person where reporting_seat = top_of_house and ended_at = null)",
        },
    ),
]


def _region(appspec: Any, ws: str, name: str) -> dict[str, Any]:
    return _region_facts(next(r for r in _workspace(appspec, ws).regions if r.name == name))


@pytest.mark.parametrize(
    ("ws", "region", "expected"),
    REGION_CLAUSES,
    ids=[f"{ws}.{region}" for ws, region, _ in REGION_CLAUSES],
)
def test_region_clauses(appspec: Any, ws: str, region: str, expected: dict[str, Any]) -> None:
    facts = _region(appspec, ws, region)
    assert {key: facts[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("ws", "region", "expected"),
    METRICS,
    ids=[f"{ws}.{region}" for ws, region, _ in METRICS],
)
def test_metric_aggregates(appspec: Any, ws: str, region: str, expected: dict[str, str]) -> None:
    aggregates = _region(appspec, ws, region)["aggregates"]
    assert {key: aggregates.get(key) for key in expected} == expected


def test_bar_charts_live_on_secondary_desks(appspec: Any) -> None:
    """The hero prunes keep bar_chart covered on the secondary desks."""
    charts = {
        (ws.name, r.name)
        for ws in appspec.workspaces
        for r in ws.regions
        if str(r.display) == "bar_chart"
    }
    assert len(charts) >= 4
    assert {("org_chart", "role_level_mix"), ("compensation_review", "reason_mix")} <= charts


# (d) Entity shape: title, display field, card repr and the depth-bearing fields.
ENTITIES = {
    # Identity chips, not a schema dump: email / photo_url stay off cards.
    "Person": (
        "Person",
        "legal_name",
        ["legal_name", "preferred_name", "work_location", "reporting_seat", "started_at"],
        {
            "photo_url": "url",
            "work_location": "enum[london_hq,manchester,remote_uk,hybrid,client_site]=london_hq",
            "reporting_seat": "enum[has_manager,unassigned,top_of_house]=unassigned",
        },
    ),
    "PersonNote": ("Person Note", "body", ["person", "author", "body"], {"body": "text required"}),
    "HrDocument": (
        "HR Document",
        "headline",
        ["person", "headline", "doc_kind", "status", "author"],
        {
            "headline": "str(200) required",
            "doc_kind": "enum[offer,policy,promo,contract,onboarding]=offer",
            "status": "enum[draft,issued,signed,archived]=draft",
        },
    ),
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


def test_hr_document_lifecycle(appspec: Any) -> None:
    entity = next(e for e in appspec.domain.entities if e.name == "HrDocument")
    moves = {(t.from_state, t.to_state) for t in entity.state_machine.transitions}
    assert {("draft", "issued"), ("issued", "signed"), ("signed", "archived")} <= moves


# (e) Surfaces: person hub discussion is conversation chrome; documents open two ways.
def test_person_detail_related_groups(appspec: Any) -> None:
    detail = next(s for s in appspec.surfaces if s.name == "person_detail")
    groups = {g.name: (str(g.display), g.show, g.columns) for g in detail.related_groups}
    assert groups["discussion"] == (
        "conversation",
        ["PersonNote"],
        ["body", "author", "created_at"],
    )
    assert groups["documents"][:2] == ("queue", ["HrDocument"])


def test_hr_document_surfaces_dual_open(appspec: Any) -> None:
    surfaces = {s.name: s for s in appspec.surfaces}
    titles = (surfaces["hr_document_list"].title, surfaces["hr_document_detail"].title)
    assert titles == ("HR Documents", "HR Document")
    targets = [(t.via, t.entity) for t in surfaces["hr_document_list"].open_via_targets]
    assert targets == [("id", "HrDocument"), ("person", "Person")]


@pytest.mark.parametrize(
    ("field", "label"), [("work_location", "Work location"), ("reporting_seat", "Reporting seat")]
)
def test_person_surfaces_expose_org_place(appspec: Any, field: str, label: str) -> None:
    carrying = {
        s.name
        for s in appspec.surfaces
        for sec in s.sections
        for el in sec.elements
        if el.field_name == field and el.label == label
    }
    assert carrying >= {"person_list", "person_detail", "person_create", "person_edit"}


# (f) Demo seeds carry domain-true copy for each depth.
def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _notes(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 10
    assert all(len(r["body"]) >= 24 and " " in r["body"] for r in rows)


def _documents(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 12
    assert all(len(r["headline"]) >= 16 and " " in r["headline"] for r in rows)
    assert all(r["person"] and r["id"].startswith("c2000000-") for r in rows)
    assert all(len(r.get("body") or "") >= 24 for r in rows)
    assert {r["doc_kind"] for r in rows} >= {"offer", "policy", "promo", "contract", "onboarding"}
    assert {r["status"] for r in rows} >= {"draft", "issued", "signed"}


def _people(rows: list[dict[str, Any]]) -> None:
    photos = [r["photo_url"] for r in rows if r.get("photo_url")]
    assert len(photos) >= 8 and all(u.startswith("https://") for u in photos)
    locations = [r.get("work_location") for r in rows]
    assert all(locations) and set(locations) >= {"london_hq", "remote_uk", "hybrid"}
    assert len(set(locations)) >= 4
    seats = [r.get("reporting_seat") for r in rows]
    assert seats.count("has_manager") >= 4 and seats.count("unassigned") >= 4
    assert seats.count("top_of_house") >= 1


def _roles(rows: list[dict[str, Any]]) -> None:
    levels = [str(r.get("level", "")) for r in rows]
    assert sum(lv.startswith("ic") for lv in levels) >= 3
    assert sum(lv.startswith("m") for lv in levels) >= 2


SEED_RULES = {
    "PersonNote": (DEMO_DATA / "PersonNote.jsonl", _notes),
    "HrDocument": (DEMO_DATA / "HrDocument.jsonl", _documents),
    "Person": (DSL_SEEDS / "Person.jsonl", _people),
    "Role": (DSL_SEEDS / "Role.jsonl", _roles),
}


@pytest.mark.parametrize("seed", list(SEED_RULES))
def test_seed_rows(seed: str) -> None:
    path, rule = SEED_RULES[seed]
    rule(_rows(path))
