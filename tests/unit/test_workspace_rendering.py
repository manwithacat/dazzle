"""Tests for workspace region rendering — column types, filters, attention, timeago.

Covers:
- _field_kind_to_col_type: correct mapping from IR field → column type
- Filterable columns: enum, bool, state-machine status
- timeago Jinja2 filter
- Attention row highlighting
- Ref/UUID column hiding
- Cross-entity action URL resolution
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

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
    return SimpleNamespace(
        name=name,
        fields=fields,
        state_machine=state_machine,
    )


# ===========================================================================
# TestFieldKindToColType
# ===========================================================================


class TestFieldKindToColType:
    """_field_kind_to_col_type() maps IR fields to column rendering types."""

    def test_enum_field_returns_badge(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "closed"])
        assert _field_kind_to_col_type(f) == "badge"

    def test_bool_field_returns_bool(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("completed", FieldTypeKind.BOOL)
        assert _field_kind_to_col_type(f) == "bool"

    def test_date_field_returns_date(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("created_at", FieldTypeKind.DATE)
        assert _field_kind_to_col_type(f) == "date"

    def test_datetime_field_returns_date(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("updated_at", FieldTypeKind.DATETIME)
        assert _field_kind_to_col_type(f) == "date"

    def test_money_field_returns_currency(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("amount", FieldTypeKind.MONEY)
        assert _field_kind_to_col_type(f) == "currency"

    def test_str_field_returns_text(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("title", FieldTypeKind.STR)
        assert _field_kind_to_col_type(f) == "text"

    def test_state_machine_status_field_returns_badge(self) -> None:
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("status", FieldTypeKind.STR)
        sm = SimpleNamespace(status_field="status", states=["open", "closed"])
        entity = _make_entity("Task", [f], state_machine=sm)
        assert _field_kind_to_col_type(f, entity) == "badge"

    def test_non_status_field_with_state_machine_returns_text(self) -> None:
        """A field that's NOT the status_field should still return text."""
        from dazzle_back.runtime.server import _field_kind_to_col_type

        f = _make_field("title", FieldTypeKind.STR)
        sm = SimpleNamespace(status_field="status", states=["open", "closed"])
        entity = _make_entity("Task", [f], state_machine=sm)
        assert _field_kind_to_col_type(f, entity) == "text"


# ===========================================================================
# TestFilterableColumns
# ===========================================================================


class TestFilterableColumns:
    """Column-building in server.py should mark filterable columns."""

    def _build_columns(self, entity: Any) -> list[dict[str, Any]]:
        """Simulate the column-building loop from server.py."""
        from dazzle_back.runtime.server import _field_kind_to_col_type

        columns: list[dict[str, Any]] = []
        for f in entity.fields:
            if f.name == "id":
                continue
            ft = getattr(f, "type", None)
            kind = getattr(ft, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
            if kind_val in ("ref", "uuid", "has_many", "has_one", "embeds", "belongs_to"):
                continue
            if f.name.endswith("_id"):
                continue
            col_type = _field_kind_to_col_type(f, entity)
            col: dict[str, Any] = {
                "key": f.name,
                "label": getattr(f, "label", None) or f.name.replace("_", " ").title(),
                "type": col_type,
                "sortable": True,
            }
            if col_type == "badge":
                if kind_val == "enum":
                    ev = getattr(ft, "enum_values", None)
                    if ev:
                        col["filterable"] = True
                        col["filter_options"] = list(ev)
                else:
                    sm = getattr(entity, "state_machine", None)
                    if sm:
                        states = getattr(sm, "states", [])
                        if states:
                            col["filterable"] = True
                            col["filter_options"] = list(states)
            if col_type == "bool":
                col["filterable"] = True
                col["filter_options"] = ["true", "false"]
            columns.append(col)
        return columns

    def test_enum_column_is_filterable_with_options(self) -> None:
        f = _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "closed", "pending"])
        entity = _make_entity("Task", [f])
        cols = self._build_columns(entity)
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["open", "closed", "pending"]

    def test_bool_column_is_filterable(self) -> None:
        f = _make_field("completed", FieldTypeKind.BOOL)
        entity = _make_entity("Task", [f])
        cols = self._build_columns(entity)
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["true", "false"]

    def test_str_column_not_filterable(self) -> None:
        f = _make_field("title", FieldTypeKind.STR)
        entity = _make_entity("Task", [f])
        cols = self._build_columns(entity)
        assert len(cols) == 1
        assert "filterable" not in cols[0]

    def test_state_machine_status_filterable_with_states(self) -> None:
        f = _make_field("status", FieldTypeKind.STR)
        sm = SimpleNamespace(status_field="status", states=["draft", "active", "done"])
        entity = _make_entity("Task", [f], state_machine=sm)
        cols = self._build_columns(entity)
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["draft", "active", "done"]


# ===========================================================================
# TestTimeagoFilter
# ===========================================================================


