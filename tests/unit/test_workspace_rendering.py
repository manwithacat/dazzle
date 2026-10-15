"""Tests for workspace region rendering — column types, filters, attention, timeago.

Covers:
- _field_kind_to_col_type: correct mapping from IR field → column type
- Filterable columns: enum, bool, state-machine status
- timeago Jinja2 filter
- Attention row highlighting
- Ref/UUID column hiding
- Cross-entity action URL resolution
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core import ir
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(
    name: str,
    kind: FieldTypeKind,
    *,
    enum_values: list[str] | None = None,
    ref_entity: str | None = None,
    label: str | None = None,
) -> FieldSpec:
    """Create a minimal FieldSpec for testing."""
    ft = FieldType(kind=kind, enum_values=enum_values, ref_entity=ref_entity)
    return FieldSpec(name=name, type=ft, label=label)


def _make_entity(
    name: str,
    fields: list[FieldSpec],
    *,
    state_machine: Any = None,
) -> SimpleNamespace:
    """Create a minimal EntitySpec-like object."""
    return SimpleNamespace(name=name, fields=fields, state_machine=state_machine)


_ID = _make_field("id", FieldTypeKind.UUID)


# ===========================================================================
# Column types
# ===========================================================================


class TestFieldKindToColType:
    """_field_kind_to_col_type() maps IR fields to column rendering types."""

    @pytest.mark.parametrize(
        ("field_name", "kind", "enum_values", "expected"),
        [
            ("status", FieldTypeKind.ENUM, ["open", "closed"], "badge"),
            ("completed", FieldTypeKind.BOOL, None, "bool"),
            ("created_at", FieldTypeKind.DATE, None, "date"),
            # datetime stays distinct so list cells can show time (#UK date/time
            # humanisation — collapsing to "date" stripped assignment timestamps).
            ("updated_at", FieldTypeKind.DATETIME, None, "datetime"),
            ("amount", FieldTypeKind.MONEY, None, "currency"),
            ("title", FieldTypeKind.STR, None, "text"),
            ("file", FieldTypeKind.FILE, None, "file"),
        ],
        ids=["enum_badge", "bool", "date", "datetime_col", "money_currency", "str_text", "file"],
    )
    def test_kind_mapping(self, field_name, kind, enum_values, expected) -> None:
        from dazzle.http.runtime.server import _field_kind_to_col_type

        f = _make_field(field_name, kind, enum_values=enum_values)
        assert _field_kind_to_col_type(f) == expected

    @pytest.mark.parametrize(
        ("field_name", "expected"),
        [
            ("status", "badge"),  # state_machine.status_field → badge
            ("title", "text"),  # not the status field → text
        ],
        ids=["status_field_badge", "non_status_field_text"],
    )
    def test_state_machine_dispatch(self, field_name, expected) -> None:
        from dazzle.http.runtime.server import _field_kind_to_col_type

        f = _make_field(field_name, FieldTypeKind.STR)
        sm = SimpleNamespace(status_field="status", states=["open", "closed"])
        entity = _make_entity("Task", [f], state_machine=sm)
        assert _field_kind_to_col_type(f, entity) == expected


@pytest.mark.parametrize(
    ("field_factory", "name"),
    [
        pytest.param(
            lambda: ir.FieldSpec(
                name="assigned_at", type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME)
            ),
            "assigned_at",
            id="datetime_kind-1597",
        ),
        pytest.param(lambda: None, "created_at", id="injected_created_at-1597"),
        pytest.param(lambda: None, "updated_at", id="injected_updated_at-1597"),
    ],
)
def test_ssr_column_type_is_datetime_not_date_1597(field_factory, name) -> None:
    """SSR template_compiler mapper must match HTMX datetime vocabulary (#1597)."""
    from dazzle.page.converters.template_compiler import _field_type_to_column_type

    assert _field_type_to_column_type(field_factory(), name) == "datetime"


# ===========================================================================
# Filterable / ref / hidden columns (public path: build_entity_columns_full)
# ===========================================================================


def _entity_columns(entity: SimpleNamespace) -> list[dict[str, Any]]:
    from dazzle.http.runtime.workspace_columns import build_entity_columns_full

    return build_entity_columns_full(entity)


_STATUS_SM = SimpleNamespace(status_field="status", states=["draft", "active", "done"])


@pytest.mark.parametrize(
    ("field", "state_machine", "tokens"),
    [
        pytest.param(
            _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "closed", "pending"]),
            None,
            ["open", "closed", "pending"],
            id="enum_with_values",
        ),
        pytest.param(
            _make_field("completed", FieldTypeKind.BOOL), None, ["true", "false"], id="bool"
        ),
        pytest.param(_make_field("title", FieldTypeKind.STR), None, None, id="str_not_filterable"),
        pytest.param(
            _make_field("status", FieldTypeKind.STR),
            _STATUS_SM,
            ["draft", "active", "done"],
            id="state_machine_status",
        ),
    ],
)
def test_filterable_columns(field, state_machine, tokens) -> None:
    """Columns are filterable when enum/bool/state-machine status; plain str is not."""
    (col,) = _entity_columns(_make_entity("Task", [field], state_machine=state_machine))
    if tokens is None:
        assert "filterable" not in col
        return
    assert col["filterable"] is True
    assert [opt[0] for opt in col["filter_options"]] == tokens


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param(
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
            ],
            [("title", "text"), ("customer", "ref")],
            id="ref_shown_as_ref-553",
        ),
        pytest.param(
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("order_id", FieldTypeKind.BELONGS_TO, ref_entity="Order"),
            ],
            [("title", "text"), ("order", "ref")],  # _id suffix stripped
            id="belongs_to_shown_as_ref-553",
        ),
        pytest.param(
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("external_id", FieldTypeKind.UUID),
            ],
            [("title", "text")],
            id="uuid_hidden",
        ),
        pytest.param(
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
            ],
            [("title", "text")],
            id="has_many_hidden",
        ),
        pytest.param(
            [_ID, _make_field("title", FieldTypeKind.STR)],
            [("title", "text")],
            id="id_hidden",
        ),
        pytest.param(
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("customer_id", FieldTypeKind.STR),
            ],
            [("title", "text")],
            id="fk_suffix_str_hidden",
        ),
    ],
)
def test_ref_and_hidden_columns(fields, expected) -> None:
    """Ref/belongs_to show as ref columns; uuid, has_many, id and *_id strs are hidden."""
    cols = _entity_columns(_make_entity("Order", fields))
    assert [(c["key"], c["type"]) for c in cols] == expected


