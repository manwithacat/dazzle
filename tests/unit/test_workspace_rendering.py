"""Tests for workspace region rendering — column types, filters, attention, timeago.

Covers:
- _field_kind_to_col_type: correct mapping from IR field → column type
- Filterable columns: enum, bool, state-machine status
- timeago Jinja2 filter
- Attention row highlighting
- Ref/UUID column hiding
- Cross-entity action URL resolution
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

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
        ],
        ids=["enum_badge", "bool", "date", "datetime_col", "money_currency", "str_text"],
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


# ===========================================================================
# TestFilterableColumns
# ===========================================================================


class TestFilterableColumns:
    """Column-building in server.py should mark filterable columns."""

    def _build_columns(self, entity: Any) -> list[dict[str, Any]]:
        """Simulate the column-building loop from server.py."""
        from dazzle.http.runtime.server import _field_kind_to_col_type

        columns: list[dict[str, Any]] = []
        for f in entity.fields:
            if f.name == "id":
                continue
            ft = getattr(f, "type", None)
            kind = getattr(ft, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
            # Ref and belongs_to: show as ref columns with relation name key
            if kind_val in ("ref", "belongs_to"):
                rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                ref_entity = getattr(ft, "ref_entity", None)
                from dazzle.core.strings import to_api_plural

                ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
                columns.append(
                    {
                        "key": rel_name,
                        "label": rel_name.replace("_", " ").title(),
                        "type": "ref",
                        "sortable": False,
                        "ref_route": ref_route,
                    }
                )
                continue
            if kind_val in ("uuid", "has_many", "has_one", "embeds"):
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

    def test_filterable_columns(self) -> None:
        """Columns are filterable when enum/bool/state_machine; str is not.

        Combined: enum_column_is_filterable_with_options, bool_column_is_filterable,
        str_column_not_filterable, state_machine_status_filterable_with_states.
        """
        # Enum field — filterable with enum values as options
        cols = self._build_columns(
            _make_entity(
                "Task",
                [
                    _make_field(
                        "status", FieldTypeKind.ENUM, enum_values=["open", "closed", "pending"]
                    )
                ],
            )
        )
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["open", "closed", "pending"]

        # Bool field — filterable with true/false options
        cols = self._build_columns(
            _make_entity("Task", [_make_field("completed", FieldTypeKind.BOOL)])
        )
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["true", "false"]

        # Str field — not filterable
        cols = self._build_columns(_make_entity("Task", [_make_field("title", FieldTypeKind.STR)]))
        assert len(cols) == 1
        assert "filterable" not in cols[0]

        # State-machine status field — filterable with states list
        sm = SimpleNamespace(status_field="status", states=["draft", "active", "done"])
        cols = self._build_columns(
            _make_entity("Task", [_make_field("status", FieldTypeKind.STR)], state_machine=sm)
        )
        assert len(cols) == 1
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["draft", "active", "done"]


# ===========================================================================
# TestTimeagoFilter
# ===========================================================================


class TestTimeagoFilter:
    """timeago Jinja2 filter returns human-readable relative times."""

    def test_seconds_ago(self) -> None:
        from dazzle.render.filters import _timeago_filter

        dt = datetime.now() - timedelta(seconds=30)
        result = _timeago_filter(dt)
        assert "seconds ago" in result

    @pytest.mark.parametrize(
        ("input_factory", "expected"),
        [
            (lambda: datetime.now() - timedelta(hours=3), "3 hours ago"),
            (lambda: datetime.now() - timedelta(days=5), "5 days ago"),
            (lambda: "not-a-date", "not-a-date"),
            (lambda: None, ""),
            (lambda: (datetime.now() - timedelta(minutes=10)).isoformat(), "10 minutes ago"),
        ],
        ids=[
            "test_hours_ago",
            "test_days_ago",
            "test_invalid_input_returns_original",
            "test_none_returns_empty",
            "test_iso_string_parsed",
        ],
    )
    def test_filter(self, input_factory, expected) -> None:
        from dazzle.render.filters import _timeago_filter

        assert _timeago_filter(input_factory()) == expected


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
        from dazzle.http.runtime.condition_evaluator import evaluate_condition

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

    def test_attention_evaluation(self) -> None:
        """Attention signals: matching condition wins, no match returns None, highest severity wins.

        Combined: warning_condition_matches, no_condition_match_returns_none,
        multiple_signals_highest_severity_wins.
        """
        # Matching condition produces signal
        sig = self._make_signal("warning", "status", "=", "overdue", "Task is overdue")
        result = self._evaluate_attention([sig], {"status": "overdue", "title": "Fix bug"})
        assert result is not None
        assert result["level"] == "warning"
        assert result["message"] == "Task is overdue"

        # No matching condition → None
        assert self._evaluate_attention([sig], {"status": "active", "title": "Fix bug"}) is None

        # Multiple signals — critical beats warning
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
    """Ref/belongs_to show as ref columns; UUID and relationship columns are hidden."""

    def _build_columns(self, entity: Any) -> list[dict[str, Any]]:
        """Simulate the column-building loop from workspace_rendering.py."""
        from dazzle.http.runtime.server import _field_kind_to_col_type

        columns: list[dict[str, Any]] = []
        for f in entity.fields:
            if f.name == "id":
                continue
            ft = getattr(f, "type", None)
            kind = getattr(ft, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
            if kind_val in ("ref", "belongs_to"):
                rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                columns.append({"key": rel_name, "type": "ref"})
                continue
            if kind_val in ("uuid", "has_many", "has_one", "embeds"):
                continue
            if f.name.endswith("_id"):
                continue
            col_type = _field_kind_to_col_type(f, entity)
            columns.append({"key": f.name, "type": col_type})
        return columns

    def test_ref_field_shown_as_ref_column(self) -> None:
        """Ref fields appear as ref-type columns with relation name key (#553)."""
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
        ]
        entity = _make_entity("Order", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "customer" in keys
        assert "title" in keys
        ref_col = next(c for c in cols if c["key"] == "customer")
        assert ref_col["type"] == "ref"

    def test_belongs_to_field_shown_as_ref_column(self) -> None:
        """Belongs_to fields appear as ref-type columns (#553)."""
        fields = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("order_id", FieldTypeKind.BELONGS_TO, ref_entity="Order"),
        ]
        entity = _make_entity("LineItem", fields)
        cols = self._build_columns(entity)
        keys = [c["key"] for c in cols]
        assert "order" in keys  # _id suffix stripped
        ref_col = next(c for c in cols if c["key"] == "order")
        assert ref_col["type"] == "ref"

    def test_hidden_field_kinds(self) -> None:
        """Hidden columns: uuid, has_many, id, _id-suffix-as-str.

        Combined: uuid_field_hidden, has_many_field_hidden, id_field_hidden,
        fk_suffix_field_hidden.
        """
        # uuid hidden
        cols = self._build_columns(
            _make_entity(
                "Order",
                [
                    _make_field("title", FieldTypeKind.STR),
                    _make_field("external_id", FieldTypeKind.UUID),
                ],
            )
        )
        keys = [c["key"] for c in cols]
        assert "external_id" not in keys

        # has_many hidden
        cols = self._build_columns(
            _make_entity(
                "Order",
                [
                    _make_field("title", FieldTypeKind.STR),
                    _make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                ],
            )
        )
        keys = [c["key"] for c in cols]
        assert "items" not in keys

        # id field hidden, other fields visible
        cols = self._build_columns(
            _make_entity(
                "Order",
                [
                    _make_field("id", FieldTypeKind.UUID),
                    _make_field("title", FieldTypeKind.STR),
                ],
            )
        )
        keys = [c["key"] for c in cols]
        assert "id" not in keys
        assert "title" in keys

        # fk_suffix string field hidden
        cols = self._build_columns(
            _make_entity(
                "Order",
                [
                    _make_field("title", FieldTypeKind.STR),
                    _make_field("customer_id", FieldTypeKind.STR),
                ],
            )
        )
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

    def test_action_url_resolution(self) -> None:
        """Action URL resolution: same-entity, cross-entity FK, fallback to {id}.

        Combined: same_entity_uses_id, cross_entity_resolves_fk_field,
        cross_entity_fallback_to_id.
        """
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle.page.runtime.workspace_renderer import build_workspace_context

        # Same entity → /app/<entity>/{id}
        region = WorkspaceRegion(name="tasks", source="Task", action="task_edit")
        ws = WorkspaceSpec(name="dashboard", regions=[region])
        ctx = build_workspace_context(ws, self._make_app_spec("task_edit", "Task"))
        assert ctx.regions[0].action_url == "/app/task/{id}"

        # Cross-entity: FK on source resolves to action_id_field
        order_fields_fk = [
            _make_field("title", FieldTypeKind.STR),
            _make_field("customer", FieldTypeKind.REF, ref_entity="Customer"),
        ]
        region2 = WorkspaceRegion(name="orders", source="Order", action="customer_detail")
        ws2 = WorkspaceSpec(name="dashboard", regions=[region2])
        ctx2 = build_workspace_context(
            ws2,
            self._make_app_spec(
                "customer_detail",
                "Customer",
                source_entity_name="Order",
                source_fields=order_fields_fk,
            ),
        )
        assert ctx2.regions[0].action_url == "/app/customer/{id}"
        assert ctx2.regions[0].action_id_field == "customer"

        # Cross-entity: no FK link → fallback to {id}
        order_fields_no_fk = [_make_field("title", FieldTypeKind.STR)]
        region3 = WorkspaceRegion(name="orders", source="Order", action="customer_detail")
        ws3 = WorkspaceSpec(name="dashboard", regions=[region3])
        ctx3 = build_workspace_context(
            ws3,
            self._make_app_spec(
                "customer_detail",
                "Customer",
                source_entity_name="Order",
                source_fields=order_fields_no_fk,
            ),
        )
        assert ctx3.regions[0].action_url == "/app/customer/{id}"