class TestTimeagoFilter:
    """timeago Jinja2 filter returns human-readable relative times."""

    def test_seconds_ago(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        dt = datetime.now() - timedelta(seconds=30)
        result = _timeago_filter(dt)
        assert "seconds ago" in result

    def test_hours_ago(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        dt = datetime.now() - timedelta(hours=3)
        result = _timeago_filter(dt)
        assert "3 hours ago" == result

    def test_days_ago(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        dt = datetime.now() - timedelta(days=5)
        result = _timeago_filter(dt)
        assert "5 days ago" == result

    def test_invalid_input_returns_original(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        result = _timeago_filter("not-a-date")
        assert result == "not-a-date"

    def test_none_returns_empty(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        assert _timeago_filter(None) == ""

    def test_iso_string_parsed(self) -> None:
        from dazzle_ui.runtime.template_renderer import _timeago_filter

        dt = datetime.now() - timedelta(minutes=10)
        result = _timeago_filter(dt.isoformat())
        assert "10 minutes ago" == result


# ===========================================================================
# TestAttentionHighlighting
# ===========================================================================


class TestAttentionHighlighting:
    """Attention signals evaluate conditions and annotate rows."""

    def _make_signal(self, level: str, field: str, operator: str, value: str, message: str) -> Any:
        from dazzle.core.ir.conditions import Comparison, ConditionExpr, ConditionValue
        from dazzle.core.ir.ux import AttentionSignal, SignalLevel

        cond = ConditionExpr(
            comparison=Comparison(
                field=field,
                operator=operator,
                value=ConditionValue(literal=value),
            )
        )
        return AttentionSignal(level=SignalLevel(level), condition=cond, message=message)

    def _evaluate_attention(
        self, signals: list[Any], item: dict[str, Any]
    ) -> dict[str, str] | None:
        """Reproduce the attention evaluation logic from server.py."""
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        severity_order = {"critical": 0, "warning": 1, "notice": 2, "info": 3}
        best: dict[str, str] | None = None
        best_sev = 999
        for sig in signals:
            cond_dict = sig.condition.model_dump(exclude_none=True)
            if evaluate_condition(cond_dict, item, {}):
                lvl = sig.level.value if hasattr(sig.level, "value") else str(sig.level)
                sev = severity_order.get(lvl, 99)
                if sev < best_sev:
                    best_sev = sev
                    best = {"level": lvl, "message": sig.message}
        return best

    def test_warning_condition_matches(self) -> None:
        sig = self._make_signal("warning", "status", "=", "overdue", "Task is overdue")
        result = self._evaluate_attention([sig], {"status": "overdue", "title": "Fix bug"})
        assert result is not None
        assert result["level"] == "warning"
        assert result["message"] == "Task is overdue"

    def test_no_condition_match_returns_none(self) -> None:
        sig = self._make_signal("warning", "status", "=", "overdue", "Task is overdue")
        result = self._evaluate_attention([sig], {"status": "active", "title": "Fix bug"})
        assert result is None

    def test_multiple_signals_highest_severity_wins(self) -> None:
        sig_warning = self._make_signal("warning", "status", "=", "overdue", "Overdue")
        sig_critical = self._make_signal("critical", "priority", "=", "high", "High priority")
        item = {"status": "overdue", "priority": "high"}
        result = self._evaluate_attention([sig_warning, sig_critical], item)
        assert result is not None
        assert result["level"] == "critical"
        assert result["message"] == "High priority"


# ===========================================================================
# TestRefColumnHiding
# ===========================================================================


class TestRefColumnHiding:
    """Ref, UUID, and relationship columns should be hidden from workspace tables."""

    def _build_columns(self, entity: Any) -> list[dict[str, Any]]:
        """Simulate the column-building loop from server.py."""
        from dazzle_back.runtime.server import _field_kind_to_col_type

        columns: list[dict[str, Any]] = []
        for f in entity.fields:
            if f.name == "id":
                continue
            ft = getattr(f, "type", None)
            kind = getattr(ft, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
            if kind_val in ("ref", "uuid", "has_many", "has_one", "embeds", "belongs_to"):
                continue
            if f.name.endswith("_id"):
                continue
            col_type = _field_kind_to_col_type(f, entity)
            columns.append({"key": f.name, "type": col_type})
        return columns

    def test_ref_field_hidden(self) -> None:
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "customer" not in keys
        assert "title" in keys

    def test_uuid_field_hidden(self) -> None:
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("external_id", FieldTypeKind.UUID),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "external_id" not in keys

    def test_has_many_field_hidden(self) -> None:
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "items" not in keys

    def test_id_field_hidden(self) -> None:
        fields = [
            _make_field("id", FieldTypeKind.UUID),
            _make_field("title", FieldTypeKind.STR),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "id" not in keys
        assert "title" in keys

    def test_fk_suffix_field_hidden(self) -> None:
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("customer_id", FieldTypeKind.STR),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "customer_id" not in keys


# ===========================================================================
# TestCrossEntityAction
# ===========================================================================


class TestCrossEntityAction:
    """Action URL resolution handles cross-entity surfaces."""

    def _make_app_spec(
        self,
        surface_name: str,
        surface_entity: str,
        source_entity_name: str | None = None,
        source_fields: list[FieldSpec] | None = None,
    ) -> Any:
        """Create minimal app_spec with domain + surface."""
        surface = SimpleNamespace(name=surface_name, entity_ref=surface_entity)
        entities = []
        if source_entity_name and source_fields:
            entities.append(SimpleNamespace(name=source_entity_name, fields=source_fields))
        domain = SimpleNamespace(entities=entities)
        return SimpleNamespace(surfaces=[surface], domain=domain)

    def test_same_entity_uses_id(self) -> None:
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        region = WorkspaceRegion(name="tasks", source="Task", action="task_edit")
        ws = WorkspaceSpec(name="dashboard", regions=[region])
        app_spec = self._make_app_spec("task_edit", "Task")

        ctx = build_workspace_context(ws, app_spec)
        assert ctx.regions[0].action_url == "/tasks/{id}"

    def test_cross_entity_resolves_fk_field(self) -> None:
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        # Order has a ref field "customer" pointing at Customer
        order_fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
        ]
        region = WorkspaceRegion(name="orders", source="Order", action="customer_detail")
        ws = WorkspaceSpec(name="dashboard", regions=[region])
        app_spec = self._make_app_spec(
            "customer_detail",
            "Customer",
            source_entity_name="Order",
            source_fields=order_fields,
        )

        ctx = build_workspace_context(ws, app_spec)
        assert ctx.regions[0].action_url == "/customers/{customer}"

    def test_cross_entity_fallback_to_id(self) -> None:
        """When no FK field links source to target, fall back to {id}."""
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        order_fields = [_make_field("title", FieldTypeKind.STR)]
        region = WorkspaceRegion(name="orders", source="Order", action="customer_detail")
        ws = WorkspaceSpec(name="dashboard", regions=[region])
        app_spec = self._make_app_spec(
            "customer_detail",
            "Customer",
            source_entity_name="Order",
            source_fields=order_fields,
        )

        ctx = build_workspace_context(ws, app_spec)
        assert ctx.regions[0].action_url == "/customers/{id}"


# ===========================================================================
# TestQueueDisplayMode
# ===========================================================================


class TestQueueDisplayMode:
    """Tests for the queue display mode (#300)."""

    def test_display_mode_enum_has_queue(self) -> None:
        """DisplayMode enum includes QUEUE value."""
        from dazzle.core.ir.workspaces import DisplayMode

        assert DisplayMode.QUEUE == "queue"
        assert DisplayMode("queue") == DisplayMode.QUEUE

    def test_queue_template_mapping(self) -> None:
        """QUEUE maps to the queue.html template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "QUEUE" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["QUEUE"] == "workspace/regions/queue.html"

    def test_workspace_region_with_queue_display(self) -> None:
        """WorkspaceRegion accepts display=queue."""
        from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion

        region = WorkspaceRegion(
            name="review_queue",
            source="BookkeepingPeriod",
            display=DisplayMode.QUEUE,
        )
        assert region.display == DisplayMode.QUEUE

    def test_queue_region_renders_correct_template(self) -> None:
        """Queue region context gets the queue template path."""
        from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("status", FieldTypeKind.ENUM, enum_values=["pending", "approved"]),
        ]
        entity = _make_entity("Task", fields)
        region = WorkspaceRegion(name="review", source="Task", display=DisplayMode.QUEUE)
        ws = WorkspaceSpec(name="dashboard", regions=[region])

        app_spec = SimpleNamespace(
            domain=SimpleNamespace(
                entities=[entity],
                get_entity=lambda n: entity if n == "Task" else None,
            ),
            surfaces=[],
            workspaces=[ws],
        )

        ctx = build_workspace_context(ws, app_spec)
        assert ctx.regions[0].template == "workspace/regions/queue.html"

    def test_current_user_filter_context(self) -> None:
        """_resolve_value handles current_user identifier in filter context."""
        from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter

        condition = {
            "comparison": {
                "field": "reviewer",
                "operator": "eq",
                "value": {"literal": "current_user"},
            }
        }
        result = condition_to_sql_filter(condition, {"current_user_id": "user-123"})
        assert result == {"reviewer": "user-123"}

    def test_current_user_filter_without_auth(self) -> None:
        """current_user resolves to None when no user is authenticated."""
        from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter

        condition = {
            "comparison": {
                "field": "reviewer",
                "operator": "eq",
                "value": {"literal": "current_user"},
            }
        }
        result = condition_to_sql_filter(condition, {})
        assert result == {"reviewer": None}

    def test_display_mode_queue_from_string(self) -> None:
        """DisplayMode('queue') works (used by DSL parser via token.value)."""
        from dazzle.core.ir.workspaces import DisplayMode

        assert DisplayMode("queue") == DisplayMode.QUEUE
        assert DisplayMode("queue").value == "queue"
