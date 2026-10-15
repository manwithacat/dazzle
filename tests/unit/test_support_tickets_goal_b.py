"""Goal B depth pins for examples/support_tickets, read from the parsed AppSpec.

Conversation, document, media, command density, org structure and empty-region
honesty on the support desks. Each kind of fact is one table read from
``load_project_appspec`` (not the DSL text): the exact ordered regions of every
desk (which carries the old order, presence and absence checks), persona focus,
region clauses, metric aggregates, entity fields, related groups, nav order and
the seed rows the desks need to fill.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir import AppSpec

APP_DIR = Path(__file__).resolve().parents[2] / "examples" / "support_tickets"
SEEDS = APP_DIR / "dsl" / "seeds" / "demo_data"

HERO_DESKS = ("ticket_queue", "manager_ops", "agent_dashboard")
MANAGER_FOCUS = [
    "media_shelf",
    "team_metrics",
    "open_stage_queue",
    "in_progress_stage_queue",
    "at_risk_queue",
    "breached_queue",
    "critical_queue",
    "unassigned_queue",
    "needs_reply",
    "live_conversation",
]


@pytest.fixture(scope="module")
def app() -> AppSpec:
    return load_project_appspec(APP_DIR)


def _ws(app: AppSpec, name: str) -> Any:
    return next(w for w in app.workspaces if w.name == name)


def _value(v: Any) -> str:
    if v is None or v.literal is None:
        return "null"
    return str(v.literal).lower() if isinstance(v.literal, bool) else str(v.literal)


def _cond(c: Any) -> str | None:
    """Render a ConditionExpr as ``field op value [and|or ...]``."""
    if c is None:
        return None
    if c.comparison is not None:
        cmp = c.comparison
        return f"{cmp.field} {cmp.operator.value} {_value(cmp.value)}"
    return f"{_cond(c.left)} {getattr(c.operator, 'value', c.operator)} {_cond(c.right)}"


def _fields_in(c: Any) -> set[str]:
    if c is None:
        return set()
    if c.comparison is not None:
        return {c.comparison.field}
    return _fields_in(c.left) | _fields_in(c.right)


def _field_sig(f: Any) -> str:
    t = f.type
    sig = t.kind.value
    if t.enum_values:
        sig = f"enum[{','.join(t.enum_values)}]"
    elif t.max_length:
        sig = f"{sig}({t.max_length})"
    if f.default is not None:
        sig += f"={str(f.default).lower() if isinstance(f.default, bool) else f.default}"
    if any(m.value == "required" for m in f.modifiers):
        sig += " required"
    return sig


REGIONS = {
    "ticket_queue": [
        ("media_shelf", "grid", "User"),
        ("queue_metrics", "summary", "Ticket"),
        ("needs_reply", "conversation", "Comment"),
        ("live_conversation", "conversation", "Comment"),
        ("composition", "queue", "SlaWaiver"),
        ("open_queue", "queue", "Ticket"),
        ("critical_now", "queue", "Ticket"),
        ("ticket_board", "kanban", "Ticket"),
        ("recent_comments", "timeline", "Comment"),
        ("queue_readiness", "status_list", None),
    ],
    "manager_ops": [
        ("media_shelf", "grid", "User"),
        ("team_metrics", "metrics", "Ticket"),
        ("open_stage_queue", "queue", "Ticket"),
        ("in_progress_stage_queue", "queue", "Ticket"),
        ("at_risk_queue", "queue", "Ticket"),
        ("breached_queue", "queue", "Ticket"),
        ("sla_readiness", "status_list", None),
        ("critical_queue", "queue", "Ticket"),
        ("unassigned_queue", "queue", "Ticket"),
        ("composition", "queue", "SlaWaiver"),
        ("needs_reply", "conversation", "Comment"),
        ("live_conversation", "conversation", "Comment"),
    ],
    "agent_dashboard": [
        ("my_assigned", "kanban", "Ticket"),
        ("needs_reply", "conversation", "Comment"),
        ("awaiting_customer", "conversation", "Comment"),
        ("my_conversation", "queue", "Comment"),
        ("pending_resolution", "queue", "Ticket"),
        ("recent_comments", "timeline", "Comment"),
    ],
    "my_tickets": [
        ("my_summary", "metrics", "Ticket"),
        ("open_cases", "queue", "Ticket"),
        ("waiting_on_us", "queue", "Ticket"),
        ("all_cases", "timeline", "Ticket"),
        ("how_it_works", "status_list", None),
    ],
    "agent_console": [
        ("agent_tickets", "queue", "Ticket"),
        ("agent_ticket_comments", "timeline", "Comment"),
        ("agent_category_chart", "bar_chart", "Ticket"),
        ("agent_comment_chart", "bar_chart", "Comment"),
        ("agent_priority_queue", "queue", "Ticket"),
        ("agent_comment_activity", "activity_feed", "Comment"),
    ],
    "people_desk": [
        ("people_pulse", "metrics", "User"),
        ("billing_staff", "queue", "User"),
        ("escalations_staff", "queue", "User"),
        ("unassigned_work", "queue", "Ticket"),
        ("l1_frontline", "queue", "User"),
        ("l3_lead", "queue", "User"),
        ("l2_escalation", "queue", "User"),
        ("by_role", "kanban", "User"),
        ("by_department", "kanban", "User"),
        ("plate_by_person", "kanban", "Ticket"),
        ("org_hint", "status_list", None),
    ],
}


@pytest.mark.parametrize("ws", REGIONS)
def test_workspace_regions(app: AppSpec, ws: str) -> None:
    regions = [(r.name, str(r.display), r.source) for r in _ws(app, ws).regions]
    assert regions == REGIONS[ws]


FOCUS = {
    "ticket_queue": {
        p: ["media_shelf", "queue_metrics", "needs_reply", "live_conversation"]
        for p in ("agent", "manager", "admin")
    },
    "manager_ops": {"manager": MANAGER_FOCUS},
    "agent_dashboard": {
        p: ["my_assigned", "needs_reply", "awaiting_customer", "pending_resolution"]
        for p in ("agent", "manager")
    },
    "my_tickets": {
        "customer": ["my_summary", "open_cases", "waiting_on_us", "all_cases", "how_it_works"]
    },
    "agent_console": {
        p: ["agent_priority_queue", "agent_ticket_comments", "agent_category_chart"]
        for p in ("manager", "agent", "admin")
    },
    "people_desk": {
        p: ["people_pulse", "billing_staff", "escalations_staff", "unassigned_work"]
        for p in ("manager", "agent")
    },
}


@pytest.mark.parametrize("ws", FOCUS)
def test_persona_focus(app: AppSpec, ws: str) -> None:
    variants = _ws(app, ws).ux.persona_variants
    assert {v.persona: v.focus for v in variants} == FOCUS[ws]


# (workspace, region, filter, limit, extra attrs)
CLAUSES = [
    ("ticket_queue", "media_shelf", "is_active = true and department != null", 4, {}),
    ("ticket_queue", "needs_reply", "ball_in_court = agent and is_internal = false", 8, {}),
    ("ticket_queue", "live_conversation", None, 10, {}),
    ("manager_ops", "media_shelf", "is_active = true and department != null", 3, {}),
    ("manager_ops", "open_stage_queue", "status = open", 4, {}),
    ("manager_ops", "in_progress_stage_queue", "status = in_progress", 4, {}),
    ("manager_ops", "at_risk_queue", "sla_state = at_risk and status != closed", 4, {}),
    ("manager_ops", "breached_queue", "sla_state = breached and status != closed", 4, {}),
    ("manager_ops", "critical_queue", "priority = critical and status != closed", 4, {}),
    ("manager_ops", "unassigned_queue", "assigned_to = null and status = open", 4, {}),
    ("manager_ops", "composition", "status = draft or status = sent", 4, {}),
    ("manager_ops", "needs_reply", "ball_in_court = agent and is_internal = false", 4, {}),
    ("manager_ops", "live_conversation", None, 4, {}),
    ("agent_dashboard", "needs_reply", "ball_in_court = agent and is_internal = false", 8, {}),
    ("people_desk", "billing_staff", "is_active = true and department = Billing", 3, {}),
    ("people_desk", "escalations_staff", "is_active = true and department = Escalations", 3, {}),
    (
        "people_desk",
        "l1_frontline",
        "is_active = true and support_tier = l1 and department != External",
        3,
        {},
    ),
    (
        "people_desk",
        "l2_escalation",
        "is_active = true and support_tier = l2 and department != External",
        3,
        {},
    ),
    (
        "people_desk",
        "l3_lead",
        "is_active = true and support_tier = l3 and department != External",
        3,
        {},
    ),
    (
        "people_desk",
        "by_department",
        "is_active = true and department != External",
        24,
        {"group_by": "department"},
    ),
]


@pytest.mark.parametrize(
    ("ws", "region", "filter_", "limit", "extra"),
    CLAUSES,
    ids=[f"{w}-{r}" for w, r, *_ in CLAUSES],
)
def test_region_clauses(
    app: AppSpec, ws: str, region: str, filter_: str | None, limit: int, extra: dict[str, str]
) -> None:
    r = next(x for x in _ws(app, ws).regions if x.name == region)
    assert (_cond(r.filter), r.limit) == (filter_, limit)
    for attr, expected in extra.items():
        assert getattr(r, attr) == expected
    if r.name == "media_shelf":
        assert [(s.field, s.direction) for s in r.sort] == [("created_at", "desc")]


METRICS = [
    ("ticket_queue", "queue_metrics", "conversation", "Comment", None),
    ("ticket_queue", "queue_metrics", "needs_reply", "Comment", "ball_in_court = agent"),
    ("ticket_queue", "queue_metrics", "documents", "SlaWaiver", None),
    (
        "manager_ops",
        "team_metrics",
        "critical_open",
        "Ticket",
        "priority = critical and status != closed",
    ),
    ("manager_ops", "team_metrics", "unassigned", "Ticket", "assigned_to = null and status = open"),
    (
        "manager_ops",
        "team_metrics",
        "at_risk",
        "Ticket",
        "sla_state = at_risk and status != closed",
    ),
    (
        "manager_ops",
        "team_metrics",
        "breached",
        "Ticket",
        "sla_state = breached and status != closed",
    ),
    ("manager_ops", "team_metrics", "conversation", "Comment", None),
    ("manager_ops", "team_metrics", "documents", "SlaWaiver", None),
    (
        "people_desk",
        "people_pulse",
        "l1",
        "User",
        "is_active = true and support_tier = l1 and department != External",
    ),
    (
        "people_desk",
        "people_pulse",
        "l2",
        "User",
        "is_active = true and support_tier = l2 and department != External",
    ),
    (
        "people_desk",
        "people_pulse",
        "l3",
        "User",
        "is_active = true and support_tier = l3 and department != External",
    ),
]


@pytest.mark.parametrize(
    ("ws", "region", "key", "entity", "where"),
    METRICS,
    ids=[f"{w}-{k}" for w, _r, k, *_ in METRICS],
)
def test_metric_aggregates(
    app: AppSpec, ws: str, region: str, key: str, entity: str, where: str | None
) -> None:
    agg = next(x for x in _ws(app, ws).regions if x.name == region).aggregates[key]
    assert (agg.func, agg.entity, _cond(agg.where)) == ("count", entity, where)


@pytest.mark.parametrize("ws", HERO_DESKS)
def test_hero_desks_have_no_cartesian_conversation_slices(app: AppSpec, ws: str) -> None:
    """Goal C: no region or metric filter keys on the speech coat enums."""
    coat = {"sla_pressure", "case_priority", "customer_tone", "channel", "escalation"}
    used: set[str] = set()
    for r in _ws(app, ws).regions:
        used |= _fields_in(r.filter)
        for agg in (r.aggregates or {}).values():
            used |= _fields_in(agg.where)
    assert not used & coat


def test_agent_console_selector_lists_agents_only(app: AppSpec) -> None:
    cs = _ws(app, "agent_console").context_selector
    assert (cs.entity, _cond(cs.filter)) == ("User", "support_tier = l1 and department != External")


ENTITIES = {
    "User": (
        "name",
        ["name", "role", "department", "support_tier"],
        {"department": "str(50)", "support_tier": "enum[l1,l2,l3]=l1", "photo_url": "url"},
    ),
    "Ticket": (
        "title",
        ["ticket_number", "title", "status", "priority", "sla_state", "category", "assigned_to"],
        {"sla_state": "enum[on_track,at_risk,breached]=on_track"},
    ),
    "Comment": (
        "content",
        [
            "ticket",
            "author",
            "content",
            "customer_tone",
            "channel",
            "escalation",
            "ball_in_court",
            "sla_pressure",
            "case_priority",
            "is_internal",
        ],
        {
            "content": "text required",
            "customer_tone": "enum[neutral,frustrated,urgent,thankful]=neutral",
            "channel": "enum[portal,email,chat,phone]=portal",
            "escalation": "enum[none,raised,critical]=none",
            "ball_in_court": "enum[agent,customer,none]=none",
            "case_priority": "enum[low,medium,high,critical]=medium",
        },
    ),
    "SlaWaiver": (
        "breach_summary",
        ["ticket", "breach_summary", "signatory_name", "status"],
        {"breach_summary": "text required", "status": "enum[draft,sent,signed,void]=draft"},
    ),
}


@pytest.mark.parametrize("entity", ENTITIES)
def test_entity_shape(app: AppSpec, entity: str) -> None:
    display_field, repr_fields, fields = ENTITIES[entity]
    e = next(x for x in app.domain.entities if x.name == entity)
    assert (e.display_field, e.fitness.repr_fields) == (display_field, repr_fields)
    sigs = {f.name: _field_sig(f) for f in e.fields}
    assert {k: sigs.get(k) for k in fields} == fields
    assert e.signable == (entity == "SlaWaiver")


RELATED = [
    (
        "ticket_detail",
        "discussion",
        "conversation",
        ["Comment"],
        [
            "content",
            "author",
            "customer_tone",
            "channel",
            "escalation",
            "ball_in_court",
            "sla_pressure",
            "case_priority",
            "created_at",
            "is_internal",
        ],
    ),
    (
        "ticket_detail",
        "waivers",
        "queue",
        ["SlaWaiver"],
        ["breach_summary", "status", "signatory_name"],
    ),
    (
        "user_detail",
        "comments",
        "conversation",
        ["Comment"],
        [
            "content",
            "customer_tone",
            "channel",
            "escalation",
            "ball_in_court",
            "sla_pressure",
            "case_priority",
            "is_internal",
            "created_at",
        ],
    ),
]


@pytest.mark.parametrize(
    ("surface", "group", "display", "show", "columns"),
    RELATED,
    ids=[f"{s}-{g}" for s, g, *_ in RELATED],
)
def test_related_groups(
    app: AppSpec, surface: str, group: str, display: str, show: list[str], columns: list[str]
) -> None:
    s = next(x for x in app.surfaces if x.name == surface)
    g = next(x for x in s.related_groups if x.name == group)
    assert (g.display.value, g.show, g.columns) == (display, show, columns)


def test_sla_waiver_list_dual_open(app: AppSpec) -> None:
    names = {s.name for s in app.surfaces}
    assert {"sla_waiver_list", "sla_waiver_detail"} <= names
    s = next(x for x in app.surfaces if x.name == "sla_waiver_list")
    assert [(t.via, t.entity) for t in s.open_via_targets] == [
        ("id", "SlaWaiver"),
        ("ticket", "Ticket"),
    ]


def test_manager_nav_puts_people_desk_after_ops(app: AppSpec) -> None:
    nav = next(n for n in app.navs if n.name == "manager_nav")
    items = [i.entity for g in nav.groups for i in g.items]
    assert items == [
        "manager_ops",
        "people_desk",
        "ticket_queue",
        "agent_console",
        "agent_dashboard",
    ]


def _rows(name: str) -> list[dict[str, Any]]:
    text = (SEEDS / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _tickets(rows: list[dict[str, Any]]) -> None:
    live = [r for r in rows if r.get("status") != "closed"]
    assert {r.get("sla_state") for r in rows} >= {"on_track", "at_risk", "breached"}
    assert sum(r.get("sla_state") in ("at_risk", "breached") for r in live) >= 3
    assert any(r.get("sla_state") == "at_risk" for r in live)
    assert any(r.get("sla_state") == "breached" for r in live)
    assert {r.get("status") for r in rows} >= {"open", "in_progress"}


def _comments(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 10
    for row in rows:
        assert len(str(row.get("content") or "")) >= 24 and " " in row["content"], row
        assert (row.get("customer_tone") or "neutral") in {
            "neutral",
            "frustrated",
            "urgent",
            "thankful",
        }
        assert (row.get("channel") or "portal") in {"portal", "email", "chat", "phone"}
        assert (row.get("escalation") or "none") in {"none", "raised", "critical"}
        assert (row.get("ball_in_court") or "none") in {"agent", "customer", "none"}
    assert {r.get("customer_tone") for r in rows} & {"frustrated", "urgent"}
    assert {r.get("channel") or "portal" for r in rows} - {"portal"}
    assert {r.get("escalation") for r in rows} & {"raised", "critical"}
    assert {r.get("ball_in_court") for r in rows} >= {"agent", "customer"}
    assert (
        sum(r.get("ball_in_court") == "agent" and r.get("is_internal") is False for r in rows) >= 3
    )


def _waivers(rows: list[dict[str, Any]]) -> None:
    assert len(rows) >= 12
    for row in rows:
        assert len(row["breach_summary"]) >= 16 and " " in row["breach_summary"], row
        assert str(row["ticket"]).startswith("c3000000-")
        assert str(row["id"]).startswith("e8000000-")
        assert len(str(row["waiver_terms"])) >= 24
    assert {r["status"] for r in rows} >= {"draft", "sent", "signed"}


def _users(rows: list[dict[str, Any]]) -> None:
    photos = [str(r["photo_url"]) for r in rows if r.get("photo_url")]
    assert len(photos) >= 6
    assert all(u.startswith("https://") and "placehold.co" in u for u in photos), photos
    staff = [r for r in rows if r.get("role") in ("agent", "manager")]
    assert len(staff) >= 5
    assert all(r.get("name") and r.get("department") for r in staff)
    assert {r["department"] for r in staff} >= {"Support", "Escalations", "Billing"}
    tiers = [r.get("support_tier") for r in staff]
    assert set(tiers) == {"l1", "l2", "l3"}
    assert tiers.count("l1") >= 3 and tiers.count("l2") >= 2 and tiers.count("l3") >= 1


SEED_RULES: dict[str, Callable[[list[dict[str, Any]]], None]] = {
    "Ticket": _tickets,
    "Comment": _comments,
    "SlaWaiver": _waivers,
    "User": _users,
}


@pytest.mark.parametrize("seed", SEED_RULES)
def test_seed_rows(seed: str) -> None:
    SEED_RULES[seed](_rows(seed))