# ===========================================================================
# TestQueueDisplayMode
# ===========================================================================


class TestDisplayModes:
    """Combined tests for queue (#300) and activity_feed (#564) display modes."""

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
                id="queue",
            ),
            pytest.param(
                "ACTIVITY_FEED",
                "activity_feed",
                "workspace/regions/_typed_primitive.html",
                "AuditLog",
                lambda: [_make_field("description", FieldTypeKind.STR)],
                id="activity_feed",
            ),
        ],
    )
    def test_display_mode_full(
        self, mode_name, string_value, expected_template, entity_name, fields_factory
    ) -> None:
        """Combined: enum value, template mapping, region acceptance, render template, string-from-value."""
        from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec
        from dazzle.page.runtime.workspace_renderer import (
            DISPLAY_TEMPLATE_MAP,
            build_workspace_context,
        )

        # enum value
        mode = getattr(DisplayMode, mode_name)
        assert mode == string_value
        assert DisplayMode(string_value) == mode
        assert DisplayMode(string_value).value == string_value

        # template mapping
        assert mode_name in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP[mode_name] == expected_template

        # WorkspaceRegion accepts the display value
        region = WorkspaceRegion(name="r", source=entity_name, display=mode)
        assert region.display == mode

        # build_workspace_context wires the right template path
        entity = _make_entity(entity_name, fields_factory())
        ws_region = WorkspaceRegion(name="r", source=entity_name, display=mode)
        ws = WorkspaceSpec(name="dashboard", regions=[ws_region])
        app_spec = SimpleNamespace(
            domain=SimpleNamespace(
                entities=[entity],
                get_entity=lambda n, _e=entity, _name=entity_name: _e if n == _name else None,
            ),
            surfaces=[],
            workspaces=[ws],
        )
        ctx = build_workspace_context(ws, app_spec)
        assert ctx.regions[0].template == expected_template


