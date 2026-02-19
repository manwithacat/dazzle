"""Tests for UI semantic layout engine."""

from dazzle.core.ir import (
    AttentionSignalKind,
    LayoutArchetype,
    LayoutSignal,
    PersonaLayout,
    WorkspaceLayout,
)
from dazzle.ui.layout_engine import (
    ARCHETYPE_DEFINITIONS,
    build_layout_plan,
    select_stage,
)
from dazzle.ui.layout_engine.adjust import adjust_attention_for_persona
from dazzle.ui.layout_engine.allocate import assign_signals_to_surfaces
from dazzle.ui.layout_engine.archetypes import FOCUS_METRIC


class TestArchetypeSelection:
    """Tests for archetype selection logic."""

    def test_select_focus_metric_single_kpi(self):
        """Test that single high-weight KPI selects FOCUS_METRIC."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="Critical KPI",
                    source="Entity",
                    attention_weight=0.9,
                )
            ],
        )

        archetype = select_stage(workspace)
        assert archetype == LayoutArchetype.FOCUS_METRIC

    def test_select_scanner_table_single_table(self):
        """Test that single table selects SCANNER_TABLE."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="table1",
                    kind=AttentionSignalKind.TABLE,
                    label="Data Table",
                    source="Entity",
                    attention_weight=0.8,
                )
            ],
        )

        archetype = select_stage(workspace)
        assert archetype == LayoutArchetype.SCANNER_TABLE

    def test_select_monitor_wall_multiple_signals(self):
        """Test that multiple moderate signals select MONITOR_WALL."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI 1",
                    source="E1",
                    attention_weight=0.5,
                ),
                LayoutSignal(
                    id="kpi2",
                    kind=AttentionSignalKind.KPI,
                    label="KPI 2",
                    source="E2",
                    attention_weight=0.4,
                ),
                LayoutSignal(
                    id="chart1",
                    kind=AttentionSignalKind.CHART,
                    label="Chart",
                    source="E3",
                    attention_weight=0.3,
                ),
            ],
        )

        archetype = select_stage(workspace)
        assert archetype == LayoutArchetype.MONITOR_WALL

    def test_select_dual_pane_list_detail(self):
        """Test that list + detail selects DUAL_PANE_FLOW."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="list1",
                    kind=AttentionSignalKind.ITEM_LIST,
                    label="Item List",
                    source="E1",
                    attention_weight=0.6,
                ),
                LayoutSignal(
                    id="detail1",
                    kind=AttentionSignalKind.DETAIL_VIEW,
                    label="Detail",
                    source="E2",
                    attention_weight=0.6,
                ),
            ],
        )

        archetype = select_stage(workspace)
        assert archetype == LayoutArchetype.DUAL_PANE_FLOW

    def test_select_command_center_expert_many_signals(self):
        """Test that expert with many diverse signals gets COMMAND_CENTER."""
        # Create diverse signals (different kinds)
        signal_kinds = [
            AttentionSignalKind.KPI,
            AttentionSignalKind.TABLE,
            AttentionSignalKind.CHART,
            AttentionSignalKind.ALERT_FEED,
            AttentionSignalKind.TASK_LIST,
            AttentionSignalKind.SEARCH,
        ]
        signals = [
            LayoutSignal(
                id=f"signal{i}",
                kind=signal_kinds[i],
                label=f"Signal {i}",
                source="E",
                attention_weight=0.3,
            )
            for i in range(6)
        ]
        workspace = WorkspaceLayout(id="test", label="Test", attention_signals=signals)

        persona = PersonaLayout(id="expert", label="Expert", proficiency_level="expert")

        archetype = select_stage(workspace, persona)
        # With 6 diverse signals and expert persona → COMMAND_CENTER
        assert archetype == LayoutArchetype.COMMAND_CENTER

    def test_select_respects_stage(self):
        """Test that stage is respected."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            stage="scanner_table",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.9,
                )
            ],
        )

        archetype = select_stage(workspace)
        # Should respect hint even though signal profile suggests FOCUS_METRIC
        assert archetype == LayoutArchetype.SCANNER_TABLE

    def test_determinism_same_inputs_same_output(self):
        """Test that same inputs always produce same output."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.7,
                )
            ],
        )

        # Run selection multiple times
        results = [select_stage(workspace) for _ in range(10)]

        # All results should be identical
        assert len(set(results)) == 1
        assert results[0] == LayoutArchetype.FOCUS_METRIC