# ===========================================================================
# timeago filter
# ===========================================================================


def _ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def _ahead(**delta: float) -> datetime:
    return datetime.now(UTC) + timedelta(**delta)


def _calendar(days: int) -> Any:
    from dazzle.i18n.display_locale import calendar_today

    return calendar_today() + timedelta(days=days)


@pytest.mark.parametrize(
    ("make_input", "expected"),
    [
        pytest.param(lambda: _ago(seconds=30), "30 seconds ago", id="seconds_ago"),
        pytest.param(lambda: _ago(hours=3), "3 hours ago", id="hours_ago"),
        pytest.param(lambda: _ago(days=5), "5 days ago", id="days_ago"),
        pytest.param(lambda: _ago(minutes=10).isoformat(), "10 minutes ago", id="iso_string"),
        pytest.param(lambda: "not-a-date", "not-a-date", id="invalid_returns_original"),
        pytest.param(lambda: None, "", id="none_returns_empty"),
        # Leftover junk stays put.
        pytest.param(lambda: "zzz", "zzz", id="leftover_zzz"),
        pytest.param(lambda: "ghost", "ghost", id="leftover_ghost"),
        pytest.param(lambda: "12abc", "12abc", id="leftover_12abc"),
        # Calendar due dates must not invent 'just now' (oral #123).
        pytest.param(lambda: _calendar(1), "tomorrow", id="due_tomorrow-123"),
        pytest.param(lambda: _calendar(5), "in 5 days", id="due_in_5_days-123"),
        pytest.param(lambda: _calendar(1).isoformat(), "tomorrow", id="due_tomorrow_iso-123"),
        pytest.param(lambda: _calendar(0), "today", id="due_today"),
        pytest.param(lambda: _calendar(-1), "yesterday", id="due_yesterday"),
        # Pad the delta so integer-second flooring cannot drop a bucket.
        pytest.param(lambda: _ahead(hours=3, minutes=5), "in 3 hours", id="future_hours"),
        pytest.param(lambda: _ahead(minutes=10, seconds=5), "in 10 minutes", id="future_minutes"),
        # Naive datetimes are UTC storage — wall datetime.now() must not invent
        # elapsed time by the TZ offset (oral #124).
        pytest.param(lambda: _ago(minutes=30, seconds=5), "30 minutes ago", id="aware-124"),
        pytest.param(
            lambda: _ago(minutes=30, seconds=5).replace(tzinfo=None),
            "30 minutes ago",
            id="naive_utc-124",
        ),
        pytest.param(
            lambda: _ago(minutes=30, seconds=5).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "30 minutes ago",
            id="zulu_string-124",
        ),
    ],
)
def test_timeago_filter(make_input, expected) -> None:
    from dazzle.render.filters import _timeago_filter

    assert _timeago_filter(make_input()) == expected