class TestCurrentUserFilter:
    """Tests for current_user identifier resolution in filter context."""

    @pytest.mark.parametrize(
        ("filter_ctx", "expected_value"),
        [
            pytest.param({"current_user_id": "user-123"}, "user-123", id="with_auth"),
            pytest.param({}, None, id="without_auth"),
        ],
    )
    def test_current_user_filter_resolution(self, filter_ctx, expected_value) -> None:
        """current_user resolves from filter context (None when unauthenticated)."""
        from dazzle.http.runtime.condition_evaluator import condition_to_sql_filter

        condition = {
            "comparison": {
                "field": "reviewer",
                "operator": "eq",
                "value": {"literal": "current_user"},
            }
        }
        result = condition_to_sql_filter(condition, filter_ctx)
        assert result == {"reviewer": expected_value}


# ===========================================================================
# TestBuildSurfaceColumns (#357)
# ===========================================================================


def _make_surface_section(field_names: list[str]) -> SimpleNamespace:
    """Create a minimal SurfaceSection-like object with elements."""
    elements = [SimpleNamespace(field_name=fn) for fn in field_names]
    return SimpleNamespace(elements=elements)


def _make_surface(
    entity_ref: str,
    mode: str = "list",
    field_names: list[str] | None = None,
) -> SimpleNamespace:
    """Create a minimal SurfaceSpec-like object."""
    sections = [_make_surface_section(field_names)] if field_names else []
    return SimpleNamespace(
        entity_ref=entity_ref,
        mode=mode,
        sections=sections,
    )