class TestSurfaceAllocation:
    """Tests for surface allocation algorithm."""

    def test_allocate_single_signal(self):
        """Test allocating a single signal to surfaces."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.8,
                )
            ],
        )

        surfaces, over_budget = assign_signals_to_surfaces(workspace, FOCUS_METRIC)

        assert len(surfaces) == 2  # FOCUS_METRIC has 2 surfaces
        assert len(over_budget) == 0
        # Signal should be allocated to first (highest priority) surface
        assert "kpi1" in surfaces[0].assigned_signals

    def test_allocate_multiple_signals_by_capacity(self):
        """Test that signals are allocated respecting capacity."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="heavy",
                    kind=AttentionSignalKind.KPI,
                    label="Heavy",
                    source="E",
                    attention_weight=0.9,
                ),
                LayoutSignal(
                    id="light",
                    kind=AttentionSignalKind.KPI,
                    label="Light",
                    source="E",
                    attention_weight=0.2,
                ),
            ],
        )

        surfaces, over_budget = assign_signals_to_surfaces(workspace, FOCUS_METRIC)

        assert len(over_budget) == 0
        # Both signals should fit
        total_assigned = sum(len(s.assigned_signals) for s in surfaces)
        assert total_assigned == 2

    def test_over_budget_signals(self):
        """Test that over-budget signals are tracked."""
        # Create signals that exceed total capacity
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id=f"signal{i}",
                    kind=AttentionSignalKind.KPI,
                    label=f"Signal {i}",
                    source="E",
                    attention_weight=0.8,
                )
                for i in range(5)  # 5 x 0.8 = 4.0 total
            ],
        )

        # FOCUS_METRIC has total capacity of 1.3 (hero=1.0, context=0.3)
        surfaces, over_budget = assign_signals_to_surfaces(workspace, FOCUS_METRIC)

        # Some signals won't fit
        assert len(over_budget) > 0

    def test_allocation_determinism(self):
        """Test that allocation is deterministic."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="s1",
                    kind=AttentionSignalKind.KPI,
                    label="S1",
                    source="E",
                    attention_weight=0.6,
                ),
                LayoutSignal(
                    id="s2",
                    kind=AttentionSignalKind.KPI,
                    label="S2",
                    source="E",
                    attention_weight=0.4,
                ),
            ],
        )

        # Run allocation multiple times
        results = [assign_signals_to_surfaces(workspace, FOCUS_METRIC) for _ in range(10)]

        # All results should be identical
        for i in range(1, len(results)):
            surfaces1, over1 = results[0]
            surfaces2, over2 = results[i]

            assert len(surfaces1) == len(surfaces2)
            assert over1 == over2
            for s1, s2 in zip(surfaces1, surfaces2, strict=True):
                assert s1.assigned_signals == s2.assigned_signals


class TestPersonaAdjustment:
    """Tests for persona-aware adjustments."""

    def test_adjust_signal_weights_with_bias(self):
        """Test that persona biases adjust signal weights."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.5,
                )
            ],
        )

        persona = PersonaLayout(
            id="test",
            label="Test",
            attention_biases={"kpi": 1.5},  # Boost KPIs by 50%
        )

        adjusted = adjust_attention_for_persona(workspace, persona)

        # Weight should be boosted: 0.5 * 1.5 = 0.75
        assert adjusted.attention_signals[0].attention_weight == 0.75

    def test_adjust_attention_budget_expert(self):
        """Test that expert persona increases budget."""
        workspace = WorkspaceLayout(id="test", label="Test", attention_budget=1.0)

        persona = PersonaLayout(
            id="expert",
            label="Expert",
            proficiency_level="expert",
            session_style="glance",
        )

        adjusted = adjust_attention_for_persona(workspace, persona)

        # Expert + glance → 1.0 * 1.2 * 1.1 = 1.32
        assert adjusted.attention_budget > workspace.attention_budget

    def test_adjust_attention_budget_novice(self):
        """Test that novice persona decreases budget."""
        workspace = WorkspaceLayout(id="test", label="Test", attention_budget=1.0)

        persona = PersonaLayout(id="novice", label="Novice", proficiency_level="novice")

        adjusted = adjust_attention_for_persona(workspace, persona)

        # Novice → 1.0 * 0.8 = 0.8
        assert adjusted.attention_budget < workspace.attention_budget

    def test_weight_clamping(self):
        """Test that adjusted weights are clamped to [0.0, 1.0]."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.9,
                )
            ],
        )

        persona = PersonaLayout(
            id="test",
            label="Test",
            attention_biases={"kpi": 2.0},  # Would push to 1.8
        )

        adjusted = adjust_attention_for_persona(workspace, persona)

        # Should be clamped to 1.0
        assert adjusted.attention_signals[0].attention_weight == 1.0


class TestLayoutPlanBuilder:
    """Tests for complete layout plan assembly."""

    def test_build_plan_basic(self):
        """Test building a basic layout plan."""
        workspace = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.9,
                )
            ],
        )

        plan = build_layout_plan(workspace)

        assert plan.workspace_id == "dashboard"
        assert plan.persona_id is None
        assert plan.stage == LayoutArchetype.FOCUS_METRIC
        assert len(plan.surfaces) > 0
        assert len(plan.over_budget_signals) == 0

    def test_build_plan_with_persona(self):
        """Test building plan with persona."""
        workspace = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.5,
                )
            ],
        )

        persona = PersonaLayout(
            id="power_user",
            label="Power User",
            proficiency_level="expert",
            attention_biases={"kpi": 1.5},
        )

        plan = build_layout_plan(workspace, persona)

        assert plan.persona_id == "power_user"
        # Persona should affect the plan (adjusted weights)
        assert plan.metadata["total_attention_weight"] > 0.5

    def test_build_plan_warnings_over_budget(self):
        """Test that warnings are generated for over-budget signals."""
        # Create workspace with too many heavy signals
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_budget=1.0,
            attention_signals=[
                LayoutSignal(
                    id=f"signal{i}",
                    kind=AttentionSignalKind.KPI,
                    label=f"Signal {i}",
                    source="E",
                    attention_weight=0.8,
                )
                for i in range(5)
            ],
        )

        plan = build_layout_plan(workspace)

        # Should have warnings about over-budget
        assert len(plan.warnings) > 0
        assert any("budget" in w.lower() for w in plan.warnings)

    def test_build_plan_metadata(self):
        """Test that plan metadata is populated."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_budget=1.2,
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.7,
                )
            ],
        )

        plan = build_layout_plan(workspace)

        assert "signal_count" in plan.metadata
        assert "total_attention_weight" in plan.metadata
        assert "attention_budget" in plan.metadata
        assert "stage_name" in plan.metadata

        assert plan.metadata["signal_count"] == 1
        assert plan.metadata["total_attention_weight"] == 0.7
        assert plan.metadata["attention_budget"] == 1.2

    def test_build_plan_determinism(self):
        """Test that plan building is deterministic."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_signals=[
                LayoutSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="E",
                    attention_weight=0.7,
                ),
                LayoutSignal(
                    id="kpi2",
                    kind=AttentionSignalKind.KPI,
                    label="KPI 2",
                    source="E",
                    attention_weight=0.5,
                ),
            ],
        )

        # Build plan multiple times
        plans = [build_layout_plan(workspace) for _ in range(10)]

        # All plans should be identical
        for i in range(1, len(plans)):
            assert plans[0].stage == plans[i].stage
            assert len(plans[0].surfaces) == len(plans[i].surfaces)
            assert plans[0].over_budget_signals == plans[i].over_budget_signals
            # Check surface assignments match
            for s1, s2 in zip(plans[0].surfaces, plans[i].surfaces, strict=True):
                assert s1.assigned_signals == s2.assigned_signals


class TestArchetypeDefinitions:
    """Tests for archetype definitions."""

    def test_all_archetypes_defined(self):
        """Test that all archetypes have definitions."""
        for archetype in LayoutArchetype:
            assert archetype in ARCHETYPE_DEFINITIONS

    def test_archetype_surface_capacities(self):
        """Test that archetype surfaces have valid capacities."""
        for archetype_def in ARCHETYPE_DEFINITIONS.values():
            for surface in archetype_def.surfaces:
                assert surface.capacity >= 0.0
                assert surface.priority >= 1

    def test_archetype_signal_ranges(self):
        """Test that archetypes have valid signal ranges."""
        for archetype_def in ARCHETYPE_DEFINITIONS.values():
            assert archetype_def.min_signals >= 0
            assert archetype_def.max_signals >= archetype_def.min_signals
