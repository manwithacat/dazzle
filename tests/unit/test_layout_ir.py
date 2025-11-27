"""Tests for UI Semantic Layout IR types."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir import (
    AttentionSignal,
    AttentionSignalKind,
    LayoutArchetype,
    LayoutPlan,
    LayoutSurface,
    PersonaLayout,
    WorkspaceLayout,
)


class TestAttentionSignal:
    """Tests for AttentionSignal model."""

    def test_attention_signal_creation(self):
        """Test creating a basic attention signal."""
        signal = AttentionSignal(
            id="task_count",
            kind=AttentionSignalKind.KPI,
            label="Active Tasks",
            source="Task",
        )

        assert signal.id == "task_count"
        assert signal.kind == AttentionSignalKind.KPI
        assert signal.label == "Active Tasks"
        assert signal.source == "Task"
        assert signal.attention_weight == 0.5  # default
        assert signal.urgency == "medium"  # default
        assert signal.interaction_frequency == "occasional"  # default

    def test_attention_signal_with_all_fields(self):
        """Test creating signal with all fields specified."""
        signal = AttentionSignal(
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

        assert signal.attention_weight == 0.9
        assert signal.urgency == "high"
        assert signal.interaction_frequency == "frequent"
        assert signal.density_preference == "compact"
        assert signal.mode == "act"
        assert signal.constraints == {"max_items": 10}

    def test_attention_weight_validation(self):
        """Test attention weight must be 0.0-1.0."""
        # Valid weights
        AttentionSignal(
            id="test1",
            kind=AttentionSignalKind.KPI,
            label="Test",
            source="Entity",
            attention_weight=0.0,
        )
        AttentionSignal(
            id="test2",
            kind=AttentionSignalKind.KPI,
            label="Test",
            source="Entity",
            attention_weight=1.0,
        )

        # Invalid weights
        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                attention_weight=-0.1,
            )

        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                attention_weight=1.1,
            )

    def test_urgency_validation(self):
        """Test urgency must be low/medium/high."""
        # Valid urgencies
        for urgency in ("low", "medium", "high"):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                urgency=urgency,
            )

        # Invalid urgency
        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                urgency="critical",
            )

    def test_interaction_frequency_validation(self):
        """Test interaction frequency must be rare/occasional/frequent."""
        # Valid frequencies
        for freq in ("rare", "occasional", "frequent"):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                interaction_frequency=freq,
            )

        # Invalid frequency
        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                interaction_frequency="never",
            )

    def test_density_preference_validation(self):
        """Test density preference must be compact/comfortable/spacious."""
        # Valid preferences
        for pref in ("compact", "comfortable", "spacious"):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                density_preference=pref,
            )

        # Invalid preference
        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                density_preference="dense",
            )

    def test_mode_validation(self):
        """Test mode must be read/act/configure."""
        # Valid modes
        for mode in ("read", "act", "configure"):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                mode=mode,
            )

        # Invalid mode
        with pytest.raises(ValidationError):
            AttentionSignal(
                id="test",
                kind=AttentionSignalKind.KPI,
                label="Test",
                source="Entity",
                mode="edit",
            )

    def test_immutability(self):
        """Test that AttentionSignal is immutable."""
        signal = AttentionSignal(
            id="test", kind=AttentionSignalKind.KPI, label="Test", source="Entity"
        )

        with pytest.raises((ValidationError, AttributeError)):
            signal.attention_weight = 0.8


class TestWorkspaceLayout:
    """Tests for WorkspaceLayout model."""

    def test_workspace_layout_creation(self):
        """Test creating a basic workspace layout."""
        workspace = WorkspaceLayout(id="dashboard", label="Main Dashboard")

        assert workspace.id == "dashboard"
        assert workspace.label == "Main Dashboard"
        assert workspace.persona_targets == []
        assert workspace.attention_budget == 1.0  # default
        assert workspace.time_horizon == "daily"  # default
        assert workspace.engine_hint is None
        assert workspace.attention_signals == []

    def test_workspace_layout_with_signals(self):
        """Test workspace with attention signals."""
        signals = [
            AttentionSignal(
                id="kpi1", kind=AttentionSignalKind.KPI, label="KPI 1", source="Entity1"
            ),
            AttentionSignal(
                id="table1",
                kind=AttentionSignalKind.TABLE,
                label="Table 1",
                source="Entity2",
            ),
        ]

        workspace = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            persona_targets=["admin", "manager"],
            attention_budget=1.2,
            time_horizon="realtime",
            engine_hint="monitor_wall",
            attention_signals=signals,
        )

        assert workspace.persona_targets == ["admin", "manager"]
        assert workspace.attention_budget == 1.2
        assert workspace.time_horizon == "realtime"
        assert workspace.engine_hint == "monitor_wall"
        assert len(workspace.attention_signals) == 2

    def test_attention_budget_validation(self):
        """Test attention budget must be 0.0-1.5."""
        # Valid budgets
        WorkspaceLayout(id="test", label="Test", attention_budget=0.0)
        WorkspaceLayout(id="test", label="Test", attention_budget=1.5)

        # Invalid budgets
        with pytest.raises(ValidationError):
            WorkspaceLayout(id="test", label="Test", attention_budget=-0.1)

        with pytest.raises(ValidationError):
            WorkspaceLayout(id="test", label="Test", attention_budget=1.6)

    def test_time_horizon_validation(self):
        """Test time horizon must be realtime/daily/archival."""
        # Valid horizons
        for horizon in ("realtime", "daily", "archival"):
            WorkspaceLayout(id="test", label="Test", time_horizon=horizon)

        # Invalid horizon
        with pytest.raises(ValidationError):
            WorkspaceLayout(id="test", label="Test", time_horizon="monthly")

    def test_immutability(self):
        """Test that WorkspaceLayout is immutable."""
        workspace = WorkspaceLayout(id="test", label="Test")

        with pytest.raises((ValidationError, AttributeError)):
            workspace.attention_budget = 1.5


class TestPersonaLayout:
    """Tests for PersonaLayout model."""

    def test_persona_layout_creation(self):
        """Test creating a basic persona layout."""
        persona = PersonaLayout(id="admin", label="Administrator")

        assert persona.id == "admin"
        assert persona.label == "Administrator"
        assert persona.goals == []
        assert persona.proficiency_level == "intermediate"  # default
        assert persona.session_style == "deep_work"  # default
        assert persona.attention_biases == {}

    def test_persona_layout_with_all_fields(self):
        """Test persona with all fields specified."""
        persona = PersonaLayout(
            id="power_user",
            label="Power User",
            goals=["monitor_metrics", "quick_actions"],
            proficiency_level="expert",
            session_style="glance",
            attention_biases={"kpi": 1.5, "table": 0.8},
        )

        assert persona.goals == ["monitor_metrics", "quick_actions"]
        assert persona.proficiency_level == "expert"
        assert persona.session_style == "glance"
        assert persona.attention_biases == {"kpi": 1.5, "table": 0.8}

    def test_proficiency_level_validation(self):
        """Test proficiency level must be novice/intermediate/expert."""
        # Valid levels
        for level in ("novice", "intermediate", "expert"):
            PersonaLayout(id="test", label="Test", proficiency_level=level)

        # Invalid level
        with pytest.raises(ValidationError):
            PersonaLayout(id="test", label="Test", proficiency_level="advanced")

    def test_session_style_validation(self):
        """Test session style must be glance/deep_work."""
        # Valid styles
        for style in ("glance", "deep_work"):
            PersonaLayout(id="test", label="Test", session_style=style)

        # Invalid style
        with pytest.raises(ValidationError):
            PersonaLayout(id="test", label="Test", session_style="focused")

    def test_immutability(self):
        """Test that PersonaLayout is immutable."""
        persona = PersonaLayout(id="test", label="Test")

        with pytest.raises((ValidationError, AttributeError)):
            persona.proficiency_level = "expert"


class TestLayoutSurface:
    """Tests for LayoutSurface model."""

    def test_layout_surface_creation(self):
        """Test creating a basic layout surface."""
        surface = LayoutSurface(id="primary", archetype=LayoutArchetype.SCANNER_TABLE)

        assert surface.id == "primary"
        assert surface.archetype == LayoutArchetype.SCANNER_TABLE
        assert surface.capacity == 1.0  # default
        assert surface.priority == 1  # default
        assert surface.assigned_signals == []
        assert surface.constraints == {}

    def test_layout_surface_with_signals(self):
        """Test surface with assigned signals."""
        surface = LayoutSurface(
            id="sidebar",
            archetype=LayoutArchetype.MONITOR_WALL,
            capacity=0.5,
            priority=2,
            assigned_signals=["signal1", "signal2"],
            constraints={"max_width": 300},
        )

        assert surface.capacity == 0.5
        assert surface.priority == 2
        assert surface.assigned_signals == ["signal1", "signal2"]
        assert surface.constraints == {"max_width": 300}

    def test_capacity_validation(self):
        """Test capacity must be >= 0.0."""
        # Valid capacities
        LayoutSurface(
            id="test", archetype=LayoutArchetype.FOCUS_METRIC, capacity=0.0
        )
        LayoutSurface(
            id="test", archetype=LayoutArchetype.FOCUS_METRIC, capacity=2.0
        )

        # Invalid capacity
        with pytest.raises(ValidationError):
            LayoutSurface(
                id="test", archetype=LayoutArchetype.FOCUS_METRIC, capacity=-0.1
            )

    def test_priority_validation(self):
        """Test priority must be >= 1."""
        # Valid priorities
        LayoutSurface(id="test", archetype=LayoutArchetype.FOCUS_METRIC, priority=1)
        LayoutSurface(id="test", archetype=LayoutArchetype.FOCUS_METRIC, priority=10)

        # Invalid priority
        with pytest.raises(ValidationError):
            LayoutSurface(id="test", archetype=LayoutArchetype.FOCUS_METRIC, priority=0)

    def test_immutability(self):
        """Test that LayoutSurface is immutable."""
        surface = LayoutSurface(id="test", archetype=LayoutArchetype.FOCUS_METRIC)

        with pytest.raises((ValidationError, AttributeError)):
            surface.capacity = 2.0


class TestLayoutPlan:
    """Tests for LayoutPlan model."""

    def test_layout_plan_creation(self):
        """Test creating a basic layout plan."""
        plan = LayoutPlan(
            workspace_id="dashboard", archetype=LayoutArchetype.MONITOR_WALL
        )

        assert plan.workspace_id == "dashboard"
        assert plan.persona_id is None
        assert plan.archetype == LayoutArchetype.MONITOR_WALL
        assert plan.surfaces == []
        assert plan.over_budget_signals == []
        assert plan.warnings == []
        assert plan.metadata == {}

    def test_layout_plan_with_all_fields(self):
        """Test plan with all fields specified."""
        surfaces = [
            LayoutSurface(
                id="primary",
                archetype=LayoutArchetype.MONITOR_WALL,
                assigned_signals=["signal1"],
            ),
            LayoutSurface(
                id="sidebar",
                archetype=LayoutArchetype.MONITOR_WALL,
                assigned_signals=["signal2"],
            ),
        ]

        plan = LayoutPlan(
            workspace_id="dashboard",
            persona_id="admin",
            archetype=LayoutArchetype.MONITOR_WALL,
            surfaces=surfaces,
            over_budget_signals=["signal3"],
            warnings=["Attention budget exceeded by 0.2"],
            metadata={"selection_score": 0.85},
        )

        assert plan.persona_id == "admin"
        assert len(plan.surfaces) == 2
        assert plan.over_budget_signals == ["signal3"]
        assert len(plan.warnings) == 1
        assert plan.metadata["selection_score"] == 0.85

    def test_immutability(self):
        """Test that LayoutPlan is immutable."""
        plan = LayoutPlan(
            workspace_id="test", archetype=LayoutArchetype.FOCUS_METRIC
        )

        with pytest.raises((ValidationError, AttributeError)):
            plan.archetype = LayoutArchetype.SCANNER_TABLE


class TestLayoutArchetype:
    """Tests for LayoutArchetype enum."""

    def test_all_archetypes_defined(self):
        """Test that all expected archetypes are defined."""
        expected = {
            "focus_metric",
            "scanner_table",
            "dual_pane_flow",
            "monitor_wall",
            "command_center",
        }
        actual = {a.value for a in LayoutArchetype}
        assert actual == expected

    def test_archetype_values(self):
        """Test individual archetype values."""
        assert LayoutArchetype.FOCUS_METRIC.value == "focus_metric"
        assert LayoutArchetype.SCANNER_TABLE.value == "scanner_table"
        assert LayoutArchetype.DUAL_PANE_FLOW.value == "dual_pane_flow"
        assert LayoutArchetype.MONITOR_WALL.value == "monitor_wall"
        assert LayoutArchetype.COMMAND_CENTER.value == "command_center"


class TestAttentionSignalKind:
    """Tests for AttentionSignalKind enum."""

    def test_all_signal_kinds_defined(self):
        """Test that all expected signal kinds are defined."""
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
        actual = {k.value for k in AttentionSignalKind}
        assert actual == expected

    def test_signal_kind_values(self):
        """Test individual signal kind values."""
        assert AttentionSignalKind.KPI.value == "kpi"
        assert AttentionSignalKind.TABLE.value == "table"
        assert AttentionSignalKind.FORM.value == "form"
        assert AttentionSignalKind.CHART.value == "chart"