class TestBuildSurfaceColumns:
    """_build_surface_columns() should use surface field projection (#357)."""

    def test_uses_surface_field_projection(self) -> None:
        """Only surface-declared fields appear as columns."""
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("description", FieldTypeKind.TEXT),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "done"]),
                _make_field("priority", FieldTypeKind.STR),
                _make_field("created_at", FieldTypeKind.DATETIME),
            ],
        )
        surface = _make_surface("Task", field_names=["title", "status"])
        columns = _build_surface_columns(entity, surface)

        keys = [c["key"] for c in columns]
        assert keys == ["title", "status"]

    def test_preserves_field_order(self) -> None:
        """Columns should appear in surface section order, not entity order."""
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Notification",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("severity", FieldTypeKind.STR),
                _make_field("title", FieldTypeKind.STR),
                _make_field("category", FieldTypeKind.STR),
                _make_field("message", FieldTypeKind.TEXT),
                _make_field("created_at", FieldTypeKind.DATETIME),
            ],
        )
        surface = _make_surface(
            "Notification", field_names=["category", "severity", "title", "message", "created_at"]
        )
        columns = _build_surface_columns(entity, surface)

        keys = [c["key"] for c in columns]
        assert keys == ["category", "severity", "title", "message", "created_at"]

    def test_falls_back_to_all_fields_when_surface_empty(self) -> None:
        """Empty surface sections should fall back to all entity fields."""
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open"]),
            ],
        )
        surface = _make_surface("Task", field_names=[])
        columns = _build_surface_columns(entity, surface)

        keys = [c["key"] for c in columns]
        assert "title" in keys
        assert "status" in keys

    def test_skips_id_field_in_projection(self) -> None:
        """'id' in surface fields should be ignored."""
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
            ],
        )
        surface = _make_surface("Task", field_names=["id", "title"])
        columns = _build_surface_columns(entity, surface)

        keys = [c["key"] for c in columns]
        assert "id" not in keys
        assert keys == ["title"]

    def test_column_types_preserved(self) -> None:
        """Surface-aware columns should have correct types (badge, date, etc.)."""
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("status", FieldTypeKind.ENUM, enum_values=["open", "done"]),
                _make_field("created_at", FieldTypeKind.DATETIME),
                _make_field("completed", FieldTypeKind.BOOL),
            ],
        )
        surface = _make_surface("Task", field_names=["title", "status", "created_at", "completed"])
        columns = _build_surface_columns(entity, surface)

        col_map = {c["key"]: c for c in columns}
        assert col_map["title"]["type"] == "text"
        assert col_map["status"]["type"] == "badge"
        assert col_map["created_at"]["type"] == "datetime"
        assert col_map["completed"]["type"] == "bool"


def _make_visible_role(role_name: str) -> SimpleNamespace:
    """Build a ConditionExpr-shaped object whose model_dump() yields a role check."""
    payload = {
        "role_check": {"role_name": role_name},
        "operator": None,
        "left": None,
        "right": None,
        "comparison": None,
        "grant_check": None,
    }
    return SimpleNamespace(model_dump=lambda p=payload: p)


class TestSurfaceColumnsVisibleCondition:
    """_build_surface_columns() should carry visible: predicates onto columns (#872)."""

    def test_element_visible_attached_to_column(self) -> None:
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("priority", FieldTypeKind.STR),
            ],
        )
        section = SimpleNamespace(
            visible=None,
            elements=[
                SimpleNamespace(field_name="title", visible=None),
                SimpleNamespace(field_name="priority", visible=_make_visible_role("admin")),
            ],
        )
        surface = SimpleNamespace(sections=[section])
        columns = _build_surface_columns(entity, surface)

        col_map = {c["key"]: c for c in columns}
        assert "visible_condition" not in col_map["title"]
        assert col_map["priority"]["visible_condition"] == {
            "role_check": {"role_name": "admin"},
            "operator": None,
            "left": None,
            "right": None,
            "comparison": None,
            "grant_check": None,
        }

    def test_section_visible_falls_through_to_columns(self) -> None:
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("priority", FieldTypeKind.STR),
            ],
        )
        section = SimpleNamespace(
            visible=_make_visible_role("school_admin"),
            elements=[
                SimpleNamespace(field_name="title", visible=None),
                SimpleNamespace(field_name="priority", visible=None),
            ],
        )
        surface = SimpleNamespace(sections=[section])
        columns = _build_surface_columns(entity, surface)

        for col in columns:
            assert col["visible_condition"]["role_check"]["role_name"] == "school_admin"

    def test_element_visible_overrides_section_visible(self) -> None:
        from dazzle.http.runtime.workspace_columns import (
            build_surface_columns as _build_surface_columns,
        )

        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
                _make_field("title", FieldTypeKind.STR),
                _make_field("priority", FieldTypeKind.STR),
            ],
        )
        section = SimpleNamespace(
            visible=_make_visible_role("school_admin"),
            elements=[
                SimpleNamespace(field_name="title", visible=None),
                SimpleNamespace(field_name="priority", visible=_make_visible_role("teacher")),
            ],
        )
        surface = SimpleNamespace(sections=[section])
        columns = _build_surface_columns(entity, surface)

        col_map = {c["key"]: c for c in columns}
        assert col_map["title"]["visible_condition"]["role_check"]["role_name"] == "school_admin"
        assert col_map["priority"]["visible_condition"]["role_check"]["role_name"] == "teacher"


