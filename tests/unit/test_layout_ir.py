"""Tests for UI Semantic Layout IR types."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir import (
    AttentionSignalKind,
    LayoutPlan,
    LayoutSignal,
    LayoutSurface,
    PersonaLayout,
    Stage,
    WorkspaceLayout,
)


class TestLayoutSignal:
    """Tests for LayoutSignal model."""

    def test_layout_signal_combined(self):
        """Combined: basic creation (defaults), all fields, weight validation
        (0.0-1.0), urgency/interaction_frequency/density_preference/mode
        validations, immutability."""
        # Basic creation + defaults
        s = LayoutSignal(
            id="task_count",
            kind=AttentionSignalKind.KPI,
            label="Active Tasks",
            source="Task",
        )
        assert s.id == "task_count"
        assert s.kind == AttentionSignalKind.KPI
        assert s.label == "Active Tasks"
        assert s.source == "Task"
        assert s.attention_weight == 0.5
        assert s.urgency == "medium"
        assert s.interaction_frequency == "occasional"

        # All fields
        s2 = LayoutSignal(
            id="urgent_alerts",
            kind=AttentionSignalKind.ALERT_FEED,
            label="Urgent Alerts",
            source="Alert",
            attention_weight=0.9,
            urgency="high",
            interaction_frequency="frequent",
            density_preference="compact",
            mode="act",
            constraints={"max_items": 10},
        )
        assert s2.attention_weight == 0.9
        assert s2.urgency == "high"
        assert s2.interaction_frequency == "frequent"
        assert s2.density_preference == "compact"
        assert s2.mode == "act"
        assert s2.constraints == {"max_items": 10}

        base_kwargs = {
            "id": "t",
            "kind": AttentionSignalKind.KPI,
            "label": "Test",
            "source": "Entity",
        }

        # Attention weight bounds
        LayoutSignal(**base_kwargs, attention_weight=0.0)
        LayoutSignal(**base_kwargs, attention_weight=1.0)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, attention_weight=-0.1)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, attention_weight=1.1)

        # Urgency
        for u in ("low", "medium", "high"):
            LayoutSignal(**base_kwargs, urgency=u)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, urgency="critical")

        # Interaction frequency
        for f in ("rare", "occasional", "frequent"):
            LayoutSignal(**base_kwargs, interaction_frequency=f)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, interaction_frequency="never")

        # Density preference
        for d in ("compact", "comfortable", "spacious"):
            LayoutSignal(**base_kwargs, density_preference=d)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, density_preference="dense")

        # Mode
        for m in ("read", "act", "configure"):
            LayoutSignal(**base_kwargs, mode=m)
        with pytest.raises(ValidationError):
            LayoutSignal(**base_kwargs, mode="edit")

        # Immutability
        immut = LayoutSignal(**base_kwargs)
        with pytest.raises((ValidationError, AttributeError)):
            immut.attention_weight = 0.8


class TestWorkspaceLayout:
    """Tests for WorkspaceLayout model."""

    def test_workspace_layout_combined(self):
        """Combined: creation defaults, with-signals, attention_budget bounds,
        time_horizon validation, immutability."""
        # Defaults
        w = WorkspaceLayout(id="dashboard", label="Main Dashboard")
        assert w.id == "dashboard"
        assert w.label == "Main Dashboard"
        assert w.persona_targets == []
        assert w.attention_budget == 1.0
        assert w.time_horizon == "daily"
        assert w.stage is None
        assert w.attention_signals == []

        # With signals
        signals = [
            LayoutSignal(id="kpi1", kind=AttentionSignalKind.KPI, label="KPI 1", source="Entity1"),
            LayoutSignal(
                id="table1", kind=AttentionSignalKind.TABLE, label="Table 1", source="Entity2"
            ),
        ]
        w2 = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            persona_targets=["admin", "manager"],
            attention_budget=1.2,
            time_horizon="realtime",
            stage="monitor_wall",
            attention_signals=signals,
        )
        assert w2.persona_targets == ["admin", "manager"]
        assert w2.attention_budget == 1.2
        assert w2.time_horizon == "realtime"
        assert w2.stage == "monitor_wall"
        assert len(w2.attention_signals) == 2

        # Attention budget bounds
        WorkspaceLayout(id="t", label="T", attention_budget=0.0)
        WorkspaceLayout(id="t", label="T", attention_budget=1.5)
        with pytest.raises(ValidationError):
            WorkspaceLayout(id="t", label="T", attention_budget=-0.1)
        with pytest.raises(ValidationError):
            WorkspaceLayout(id="t", label="T", attention_budget=1.6)

        # Time horizon
        for h in ("realtime", "daily", "archival"):
            WorkspaceLayout(id="t", label="T", time_horizon=h)
        with pytest.raises(ValidationError):
            WorkspaceLayout(id="t", label="T", time_horizon="monthly")

        # Immutability
        immut = WorkspaceLayout(id="t", label="T")
        with pytest.raises((ValidationError, AttributeError)):
            immut.attention_budget = 1.5


class TestPersonaLayout:
    """Tests for PersonaLayout model."""

    def test_persona_layout_combined(self):
        """Combined: creation defaults, all fields, proficiency_level
        validation, session_style validation, immutability."""
        # Defaults
        p = PersonaLayout(id="admin", label="Administrator")
        assert p.id == "admin"
        assert p.label == "Administrator"
        assert p.goals == []
        assert p.proficiency_level == "intermediate"
        assert p.session_style == "deep_work"
        assert p.attention_biases == {}

        # All fields
        p2 = PersonaLayout(
            id="power_user",
            label="Power User",
            goals=["monitor_metrics", "quick_actions"],
            proficiency_level="expert",
            session_style="glance",
            attention_biases={"kpi": 1.5, "table": 0.8},
        )
        assert p2.goals == ["monitor_metrics", "quick_actions"]
        assert p2.proficiency_level == "expert"
        assert p2.session_style == "glance"
        assert p2.attention_biases == {"kpi": 1.5, "table": 0.8}

        # Proficiency level
        for level in ("novice", "intermediate", "expert"):
            PersonaLayout(id="t", label="T", proficiency_level=level)
        with pytest.raises(ValidationError):
            PersonaLayout(id="t", label="T", proficiency_level="advanced")

        # Session style
        for style in ("glance", "deep_work"):
            PersonaLayout(id="t", label="T", session_style=style)
        with pytest.raises(ValidationError):
            PersonaLayout(id="t", label="T", session_style="focused")

        # Immutability
        immut = PersonaLayout(id="t", label="T")
        with pytest.raises((ValidationError, AttributeError)):
            immut.proficiency_level = "expert"


class TestLayoutSurface:
    """Tests for LayoutSurface model."""

    def test_layout_surface_combined(self):
        """Combined: creation defaults, with-signals, capacity validation,
        priority validation, immutability."""
        # Defaults
        s = LayoutSurface(id="primary", stage=Stage.SCANNER_TABLE)
        assert s.id == "primary"
        assert s.stage == Stage.SCANNER_TABLE
        assert s.capacity == 1.0
        assert s.priority == 1
        assert s.assigned_signals == []
        assert s.constraints == {}

        # With signals
        s2 = LayoutSurface(
            id="sidebar",
            stage=Stage.MONITOR_WALL,
            capacity=0.5,
            priority=2,
            assigned_signals=["signal1", "signal2"],
            constraints={"max_width": 300},
        )
        assert s2.capacity == 0.5
        assert s2.priority == 2
        assert s2.assigned_signals == ["signal1", "signal2"]
        assert s2.constraints == {"max_width": 300}

        # Capacity bounds
        LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, capacity=0.0)
        LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, capacity=2.0)
        with pytest.raises(ValidationError):
            LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, capacity=-0.1)

        # Priority bounds
        LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, priority=1)
        LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, priority=10)
        with pytest.raises(ValidationError):
            LayoutSurface(id="t", stage=Stage.FOCUS_METRIC, priority=0)

        # Immutability
        immut = LayoutSurface(id="t", stage=Stage.FOCUS_METRIC)
        with pytest.raises((ValidationError, AttributeError)):
            immut.capacity = 2.0


class TestLayoutPlan:
    """Tests for LayoutPlan model."""

    def test_layout_plan_combined(self):
        """Combined: creation defaults, all-fields with surfaces, immutability."""
        # Defaults
        p = LayoutPlan(workspace_id="dashboard", stage=Stage.MONITOR_WALL)
        assert p.workspace_id == "dashboard"
        assert p.persona_id is None
        assert p.stage == Stage.MONITOR_WALL
        assert p.surfaces == []
        assert p.over_budget_signals == []
        assert p.warnings == []
        assert p.metadata == {}

        # All fields
        surfaces = [
            LayoutSurface(id="primary", stage=Stage.MONITOR_WALL, assigned_signals=["signal1"]),
            LayoutSurface(id="sidebar", stage=Stage.MONITOR_WALL, assigned_signals=["signal2"]),
        ]
        p2 = LayoutPlan(
            workspace_id="dashboard",
            persona_id="admin",
            stage=Stage.MONITOR_WALL,
            surfaces=surfaces,
            over_budget_signals=["signal3"],
            warnings=["Attention budget exceeded by 0.2"],
            metadata={"selection_score": 0.85},
        )
        assert p2.persona_id == "admin"
        assert len(p2.surfaces) == 2
        assert p2.over_budget_signals == ["signal3"]
        assert len(p2.warnings) == 1
        assert p2.metadata["selection_score"] == 0.85

        # Immutability
        immut = LayoutPlan(workspace_id="t", stage=Stage.FOCUS_METRIC)
        with pytest.raises((ValidationError, AttributeError)):
            immut.stage = Stage.SCANNER_TABLE


class TestLayoutArchetype:
    """Tests for Stage enum."""

    def test_archetype_combined(self):
        """Combined: all archetypes defined + individual values."""
        expected = {
            "focus_metric",
            "scanner_table",
            "dual_pane_flow",
            "monitor_wall",
            "command_center",
        }
        assert {a.value for a in Stage} == expected
        assert Stage.FOCUS_METRIC.value == "focus_metric"
        assert Stage.SCANNER_TABLE.value == "scanner_table"
        assert Stage.DUAL_PANE_FLOW.value == "dual_pane_flow"
        assert Stage.MONITOR_WALL.value == "monitor_wall"
        assert Stage.COMMAND_CENTER.value == "command_center"


class TestAttentionSignalKind:
    """Tests for LayoutSignalKind enum."""

    def test_signal_kind_combined(self):
        """Combined: all expected kinds defined + individual kind values."""
        expected = {
            "kpi",
            "alert_feed",
            "table",
            "item_list",
            "detail_view",
            "task_list",
            "form",
            "chart",
            "search",
            "filter",
        }
        assert {k.value for k in AttentionSignalKind} == expected
        assert AttentionSignalKind.KPI.value == "kpi"
        assert AttentionSignalKind.TABLE.value == "table"
        assert AttentionSignalKind.FORM.value == "form"
        assert AttentionSignalKind.CHART.value == "chart"