# ===========================================================================
# Attention highlighting
# ===========================================================================


def _signal(level: str, field: str, operator: str, value: str, message: str) -> Any:
    from dazzle.core.ir.conditions import Comparison, ConditionExpr, ConditionValue
    from dazzle.core.ir.ux import AttentionSignal, SignalLevel

    cond = ConditionExpr(
        comparison=Comparison(field=field, operator=operator, value=ConditionValue(literal=value))
    )
    return AttentionSignal(level=SignalLevel(level), condition=cond, message=message)


def _overdue_status() -> Any:
    return _signal("warning", "status", "=", "overdue", "Task is overdue")


def _high_priority() -> Any:
    return _signal("critical", "priority", "=", "high", "High priority")


def _due_before_today() -> Any:
    from dazzle.core.ir.conditions import Comparison, ConditionExpr, ConditionValue
    from dazzle.core.ir.dates import DateLiteral, DateLiteralKind
    from dazzle.core.ir.ux import AttentionSignal, SignalLevel

    cond = ConditionExpr(
        comparison=Comparison(
            field="due_date",
            operator="<",
            value=ConditionValue(date_expr=DateLiteral(kind=DateLiteralKind.TODAY)),
        )
    )
    return AttentionSignal(level=SignalLevel.WARNING, condition=cond, message="Overdue task")


@pytest.mark.parametrize(
    ("make_signals", "make_item", "expected"),
    [
        pytest.param(
            lambda: [_overdue_status()],
            lambda: {"status": "overdue", "title": "Fix bug"},
            {"level": "warning", "message": "Task is overdue"},
            id="warning_matches",
        ),
        pytest.param(
            lambda: [_overdue_status()],
            lambda: {"status": "active", "title": "Fix bug"},
            None,
            id="no_match",
        ),
        pytest.param(
            lambda: [_overdue_status(), _high_priority()],
            lambda: {"status": "overdue", "priority": "high"},
            {"level": "critical", "message": "High priority"},
            id="highest_severity_wins",
        ),
        pytest.param(
            lambda: [_due_before_today()],
            lambda: {"due_date": _calendar(-1), "status": "todo"},
            {"level": "warning", "message": "Overdue task"},
            id="past_due_date_fires",
        ),
        pytest.param(
            lambda: [_due_before_today()],
            lambda: {"due_date": _calendar(1)},
            None,
            id="future_due_date_quiet",
        ),
    ],
)
def test_attention_signals(make_signals, make_item, expected) -> None:
    """apply_attention_signals annotates a row with the most severe matching signal."""
    from dazzle.http.runtime.workspace_region_computes import apply_attention_signals

    items = [make_item()]
    apply_attention_signals(items, make_signals(), {})
    assert items[0].get("_attention") == expected


# ===========================================================================
# Cross-entity action URL resolution
# ===========================================================================