# ---------------------------------------------------------------------------
# Surface UX Metadata on WorkspaceRegionContext (#362)
# ---------------------------------------------------------------------------


class TestWorkspaceRegionContextUXMetadata:
    """WorkspaceRegionContext should carry surface UX sort and empty_message."""

    def test_default_sort_stored(self) -> None:
        """surface_default_sort should store SortSpec-like objects."""
        from dazzle.http.runtime.workspace_context import WorkspaceRegionContext

        sort_specs = [SimpleNamespace(field="due_date", direction="desc")]
        ctx = WorkspaceRegionContext(
            ctx_region=SimpleNamespace(
                display="LIST",
                limit=None,
                empty_message="No data available.",
                aggregates={},
                group_by="",
                template="workspace/regions/_typed_primitive.html",
                title="Tasks",
                name="tasks",
                endpoint="/api/workspaces/dash/regions/tasks",
                action_url="",
                source_tabs=[],
            ),
            ir_region=SimpleNamespace(sort=[], filter=None),
            source="Task",
            entity_spec=None,
            attention_signals=[],
            ws_access=None,
            repositories={},
            require_auth=False,
            auth_middleware=None,
            surface_default_sort=sort_specs,
        )
        assert ctx.surface_default_sort == sort_specs
        assert ctx.surface_default_sort[0].field == "due_date"
        assert ctx.surface_default_sort[0].direction == "desc"

    def test_empty_message_stored(self) -> None:
        """surface_empty_message should store the surface's empty message."""
        from dazzle.http.runtime.workspace_context import WorkspaceRegionContext

        ctx = WorkspaceRegionContext(
            ctx_region=SimpleNamespace(
                display="LIST",
                limit=None,
                empty_message="No data available.",
                aggregates={},
                group_by="",
                template="workspace/regions/_typed_primitive.html",
                title="Tasks",
                name="tasks",
                endpoint="/api/workspaces/dash/regions/tasks",
                action_url="",
                source_tabs=[],
            ),
            ir_region=SimpleNamespace(sort=[], filter=None),
            source="Task",
            entity_spec=None,
            attention_signals=[],
            ws_access=None,
            repositories={},
            require_auth=False,
            auth_middleware=None,
            surface_empty_message="No tasks assigned yet.",
        )
        assert ctx.surface_empty_message == "No tasks assigned yet."

    def test_defaults_when_not_provided(self) -> None:
        """Default values should be empty list/string when not provided."""
        from dazzle.http.runtime.workspace_context import WorkspaceRegionContext

        ctx = WorkspaceRegionContext(
            ctx_region=SimpleNamespace(
                display="LIST",
                limit=None,
                empty_message="fallback",
                aggregates={},
                group_by="",
                template="workspace/regions/_typed_primitive.html",
                title="T",
                name="t",
                endpoint="",
                action_url="",
                source_tabs=[],
            ),
            ir_region=SimpleNamespace(sort=[], filter=None),
            source="Task",
            entity_spec=None,
            attention_signals=[],
            ws_access=None,
            repositories={},
            require_auth=False,
            auth_middleware=None,
        )
        assert ctx.surface_default_sort == []
        assert ctx.surface_empty_message == ""


# ===========================================================================
# TestViewportLazyLoading (#378)
# ===========================================================================


