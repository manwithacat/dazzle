"""
DSL to Layout IR converter.

Converts parsed DSL constructs (WorkspaceSpec, etc.) into layout engine IR (WorkspaceLayout).
"""

from ...core.ir import (
    AppSpec,
    AttentionSignal,
    AttentionSignalKind,
    PersonaLayout,
    UXLayouts,
    WorkspaceLayout,
    WorkspaceSpec,
)


def convert_workspaces_to_layouts(app_spec: AppSpec) -> list[WorkspaceLayout]:
    """
    Convert WorkspaceSpec objects to WorkspaceLayout objects.

    Extracts attention signals from workspace regions and creates
    layout-ready workspace definitions.

    Args:
        app_spec: Application specification with workspaces

    Returns:
        List of WorkspaceLayout objects ready for layout planning
    """
    workspace_layouts = []

    for workspace in app_spec.workspaces:
        layout = convert_workspace_to_layout(workspace)
        workspace_layouts.append(layout)

    return workspace_layouts


def convert_workspace_to_layout(workspace: WorkspaceSpec) -> WorkspaceLayout:
    """
    Convert single WorkspaceSpec to WorkspaceLayout.

    Args:
        workspace: Parsed workspace from DSL

    Returns:
        WorkspaceLayout ready for layout engine
    """
    # Extract attention signals from regions
    attention_signals = _extract_attention_signals_from_regions(workspace)

    # Extract layout hints from UX spec if present
    attention_budget = 1.0
    engine_hint = None

    if workspace.ux:
        # Check for attention signals in UX spec
        if workspace.ux.attention_signals:
            attention_signals.extend(workspace.ux.attention_signals)

    return WorkspaceLayout(
        id=workspace.name,
        label=workspace.title or workspace.name,
        persona_targets=[],  # TODO: Extract from UX persona variants
        attention_budget=attention_budget,
        time_horizon="daily",  # Default, could infer from purpose
        engine_hint=engine_hint,
        attention_signals=attention_signals,
    )


def _extract_attention_signals_from_regions(
    workspace: WorkspaceSpec,
) -> list[AttentionSignal]:
    """
    Extract attention signals from workspace regions.

    Maps regions to attention signal kinds based on their characteristics.

    Args:
        workspace: Workspace with regions

    Returns:
        List of attention signals
    """
    signals = []

    for region in workspace.regions:
        # Determine signal kind based on region type
        signal_kind = _infer_signal_kind_from_region(region)

        # Determine attention weight (higher for filtered/limited views)
        attention_weight = _calculate_attention_weight(region)

        signal = AttentionSignal(
            id=region.name,
            kind=signal_kind,
            label=region.name,  # WorkspaceRegion doesn't have title field
            source=region.source if hasattr(region, "source") else "unknown",
            attention_weight=attention_weight,
        )

        signals.append(signal)

    return signals


def _infer_signal_kind_from_region(region) -> AttentionSignalKind:
    """
    Infer attention signal kind from region characteristics.

    Args:
        region: WorkspaceRegion

    Returns:
        AttentionSignalKind
    """
    # Check if region has aggregates (likely a KPI)
    if hasattr(region, "aggregates") and region.aggregates:
        return AttentionSignalKind.KPI

    # Check if region has filters and limits (likely a curated list)
    if hasattr(region, "filter") and region.filter is not None:
        if hasattr(region, "limit") and region.limit is not None and region.limit > 0:
            return AttentionSignalKind.ITEM_LIST
        return AttentionSignalKind.TABLE

    # Check if limited without filter (top N items)
    if hasattr(region, "limit") and region.limit is not None and region.limit > 0:
        return AttentionSignalKind.ITEM_LIST

    # Check region display mode for specialized views
    if hasattr(region, "display"):
        display_str = str(region.display).lower()
        # Only treat timeline/map as special - list/grid are just presentation
        if "timeline" in display_str or "map" in display_str:
            return AttentionSignalKind.CHART

    # Default to table view for browsing all data
    # (even if display mode is "list" - that's just visual styling)
    return AttentionSignalKind.TABLE


def _calculate_attention_weight(region) -> float:
    """
    Calculate attention weight for a region.

    Higher weights for:
    - Filtered views (user cares about subset)
    - Limited views (top N items)
    - Urgent/critical data

    Args:
        region: WorkspaceRegion

    Returns:
        Attention weight between 0.0 and 1.0
    """
    weight = 0.5  # Base weight

    # Boost for filtered views
    if hasattr(region, "filter") and region.filter is not None:
        weight += 0.2

    # Boost for limited views
    if hasattr(region, "limit") and region.limit is not None and region.limit > 0:
        weight += 0.1

    # Boost for aggregates (KPIs are important)
    if hasattr(region, "aggregates") and region.aggregates:
        weight += 0.2

    # Clamp to valid range
    return min(1.0, max(0.0, weight))


def enrich_app_spec_with_layouts(app_spec: AppSpec) -> AppSpec:
    """
    Enrich AppSpec with layout information.

    Converts WorkspaceSpec objects to WorkspaceLayout and adds them
    to the AppSpec's ux field.

    Args:
        app_spec: Application specification

    Returns:
        New AppSpec with ux.workspaces populated
    """
    # Convert workspaces to layouts
    workspace_layouts = convert_workspaces_to_layouts(app_spec)

    # Create or update UXLayouts
    if app_spec.ux:
        # Merge with existing
        ux_layouts = UXLayouts(
            workspaces=workspace_layouts,
            personas=app_spec.ux.personas,
        )
    else:
        # Create new
        ux_layouts = UXLayouts(
            workspaces=workspace_layouts,
            personas=[],
        )

    # Create new AppSpec with ux field populated
    return AppSpec(
        name=app_spec.name,
        title=app_spec.title,
        version=app_spec.version,
        domain=app_spec.domain,
        surfaces=app_spec.surfaces,
        workspaces=app_spec.workspaces,
        experiences=app_spec.experiences,
        services=app_spec.services,
        foreign_models=app_spec.foreign_models,
        integrations=app_spec.integrations,
        tests=app_spec.tests,
        metadata=app_spec.metadata,
        ux=ux_layouts,
    )


__all__ = [
    "convert_workspaces_to_layouts",
    "convert_workspace_to_layout",
    "enrich_app_spec_with_layouts",
]