@pytest.mark.parametrize(
    ("source", "action", "surface_entity", "source_fields", "expected_url", "expected_id_field"),
    [
        pytest.param("Task", "task_edit", "Task", None, "/app/task/{id}", "id", id="same_entity"),
        pytest.param(
            "Order",
            "customer_detail",
            "Customer",
            [
                _make_field("title", FieldTypeKind.STR),
                _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
            ],
            "/app/customer/{id}",
            "customer",
            id="cross_entity_fk_field",
        ),
        pytest.param(
            "Order",
            "customer_detail",
            "Customer",
            [_make_field("title", FieldTypeKind.STR)],
            "/app/customer/{id}",
            "id",
            id="cross_entity_fallback_to_id",
        ),
    ],
)
def test_action_url_resolution(
    source, action, surface_entity, source_fields, expected_url, expected_id_field
) -> None:
    from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
    from dazzle.page.runtime.workspace_renderer import build_workspace_context

    entities = [SimpleNamespace(name=source, fields=source_fields)] if source_fields else []
    app_spec = SimpleNamespace(
        surfaces=[SimpleNamespace(name=action, entity_ref=surface_entity)],
        domain=SimpleNamespace(entities=entities),
    )
    region = WorkspaceRegion(name="r", source=source, action=action)
    ctx = build_workspace_context(WorkspaceSpec(name="dashboard", regions=[region]), app_spec)
    assert ctx.regions[0].action_url == expected_url
    assert ctx.regions[0].action_id_field == expected_id_field


# ===========================================================================
# Display modes — queue (#300) and activity_feed (#564)
# ===========================================================================


@pytest.mark.parametrize(
    ("mode_name", "string_value", "expected_template", "entity_name", "fields_factory"),
    [
        pytest.param(
            "QUEUE",
            "queue",
            "workspace/regions/_typed_primitive.html",
            "Task",
            lambda: [
                _make_field("title", FieldTypeKind.STR),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["pending", "approved"]),
            ],
            id="queue-300",
        ),
        pytest.param(
            "ACTIVITY_FEED",
            "activity_feed",
            "workspace/regions/_typed_primitive.html",
            "AuditLog",
            lambda: [_make_field("description", FieldTypeKind.STR)],
            id="activity_feed-564",
        ),
    ],
)
def test_display_mode_full(
    mode_name, string_value, expected_template, entity_name, fields_factory
) -> None:
    """Enum value, template mapping, region acceptance and rendered template path."""
    from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec
    from dazzle.page.runtime.workspace_renderer import (
        DISPLAY_TEMPLATE_MAP,
        build_workspace_context,
    )

    mode = getattr(DisplayMode, mode_name)
    assert mode == string_value
    assert DisplayMode(string_value) == mode
    assert DISPLAY_TEMPLATE_MAP[mode_name] == expected_template

    entity = _make_entity(entity_name, fields_factory())
    ws_region = WorkspaceRegion(name="r", source=entity_name, display=mode)
    assert ws_region.display == mode
    ws = WorkspaceSpec(name="dashboard", regions=[ws_region])
    app_spec = SimpleNamespace(
        domain=SimpleNamespace(
            entities=[entity],
            get_entity=lambda n, _e=entity, _name=entity_name: _e if n == _name else None,
        ),
        surfaces=[],
        workspaces=[ws],
    )
    assert build_workspace_context(ws, app_spec).regions[0].template == expected_template


# ===========================================================================
# current_user resolution (#486)
# ===========================================================================


@pytest.mark.parametrize(
    ("literal", "filter_ctx", "expected_value"),
    [
        pytest.param("current_user", {"current_user_id": "user-123"}, "user-123", id="with_auth"),
        pytest.param("current_user", {}, None, id="without_auth"),
        pytest.param(
            "current_user.department",
            {"current_user_id": "user-123", "current_user_entity": {"department": "dept-456"}},
            "dept-456",
            id="dot_notation-486",
        ),
    ],
)
def test_current_user_filter_resolution(literal, filter_ctx, expected_value) -> None:
    from dazzle.http.runtime.condition_evaluator import condition_to_sql_filter

    condition = {
        "comparison": {"field": "reviewer", "operator": "eq", "value": {"literal": literal}}
    }
    assert condition_to_sql_filter(condition, filter_ctx) == {"reviewer": expected_value}