class TestViewportLazyLoading:
    """Regions below the fold use intersect-based lazy loading (#378)."""

    @pytest.mark.parametrize(
        ("stage", "expected"),
        [
            (None, 3),
            ("command_center", 6),
            ("monitor_wall", 6),
            ("scanner_table", 2),
            ("dual_pane_flow", 4),
        ],
        ids=[
            "test_fold_count_default",
            "test_fold_count_command_center",
            "test_fold_count_monitor_wall",
            "test_fold_count_scanner_table",
            "test_fold_count_dual_pane",
        ],
    )
    def test_fold_count(self, stage, expected) -> None:
        from dazzle.core.ir.workspaces import WorkspaceSpec
        from dazzle.page.runtime.workspace_renderer import build_workspace_context

        kwargs = {"name": "dashboard", "regions": []}
        if stage is not None:
            kwargs["stage"] = stage
        ws = WorkspaceSpec(**kwargs)
        ctx = build_workspace_context(ws)
        assert ctx.fold_count == expected

    def test_stage_fold_count_map_keys(self) -> None:
        """All stages in STAGE_DEFAULT_SPANS have a corresponding fold count."""
        from dazzle.page.runtime.workspace_renderer import STAGE_DEFAULT_SPANS, STAGE_FOLD_COUNTS

        for stage in STAGE_DEFAULT_SPANS:
            assert stage in STAGE_FOLD_COUNTS, f"Missing fold count for stage: {stage}"


# ===========================================================================
# Test mode current_user resolution (#483)
# ===========================================================================


class TestCurrentUserTestMode:
    """Test that current_user is resolved even with require_auth=False (#483)."""

    def test_guard_condition_allows_auth_resolution_without_require_auth(self) -> None:
        """The guard for current_user resolution checks auth_middleware, not require_auth.

        Previously the guard was ``if ctx.require_auth and ctx.auth_middleware``,
        which skipped user resolution entirely in test mode.  After #483 the guard
        is just ``if ctx.auth_middleware``.

        v0.67.110 (#1057 cut 11): the guard moved to
        ``workspace_region_prelude.resolve_request_user_context``. Same
        invariant, new home.
        """
        import ast
        import inspect
        import textwrap

        from dazzle.http.runtime.workspace_region_prelude import (
            resolve_request_user_context,
        )

        source = textwrap.dedent(inspect.getsource(resolve_request_user_context))
        tree = ast.parse(source)

        # Walk the AST looking for `if ctx.auth_middleware:` without `ctx.require_auth`
        found_guard = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test_src = ast.dump(node.test)
                # The guard should reference auth_middleware but NOT require_auth
                if "auth_middleware" in test_src and "require_auth" not in test_src:
                    found_guard = True
                    break
                # Fail if we still see the old combined guard
                if "require_auth" in test_src and "auth_middleware" in test_src:
                    raise AssertionError(
                        "Guard still combines require_auth and auth_middleware — "
                        "current_user won't resolve in test mode"
                    )

        assert found_guard, (
            "Could not find `if ctx.auth_middleware:` guard in _workspace_region_handler"
        )

    def test_user_entity_lookup_handles_dict_result(self) -> None:
        """Repository.list() returns a dict, not an object — ensure dict access works (#484).

        The code must use dict-style access (result.get("items")) rather than
        attribute access (result.items) since Repository.list() returns a plain dict.
        """
        import inspect
        import textwrap

        from dazzle.http.runtime.workspace_user import _resolve_workspace_user

        source = textwrap.dedent(inspect.getsource(_resolve_workspace_user))

        # The old buggy pattern: `_user_result.items if hasattr(...)` confuses
        # dict.items (the method) with the "items" key in the result dict.
        assert "_user_result.items if hasattr" not in source, (
            "Still using attribute-style access on dict return from repository.list() — "
            "use user_result.get('items', []) instead"
        )
        # Verify the fix is present
        assert 'user_result.get("items"' in source or "user_result.get('items'" in source, (
            "Expected dict-style access user_result.get('items') for repository.list() result"
        )

    def test_user_entity_stored_in_filter_context(self) -> None:
        """Verify the resolved User entity record is stored in filter context (#486).

        This is needed so that current_user.<field> dot-notation can resolve
        fields from the User entity (e.g. current_user.department).
        """
        import inspect
        import textwrap

        from dazzle.http.runtime.workspace_region_handler import _workspace_region_handler
        from dazzle.http.runtime.workspace_user import _resolve_workspace_user

        handler_source = textwrap.dedent(inspect.getsource(_workspace_region_handler))
        helper_source = textwrap.dedent(inspect.getsource(_resolve_workspace_user))

        assert "current_user_entity" in handler_source or "entity_dict" in helper_source, (
            "Must store user entity record in filter context as 'current_user_entity' "
            "for current_user.<field> dot-notation resolution"
        )

    def test_resolve_workspace_user_uses_entity_name_param(self) -> None:
        """_resolve_workspace_user must use user_entity_name, not hardcoded 'User' (#588).

        When the DSL user entity is named something other than 'User'
        (e.g. 'Student'), the function must look up that entity name
        in the repositories dict.
        """
        import inspect
        import textwrap

        from dazzle.http.runtime.workspace_user import _resolve_workspace_user

        source = textwrap.dedent(inspect.getsource(_resolve_workspace_user))

        # Must accept user_entity_name parameter
        assert "user_entity_name" in source, (
            "_resolve_workspace_user must accept user_entity_name parameter "
            "to support non-'User' entity names (#588)"
        )
        # Must use the parameter for repo lookup, not hardcoded "User"
        assert 'repositories.get("User")' not in source, (
            "_resolve_workspace_user must use user_entity_name param for repo lookup, "
            "not hardcoded 'User' (#588)"
        )
        assert "repositories.get(user_entity_name)" in source, (
            "_resolve_workspace_user must look up repositories.get(user_entity_name)"
        )


