"""
Archetype selection logic.

Deterministic rules for selecting the optimal layout archetype based on
workspace characteristics and persona preferences.
"""

from dazzle.core.ir import (
    AttentionSignalKind,
    LayoutArchetype,
    LayoutSignal,
    PersonaLayout,
    WorkspaceLayout,
)


def select_archetype(
    workspace: WorkspaceLayout, persona: PersonaLayout | None = None
) -> LayoutArchetype:
    """
    Select layout archetype based on workspace characteristics.

    This function implements deterministic selection rules:
    1. Check engine_hint if provided
    2. Analyze signal profile (kinds, weights, count)
    3. Apply persona biases if available
    4. Return most appropriate archetype

    Args:
        workspace: Workspace with attention signals
        persona: Optional persona for bias adjustment

    Returns:
        Selected archetype enum value

    Examples:
        >>> workspace = WorkspaceLayout(
        ...     id="dashboard",
        ...     label="Dashboard",
        ...     attention_signals=[
        ...         LayoutSignal(id="kpi1", kind=AttentionSignalKind.KPI,
        ...                        label="KPI", source="Entity",
        ...                        attention_weight=0.9)
        ...     ]
        ... )
        >>> select_archetype(workspace)
        <LayoutArchetype.FOCUS_METRIC: 'focus_metric'>
    """
    # Rule 1: Respect explicit engine hint
    if workspace.engine_hint:
        hint_lower = workspace.engine_hint.lower()
        for archetype in LayoutArchetype:
            if archetype.value == hint_lower:
                return archetype

    signals = workspace.attention_signals
    signal_count = len(signals)

    # Rule 2: Empty or single signal defaults
    if signal_count == 0:
        return LayoutArchetype.FOCUS_METRIC  # Empty state

    if signal_count == 1:
        signal = signals[0]
        if signal.kind == AttentionSignalKind.TABLE:
            return LayoutArchetype.SCANNER_TABLE
        else:
            return LayoutArchetype.FOCUS_METRIC

    # Rule 3: Analyze signal profile
    signal_profile = _analyze_signal_profile(signals, persona)

    # Rule 4: Apply selection rules based on profile
    return _select_from_profile(signal_profile, signal_count, persona)


def _analyze_signal_profile(
    signals: list[LayoutSignal], persona: PersonaLayout | None
) -> dict[str, float]:
    """
    Analyze signal characteristics to build selection profile.

    Returns dict with:
    - dominant_kpi: weight of strongest KPI signal
    - table_weight: total weight of table signals
    - list_weight: total weight of list signals
    - detail_weight: total weight of detail signals
    - diversity: number of unique signal kinds
    """
    profile = {
        "dominant_kpi": 0.0,
        "table_weight": 0.0,
        "list_weight": 0.0,
        "detail_weight": 0.0,
        "diversity": 0,
    }

    kind_counts: dict[AttentionSignalKind, int] = {}
    kpi_weights: list[float] = []

    for signal in signals:
        kind = signal.kind
        weight = signal.attention_weight

        # Apply persona bias if available
        if persona and persona.attention_biases:
            bias_key = kind.value
            if bias_key in persona.attention_biases:
                weight *= persona.attention_biases[bias_key]

        # Track by kind
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

        if kind == AttentionSignalKind.KPI:
            kpi_weights.append(weight)
        elif kind == AttentionSignalKind.TABLE:
            profile["table_weight"] += weight
        elif kind in (AttentionSignalKind.ITEM_LIST, AttentionSignalKind.TASK_LIST):
            profile["list_weight"] += weight
        elif kind == AttentionSignalKind.DETAIL_VIEW:
            profile["detail_weight"] += weight

    profile["dominant_kpi"] = max(kpi_weights) if kpi_weights else 0.0
    profile["diversity"] = len(kind_counts)

    return profile


def _select_from_profile(
    profile: dict[str, float], signal_count: int, persona: PersonaLayout | None
) -> LayoutArchetype:
    """
    Select archetype based on analyzed profile.

    Selection rules (in priority order):
    1. Dominant KPI (>0.7) → FOCUS_METRIC
    2. Strong table weight (>0.6) → SCANNER_TABLE
    3. List + detail → DUAL_PANE_FLOW
    4. High diversity + many signals (5+) → COMMAND_CENTER (for experts)
    5. Multiple moderate signals (3-8) → MONITOR_WALL
    6. Default: MONITOR_WALL
    """
    # Rule 1: Dominant KPI
    if profile["dominant_kpi"] > 0.7:
        return LayoutArchetype.FOCUS_METRIC

    # Rule 2: Strong table presence
    if profile["table_weight"] > 0.6:
        return LayoutArchetype.SCANNER_TABLE

    # Rule 3: List + detail combination
    if profile["list_weight"] > 0.3 and profile["detail_weight"] > 0.3:
        return LayoutArchetype.DUAL_PANE_FLOW

    # Rule 4: Command center for experts with many signals
    if signal_count >= 5:
        if persona and persona.proficiency_level == "expert":
            if profile["diversity"] >= 3:  # Reduced from 4 for 6 KPI signals
                return LayoutArchetype.COMMAND_CENTER
        # Non-experts get monitor wall

    # Rule 5: Monitor wall for multiple moderate signals
    if 3 <= signal_count <= 8:
        return LayoutArchetype.MONITOR_WALL

    # Rule 6: Command center for many signals
    if signal_count > 8:
        if persona and persona.proficiency_level == "expert":
            return LayoutArchetype.COMMAND_CENTER
        else:
            return LayoutArchetype.MONITOR_WALL  # Simplify for non-experts

    # Default
    return LayoutArchetype.MONITOR_WALL


__all__ = ["select_archetype"]
