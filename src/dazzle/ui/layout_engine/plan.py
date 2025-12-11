"""
Layout plan assembly.

Main orchestrator that combines stage selection, surface allocation,
and persona adjustments to produce complete layout plans.
"""

from typing import Any

from dazzle.core.ir import LayoutPlan, PersonaLayout, Stage, WorkspaceLayout
from dazzle.ui.layout_engine.adjust import adjust_attention_for_persona
from dazzle.ui.layout_engine.allocate import assign_signals_to_surfaces
from dazzle.ui.layout_engine.archetypes import ArchetypeDefinition, get_archetype_definition
from dazzle.ui.layout_engine.select_archetype import select_stage


def build_layout_plan(
    workspace: WorkspaceLayout, persona: PersonaLayout | None = None
) -> LayoutPlan:
    """
    Build complete layout plan from workspace and optional persona.

    This is the main entry point for the layout engine. It orchestrates:
    1. Persona-aware adjustments (if persona provided)
    2. Stage selection
    3. Surface allocation
    4. Warning generation (over-budget, etc.)

    Args:
        workspace: Workspace with attention signals
        persona: Optional persona for personalization

    Returns:
        Complete LayoutPlan ready for rendering

    Examples:
        >>> from dazzle.core.ir import LayoutSignal, AttentionSignalKind
        >>> workspace = WorkspaceLayout(
        ...     id="dashboard",
        ...     label="Dashboard",
        ...     attention_signals=[
        ...         LayoutSignal(id="kpi", kind=AttentionSignalKind.KPI,
        ...                        label="KPI", source="E", attention_weight=0.9)
        ...     ]
        ... )
        >>> plan = build_layout_plan(workspace)
        >>> plan.stage.value
        'focus_metric'
        >>> len(plan.surfaces) > 0
        True
    """
    # Step 1: Apply persona adjustments if provided
    if persona:
        adjusted_workspace = adjust_attention_for_persona(workspace, persona)
    else:
        adjusted_workspace = workspace

    # Step 2: Select stage
    stage = select_stage(adjusted_workspace, persona)
    archetype_def = get_archetype_definition(stage)

    # Step 3: Allocate signals to surfaces
    surfaces, over_budget_signals = assign_signals_to_surfaces(adjusted_workspace, archetype_def)

    # Step 4: Generate warnings
    warnings = _generate_warnings(
        workspace=adjusted_workspace,
        archetype_def=archetype_def,
        over_budget_signals=over_budget_signals,
    )

    # Step 5: Build metadata
    metadata = _build_metadata(
        workspace=adjusted_workspace,
        stage=stage,
        archetype_def=archetype_def,
    )

    # Step 6: Assemble final plan
    return LayoutPlan(
        workspace_id=workspace.id,
        persona_id=persona.id if persona else None,
        stage=stage,
        surfaces=surfaces,
        over_budget_signals=over_budget_signals,
        warnings=warnings,
        metadata=metadata,
    )


def _generate_warnings(
    workspace: WorkspaceLayout,
    archetype_def: ArchetypeDefinition,
    over_budget_signals: list[str],
) -> list[str]:
    """
    Generate warnings about layout issues.

    Warnings include:
    - Attention budget exceeded
    - Over-budget signals
    - Signal count outside archetype recommendations
    """
    warnings = []

    # Warning 1: Over-budget signals
    if over_budget_signals:
        count = len(over_budget_signals)
        warnings.append(
            f"{count} signal(s) exceeded capacity and were not allocated: "
            f"{', '.join(over_budget_signals[:3])}" + ("..." if count > 3 else "")
        )

    # Warning 2: Total attention weight vs budget
    total_weight = sum(s.attention_weight for s in workspace.attention_signals)
    if total_weight > workspace.attention_budget:
        excess = total_weight - workspace.attention_budget
        warnings.append(
            f"Total attention weight ({total_weight:.2f}) exceeds budget "
            f"({workspace.attention_budget:.2f}) by {excess:.2f}"
        )

    # Warning 3: Signal count outside recommendations
    signal_count = len(workspace.attention_signals)
    if signal_count < archetype_def.min_signals:
        warnings.append(
            f"Signal count ({signal_count}) below minimum recommended "
            f"for {archetype_def.name} ({archetype_def.min_signals})"
        )
    elif signal_count > archetype_def.max_signals:
        warnings.append(
            f"Signal count ({signal_count}) exceeds maximum recommended "
            f"for {archetype_def.name} ({archetype_def.max_signals})"
        )

    return warnings


def _build_metadata(
    workspace: WorkspaceLayout, stage: Stage, archetype_def: ArchetypeDefinition
) -> dict[str, Any]:
    """Build metadata for debugging and logging."""
    return {
        "signal_count": len(workspace.attention_signals),
        "total_attention_weight": sum(s.attention_weight for s in workspace.attention_signals),
        "attention_budget": workspace.attention_budget,
        "stage_name": archetype_def.name,
        "surface_count": len(archetype_def.surfaces),
        "time_horizon": workspace.time_horizon,
    }


__all__ = ["build_layout_plan"]