class TestCurrentUserDotNotation:
    """Tests for current_user.<field> dot-notation in condition evaluator (#486)."""

    def test_resolve_current_user_dot_notation(self) -> None:
        """current_user.<field> dot-notation: scalar, ref dict, plain, missing entity, missing field.

        Combined: department, department_ref_dict, plain_still_works, missing_entity, missing_field.
        """
        from dazzle.http.runtime.condition_evaluator import _resolve_value

        # Scalar field (uuid string)
        ctx_scalar = {
            "current_user_id": "user-123",
            "current_user_entity": {
                "id": "user-123",
                "department": "f6ac5054-79ff-5b1a-acd0-f1c832d3433b",
            },
        }
        assert (
            _resolve_value({"literal": "current_user.department"}, ctx_scalar)
            == "f6ac5054-79ff-5b1a-acd0-f1c832d3433b"
        )

        # Ref dict — extract id from {id, name}
        ctx_ref = {
            "current_user_id": "user-123",
            "current_user_entity": {
                "id": "user-123",
                "department": {
                    "id": "f6ac5054-79ff-5b1a-acd0-f1c832d3433b",
                    "name": "English",
                },
            },
        }
        assert (
            _resolve_value({"literal": "current_user.department"}, ctx_ref)
            == "f6ac5054-79ff-5b1a-acd0-f1c832d3433b"
        )

        # Plain current_user (no dot) → user_id
        assert (
            _resolve_value({"literal": "current_user"}, {"current_user_id": "user-123"})
            == "user-123"
        )

        # Missing entity → None
        assert (
            _resolve_value({"literal": "current_user.department"}, {"current_user_id": "user-123"})
            is None
        )

        # Missing field on entity → None
        ctx_missing_field = {
            "current_user_id": "user-123",
            "current_user_entity": {"id": "user-123", "name": "Alice"},
        }
        assert _resolve_value({"literal": "current_user.department"}, ctx_missing_field) is None

    def test_condition_to_sql_filter_with_dot_notation(self) -> None:
        """condition_to_sql_filter resolves current_user.department in filters."""
        from dazzle.http.runtime.condition_evaluator import condition_to_sql_filter

        condition = {
            "comparison": {
                "field": "department",
                "operator": "eq",
                "value": {"literal": "current_user.department"},
            }
        }
        context = {
            "current_user_id": "user-123",
            "current_user_entity": {
                "id": "user-123",
                "department": "dept-456",
            },
        }
        filters = condition_to_sql_filter(condition, context)
        assert filters == {"department": "dept-456"}

    def test_identifier_kind_dot_notation(self) -> None:
        """Handle current_user.field via identifier kind value format."""
        from dazzle.http.runtime.condition_evaluator import _resolve_value

        context = {
            "current_user_id": "user-123",
            "current_user_entity": {"id": "user-123", "team_id": "team-789"},
        }
        value = {"kind": "identifier", "value": "current_user.team_id"}
        result = _resolve_value(value, context)
        assert result == "team-789"


# ===========================================================================
# Workspace stats endpoint (#783)
# ===========================================================================