_DEPT = "f6ac5054-79ff-5b1a-acd0-f1c832d3433b"


@pytest.mark.parametrize(
    ("value", "context", "expected"),
    [
        pytest.param(
            {"literal": "current_user.department"},
            {
                "current_user_id": "user-123",
                "current_user_entity": {"id": "u", "department": _DEPT},
            },
            _DEPT,
            id="scalar_field-486",
        ),
        pytest.param(
            {"literal": "current_user.department"},
            {
                "current_user_id": "user-123",
                "current_user_entity": {"id": "u", "department": {"id": _DEPT, "name": "English"}},
            },
            _DEPT,
            id="ref_dict_extracts_id-486",
        ),
        pytest.param(
            {"literal": "current_user"},
            {"current_user_id": "user-123"},
            "user-123",
            id="plain_current_user",
        ),
        pytest.param(
            {"literal": "current_user.department"},
            {"current_user_id": "user-123"},
            None,
            id="missing_entity",
        ),
        pytest.param(
            {"literal": "current_user.department"},
            {"current_user_id": "user-123", "current_user_entity": {"id": "u", "name": "Alice"}},
            None,
            id="missing_field",
        ),
        pytest.param(
            {"kind": "identifier", "value": "current_user.team_id"},
            {"current_user_id": "user-123", "current_user_entity": {"team_id": "team-789"}},
            "team-789",
            id="identifier_kind",
        ),
    ],
)
def test_resolve_current_user_value(value, context, expected) -> None:
    from dazzle.http.runtime.condition_evaluator import _resolve_value

    assert _resolve_value(value, context) == expected


# ===========================================================================
# Surface columns (#357, #872, #1426)
# ===========================================================================


def _make_surface(entity_ref: str, field_names: list[str]) -> SimpleNamespace:
    """Create a minimal SurfaceSpec-like object (no sections when field_names is empty)."""
    sections = (
        [SimpleNamespace(elements=[SimpleNamespace(field_name=fn) for fn in field_names])]
        if field_names
        else []
    )
    return SimpleNamespace(entity_ref=entity_ref, mode="list", sections=sections)


def _surface_columns(entity: Any, surface: Any) -> list[dict[str, Any]]:
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    return build_surface_columns(entity, surface)


@pytest.mark.parametrize(
    ("fields", "surface_fields", "expected"),
    [
        pytest.param(
            [
                _ID,
                _make_field("title", FieldTypeKind.STR),
                _make_field("description", FieldTypeKind.TEXT),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "done"]),
                _make_field("priority", FieldTypeKind.STR),
                _make_field("created_at", FieldTypeKind.DATETIME),
            ],
            ["title", "status"],
            [("title", "text"), ("status", "badge")],
            id="uses_surface_projection-357",
        ),
        pytest.param(
            [
                _ID,
                _make_field("severity", FieldTypeKind.STR),
                _make_field("title", FieldTypeKind.STR),
                _make_field("category", FieldTypeKind.STR),
                _make_field("message", FieldTypeKind.TEXT),
                _make_field("created_at", FieldTypeKind.DATETIME),
            ],
            ["category", "severity", "title", "message", "created_at"],
            [
                ("category", "text"),
                ("severity", "text"),
                ("title", "text"),
                ("message", "text"),
                ("created_at", "datetime"),
            ],
            id="preserves_surface_order-357",
        ),
        pytest.param(
            [
                _ID,
                _make_field("title", FieldTypeKind.STR),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open"]),
            ],
            [],
            [("title", "text"), ("status", "badge")],
            id="empty_surface_falls_back_to_all_fields-357",
        ),
        pytest.param(
            [_ID, _make_field("title", FieldTypeKind.STR)],
            ["id", "title"],
            [("title", "text")],
            id="id_in_projection_skipped-357",
        ),
        pytest.param(
            [
                _ID,
                _make_field("title", FieldTypeKind.STR),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "done"]),
                _make_field("created_at", FieldTypeKind.DATETIME),
                _make_field("completed", FieldTypeKind.BOOL),
            ],
            ["title", "status", "created_at", "completed"],
            [
                ("title", "text"),
                ("status", "badge"),
                ("created_at", "datetime"),
                ("completed", "bool"),
            ],
            id="column_types_per_field_kind",
        ),
    ],
)
def test_surface_column_projection(fields, surface_fields, expected) -> None:
    columns = _surface_columns(_make_entity("Task", fields), _make_surface("Task", surface_fields))
    assert [(c["key"], c["type"]) for c in columns] == expected


