"""#1558 (2a → L4): infer a persona's answer-first landing workspace from its
rhythm when ``default_workspace`` is unset, and detect declared-vs-rhythm drift.

Rhythm-only, pure, no I/O. Declaration precedence lives in the caller
(``_resolve_persona_route``); this module only produces the *inferred* signal.
"""

from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind

# Phases that are NOT a persona's day-to-day landing (one-time / boundary).
_ONE_TIME_KINDS = frozenset({PhaseKind.ONBOARDING, PhaseKind.GATE, PhaseKind.OFFBOARDING})


def _select_active_phase(rhythm: ir.RhythmSpec) -> ir.PhaseSpec | None:
    """The phase whose first scene represents the persona's day-to-day landing.

    ``PhaseSpec.kind`` is an optional hint (usually unset). Prefer an explicit
    ACTIVE phase; else the first phase that is not a one-time boundary phase
    (with kind unset everywhere this is simply the first declared phase, since
    phases are in temporal order); else None.
    """
    for phase in rhythm.phases:
        if phase.kind == PhaseKind.ACTIVE:
            return phase
    for phase in rhythm.phases:
        if phase.kind not in _ONE_TIME_KINDS:  # None / ACTIVE / PERIODIC / AMBIENT
            return phase
    return None


def infer_landing_workspace(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> str | None:
    """Return the workspace name inferred from the persona's rhythm, or None.

    Does NOT consider ``persona.default_workspace`` — the caller owns
    declaration precedence. v1 acts only when the first active-phase scene's
    surface names a workspace directly.
    """
    rhythm = next((r for r in rhythms if r.persona == persona.id), None)
    if rhythm is None:
        return None
    phase = _select_active_phase(rhythm)
    if phase is None or not phase.scenes:
        return None
    surface = phase.scenes[0].surface
    workspace_names = {ws.name for ws in workspaces}
    return surface if surface in workspace_names else None


def check_landing_drift(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> str | None:
    """Return an advisory warning when a declared ``default_workspace``
    contradicts the persona's rhythm-inferred landing, else None."""
    if not persona.default_workspace:
        return None
    inferred = infer_landing_workspace(persona, rhythms, workspaces)
    if inferred is None or inferred == persona.default_workspace:
        return None
    return (
        f"persona {persona.id!r} declares default_workspace="
        f"{persona.default_workspace!r}, but its rhythm's active landing points "
        f"at {inferred!r} — the landing may not be answer-first for this persona"
    )