class TestWorkspaceStatsHandler:
    """_workspace_stats_handler computes region aggregates as standalone JSON."""

    def _make_ctx(
        self,
        *,
        region_name: str,
        aggregates: dict[str, str],
        repositories: dict[str, Any] | None = None,
        endpoint: str = "/api/workspaces/dash/regions/r",
        require_auth: bool = False,
        ws_access: Any = None,
        auth_middleware: Any = None,
    ) -> Any:
        from dazzle.http.runtime.workspace_context import WorkspaceRegionContext

        return WorkspaceRegionContext(
            ctx_region=SimpleNamespace(
                display="LIST",
                limit=None,
                empty_message="",
                aggregates=aggregates,
                group_by="",
                template="workspace/regions/_typed_primitive.html",
                title=region_name.title(),
                name=region_name,
                endpoint=endpoint,
                action_url="",
                source_tabs=[],
            ),
            ir_region=SimpleNamespace(sort=[], filter=None),
            source="Task",
            entity_spec=None,
            attention_signals=[],
            ws_access=ws_access,
            repositories=repositories or {},
            require_auth=require_auth,
            auth_middleware=auth_middleware,
        )

    async def test_returns_empty_stats_when_no_aggregates(self) -> None:
        from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

        ctx = self._make_ctx(region_name="tasks", aggregates={})
        result = await _workspace_stats_handler(SimpleNamespace(query_params={}), [ctx])
        assert result == {"workspace": "dash", "stats": {}}

    async def test_computes_count_entity_aggregates(self) -> None:
        from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

        class FakeRepo:
            async def list(self, *, page: int, page_size: int, filters: Any = None) -> Any:
                return {"items": [], "total": 42}

        ctx = self._make_ctx(
            region_name="overview",
            aggregates={"total_work": AggregateRef(func="count", entity="Work")},
            repositories={"Work": FakeRepo()},
        )
        result = await _workspace_stats_handler(SimpleNamespace(query_params={}), [ctx])
        assert result["workspace"] == "dash"
        assert result["stats"] == {"overview": {"Total Work": 42}}

    async def test_namespaces_stats_by_region(self) -> None:
        from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

        class FakeRepo:
            def __init__(self, total: int) -> None:
                self._total = total

            async def list(self, *, page: int, page_size: int, filters: Any = None) -> Any:
                return {"items": [], "total": self._total}

        ctx1 = self._make_ctx(
            region_name="kpis",
            aggregates={"active_works": AggregateRef(func="count", entity="Work")},
            repositories={"Work": FakeRepo(10)},
        )
        ctx2 = self._make_ctx(
            region_name="campaigns",
            aggregates={"running": AggregateRef(func="count", entity="Campaign")},
            repositories={"Campaign": FakeRepo(3)},
        )
        result = await _workspace_stats_handler(SimpleNamespace(query_params={}), [ctx1, ctx2])
        assert result["stats"]["kpis"] == {"Active Works": 10}
        assert result["stats"]["campaigns"] == {"Running": 3}

    async def test_skips_regions_without_aggregates(self) -> None:
        from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

        class FakeRepo:
            async def list(self, *, page: int, page_size: int, filters: Any = None) -> Any:
                return {"items": [], "total": 5}

        plain = self._make_ctx(region_name="plain", aggregates={})
        with_agg = self._make_ctx(
            region_name="with_agg",
            aggregates={"n": AggregateRef(func="count", entity="Task")},
            repositories={"Task": FakeRepo()},
        )
        result = await _workspace_stats_handler(SimpleNamespace(query_params={}), [plain, with_agg])
        assert "plain" not in result["stats"]
        assert result["stats"]["with_agg"] == {"N": 5}

    async def test_requires_auth_when_configured(self) -> None:
        from fastapi import HTTPException

        from dazzle.http.runtime.workspace_handlers import _workspace_stats_handler

        class FailingAuth:
            def get_auth_context(self, request: Any) -> Any:
                return SimpleNamespace(is_authenticated=False, user=None, roles=[])

        ctx = self._make_ctx(
            region_name="kpis",
            aggregates={"n": AggregateRef(func="count", entity="Task")},
            require_auth=True,
            auth_middleware=FailingAuth(),
        )
        try:
            await _workspace_stats_handler(SimpleNamespace(query_params={}), [ctx])
        except HTTPException as e:
            assert e.status_code == 401
        else:
            raise AssertionError("Expected 401 HTTPException")