def test_ref_columns_use_app_detail_route_not_api_plural_1426() -> None:
    """Kanban/detail FK links must target /app/<slug>/{id} hubs, not JSON API plurals."""
    entity = _make_entity(
        "Task",
        [
            _ID,
            _make_field("title", FieldTypeKind.STR),
            _make_field("project", FieldTypeKind.REF, ref_entity="Project"),
            _make_field("assigned_to", FieldTypeKind.REF, ref_entity="User"),
        ],
    )
    surface = _make_surface("Task", ["title", "project", "assigned_to"])
    expected = {"project": "/app/project/{id}", "assigned_to": "/app/user/{id}"}
    for columns in (_surface_columns(entity, surface), _entity_columns(entity)):
        assert {c["key"]: c["ref_route"] for c in columns if c["type"] == "ref"} == expected


def _role_payload(role_name: str) -> dict[str, Any]:
    return {
        "role_check": {"role_name": role_name},
        "operator": None,
        "left": None,
        "right": None,
        "comparison": None,
        "grant_check": None,
    }


def _visible_role(role_name: str) -> SimpleNamespace:
    """ConditionExpr-shaped object whose model_dump() yields a role check."""
    return SimpleNamespace(model_dump=lambda: _role_payload(role_name))


@pytest.mark.parametrize(
    ("section_visible", "priority_visible", "expected"),
    [
        pytest.param(
            None,
            _visible_role("admin"),
            {"title": None, "priority": _role_payload("admin")},
            id="element_visible_attached-872",
        ),
        pytest.param(
            _visible_role("school_admin"),
            None,
            {"title": _role_payload("school_admin"), "priority": _role_payload("school_admin")},
            id="section_visible_falls_through-872",
        ),
        pytest.param(
            _visible_role("school_admin"),
            _visible_role("teacher"),
            {"title": _role_payload("school_admin"), "priority": _role_payload("teacher")},
            id="element_overrides_section-872",
        ),
    ],
)
def test_surface_columns_visible_condition(section_visible, priority_visible, expected) -> None:
    entity = _make_entity(
        "Task",
        [_ID, _make_field("title", FieldTypeKind.STR), _make_field("priority", FieldTypeKind.STR)],
    )
    section = SimpleNamespace(
        visible=section_visible,
        elements=[
            SimpleNamespace(field_name="title", visible=None),
            SimpleNamespace(field_name="priority", visible=priority_visible),
        ],
    )
    columns = _surface_columns(entity, SimpleNamespace(sections=[section]))
    assert {c["key"]: c.get("visible_condition") for c in columns} == expected


# ===========================================================================
# WorkspaceRegionContext (#362) and stats endpoint (#783)
# ===========================================================================


def _region_ctx(
    *,
    region_name: str = "t",
    aggregates: dict[str, Any] | None = None,
    repositories: dict[str, Any] | None = None,
    require_auth: bool = False,
    auth_middleware: Any = None,
) -> Any:
    from dazzle.http.runtime.workspace_context import WorkspaceRegionContext

    return WorkspaceRegionContext(
        ctx_region=SimpleNamespace(
            display="LIST",
            limit=None,
            empty_message="",
            aggregates=aggregates or {},
            group_by="",
            template="workspace/regions/_typed_primitive.html",
            title=region_name.title(),
            name=region_name,
            endpoint="/api/workspaces/dash/regions/r",
            action_url="",
            source_tabs=[],
        ),
        ir_region=SimpleNamespace(sort=[], filter=None),
        source="Task",
        entity_spec=None,
        attention_signals=[],
        ws_access=None,
        repositories=repositories or {},
        require_auth=require_auth,
        auth_middleware=auth_middleware,
    )


