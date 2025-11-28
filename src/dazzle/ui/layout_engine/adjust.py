"""
Persona-aware attention adjustment.

Applies persona preferences to modify attention weights and workspace
characteristics before layout planning.
"""

from dazzle.core.ir import LayoutSignal, PersonaLayout, WorkspaceLayout


def adjust_attention_for_persona(
    workspace: WorkspaceLayout, persona: PersonaLayout
) -> WorkspaceLayout:
    """
    Adjust workspace attention signals based on persona preferences.

    Applies persona attention biases to signal weights and adjusts
    attention budget based on session style and proficiency level.

    Args:
        workspace: Original workspace
        persona: Persona with attention biases

    Returns:
        New WorkspaceLayout with adjusted signals and budget

    Examples:
        >>> from dazzle.core.ir import AttentionSignalKind
        >>> workspace = WorkspaceLayout(
        ...     id="test",
        ...     label="Test",
        ...     attention_budget=1.0,
        ...     attention_signals=[
        ...         LayoutSignal(id="kpi", kind=AttentionSignalKind.KPI,
        ...                        label="KPI", source="E", attention_weight=0.5)
        ...     ]
        ... )
        >>> persona = PersonaLayout(
        ...     id="expert",
        ...     label="Expert",
        ...     proficiency_level="expert",
        ...     session_style="glance",
        ...     attention_biases={"kpi": 1.5}
        ... )
        >>> adjusted = adjust_attention_for_persona(workspace, persona)
        >>> adjusted.attention_budget > workspace.attention_budget
        True
    """
    # Step 1: Adjust signal weights based on persona biases
    adjusted_signals = _adjust_signal_weights(workspace.attention_signals, persona)

    # Step 2: Adjust attention budget based on persona characteristics
    adjusted_budget = _adjust_attention_budget(workspace.attention_budget, persona)

    # Step 3: Create new workspace with adjustments
    return WorkspaceLayout(
        id=workspace.id,
        label=workspace.label,
        persona_targets=workspace.persona_targets,
        attention_budget=adjusted_budget,
        time_horizon=workspace.time_horizon,
        engine_hint=workspace.engine_hint,
        attention_signals=adjusted_signals,
    )


def _adjust_signal_weights(
    signals: list[LayoutSignal], persona: PersonaLayout
) -> list[LayoutSignal]:
    """
    Apply persona attention biases to signal weights.

    For each signal, multiply its weight by the bias for its kind
    (if a bias exists). Weights are clamped to [0.0, 1.0].
    """
    if not persona.attention_biases:
        return signals  # No biases to apply

    adjusted_signals = []

    for signal in signals:
        bias_key = signal.kind.value
        bias = persona.attention_biases.get(bias_key, 1.0)

        # Apply bias and clamp to valid range
        new_weight = min(1.0, max(0.0, signal.attention_weight * bias))

        # Create new signal with adjusted weight
        adjusted_signal = LayoutSignal(
            id=signal.id,
            kind=signal.kind,
            label=signal.label,
            source=signal.source,
            attention_weight=new_weight,
            urgency=signal.urgency,
            interaction_frequency=signal.interaction_frequency,
            density_preference=signal.density_preference,
            mode=signal.mode,
            constraints=signal.constraints,
        )
        adjusted_signals.append(adjusted_signal)

    return adjusted_signals


def _adjust_attention_budget(budget: float, persona: PersonaLayout) -> float:
    """
    Adjust attention budget based on persona characteristics.

    Rules:
    - Expert + glance → increase budget (can handle more density)
    - Novice → decrease budget (reduce complexity)
    - Deep work → neutral
    """
    adjusted = budget

    # Proficiency adjustments
    if persona.proficiency_level == "expert":
        adjusted *= 1.2  # Experts can handle more
    elif persona.proficiency_level == "novice":
        adjusted *= 0.8  # Novices need simpler layouts

    # Session style adjustments
    if persona.session_style == "glance":
        adjusted *= 1.1  # Glance users want quick overview
    # deep_work is neutral (1.0x)

    # Clamp to valid range [0.0, 1.5]
    return min(1.5, max(0.0, adjusted))


__all__ = ["adjust_attention_for_persona"]
