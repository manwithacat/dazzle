"""#1558 (2a → L4): infer a persona's answer-first landing route from its rhythm
when ``default_workspace`` is unset, and detect declared-vs-rhythm drift.

Rhythm-only, pure, no I/O. Declaration precedence lives in the callers
(``_resolve_persona_route`` / ``resolve_persona_workspace_route``); this module
only produces the *inferred* signal.

The first active-phase scene's target may name a **workspace** (→ its root route)
or a **list-mode surface** (→ that surface's list route, keyed by the surface's
entity via the ``app_paths`` SSOT so the route matches registration — never a
dead link). Anything else (detail/create/edit surface, dangling name) → no
inference.
"""

from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.page import app_paths

# The workspace root-route form (mirrors workspace_converter._workspace_root_route;
# inlined to avoid a page.runtime -> page.converters import inversion).
_APP_PREFIX = "/app"

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


def _target_route(
    target: str,
    workspaces: list[ir.WorkspaceSpec],
    surfaces: list[ir.SurfaceSpec],
) -> str | None:
    """Resolve a rhythm scene's surface/workspace name to a landing route."""
    for ws in workspaces:
        if ws.name == target:
            return f"{_APP_PREFIX}/workspaces/{ws.name}"
    for sf in surfaces:
        if sf.name == target and sf.mode == SurfaceMode.LIST and sf.entity_ref:
            # Same SSOT the list route registers with (app_paths #1426) — the
            # slug is the surface's ENTITY, so this can never be a dead link.
            return app_paths.list_path(_APP_PREFIX, app_paths.entity_slug(sf.entity_ref))
    return None


def infer_landing_route(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
    surfaces: list[ir.SurfaceSpec],
) -> str | None:
    """Return the landing route inferred from the persona's rhythm, or None.

    Does NOT consider ``persona.default_workspace`` — the caller owns
    declaration precedence.
    """
    rhythm = next((r for r in rhythms if r.persona == persona.id), None)
    if rhythm is None:
        return None
    phase = _select_active_phase(rhythm)
    if phase is None or not phase.scenes:
        return None
    return _target_route(phase.scenes[0].surface, workspaces, surfaces)


def check_landing_drift(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
    surfaces: list[ir.SurfaceSpec],
) -> str | None:
    """Return an advisory warning when a declared ``default_workspace``
    contradicts the persona's rhythm-inferred landing, else None."""
    if not persona.default_workspace:
        return None
    inferred = infer_landing_route(persona, rhythms, workspaces, surfaces)
    if inferred is None:
        return None
    declared_route = f"{_APP_PREFIX}/workspaces/{persona.default_workspace}"
    if inferred == declared_route:
        return None
    return (
        f"persona {persona.id!r} declares default_workspace="
        f"{persona.default_workspace!r} (→ {declared_route}), but its rhythm's "
        f"active landing resolves to {inferred!r} — the landing may not be "
        f"answer-first for this persona"
    )