def test_region_context_surface_ux_defaults_362() -> None:
    """Surface UX sort / empty_message default to empty list / string when not provided."""
    ctx = _region_ctx()
    assert ctx.surface_default_sort == []
    assert ctx.surface_empty_message == ""


class _FakeRepo:
    def __init__(self, total: int) -> None:
        self._total = total

    async def list(self, *, page: int, page_size: int, filters: Any = None) -> Any:
        return {"items": [], "total": self._total}


def _agg_ctx(name: str, label_key: str, entity: str, total: int) -> Any:
    return _region_ctx(
        region_name=name,
        aggregates={label_key: AggregateRef(func="count", entity=entity)},
        repositories={entity: _FakeRepo(total)},
    )


@pytest.mark.parametrize(
    ("make_ctxs", "expected_stats"),
    [
        pytest.param(lambda: [_region_ctx(region_name="tasks")], {}, id="no_aggregates"),
        pytest.param(
            lambda: [_agg_ctx("overview", "total_work", "Work", 42)],
            {"overview": {"Total Work": 42}},
            id="count_entity_aggregate",
        ),
        pytest.param(
            lambda: [
                _agg_ctx("kpis", "active_works", "Work", 10),
                _agg_ctx("campaigns", "running", "Campaign", 3),
            ],
            {"kpis": {"Active Works": 10}, "campaigns": {"Running": 3}},
            id="namespaced_by_region",
        ),
        pytest.param(
            lambda: [_region_ctx(region_name="plain"), _agg_ctx("with_agg", "n", "Task", 5)],
            {"with_agg": {"N": 5}},
            id="skips_regions_without_aggregates",
        ),
    ],
)
async def test_workspace_stats_handler_783(make_ctxs, expected_stats) -> None:
    from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

    result = await _workspace_stats_handler(SimpleNamespace(query_params={}), make_ctxs())
    assert result == {"workspace": "dash", "stats": expected_stats}


async def test_workspace_stats_handler_requires_auth_when_configured_783() -> None:
    from fastapi import HTTPException

    from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

    class FailingAuth:
        def get_auth_context(self, request: Any) -> Any:
            return SimpleNamespace(is_authenticated=False, user=None, roles=[])

    ctx = _region_ctx(
        region_name="kpis",
        aggregates={"n": AggregateRef(func="count", entity="Task")},
        require_auth=True,
        auth_middleware=FailingAuth(),
    )
    with pytest.raises(HTTPException) as exc:
        await _workspace_stats_handler(SimpleNamespace(query_params={}), [ctx])
    assert exc.value.status_code == 401


# ===========================================================================
# Viewport lazy loading (#378)
# ===========================================================================


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        pytest.param(None, 3, id="default"),
        pytest.param("command_center", 3, id="command_center"),
        pytest.param("monitor_wall", 4, id="monitor_wall"),
        pytest.param("scanner_table", 2, id="scanner_table"),
        pytest.param("dual_pane_flow", 3, id="dual_pane"),
        pytest.param("pair_strip", 3, id="pair_strip"),
    ],
)
def test_fold_count_378(stage, expected) -> None:
    from dazzle.core.ir.workspaces import WorkspaceSpec
    from dazzle.page.runtime.workspace_renderer import build_workspace_context

    kwargs: dict[str, Any] = {"name": "dashboard", "regions": []}
    if stage is not None:
        kwargs["stage"] = stage
    assert build_workspace_context(WorkspaceSpec(**kwargs)).fold_count == expected


def test_stage_fold_count_map_keys_378() -> None:
    """All stages in STAGE_DEFAULT_SPANS have a corresponding fold count."""
    from dazzle.page.runtime.workspace_renderer import STAGE_DEFAULT_SPANS, STAGE_FOLD_COUNTS

    assert set(STAGE_DEFAULT_SPANS) <= set(STAGE_FOLD_COUNTS)


# Region-request current_user resolution (#483, #484, #486, #588) is pinned
# behaviourally in test_workspace_user_stable_id_1626.py.
