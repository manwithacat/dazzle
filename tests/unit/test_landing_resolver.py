"""#1558 (2a → L4): rhythm-based answer-first landing inference + drift.

`infer_landing_workspace` picks the persona's landing workspace from its rhythm
(first ACTIVE-phase scene naming a workspace) when `default_workspace` is unset;
`check_landing_drift` warns when a declared landing contradicts the rhythm.
"""

from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.page.converters.workspace_converter import compute_persona_default_routes
from dazzle.page.runtime.landing_resolver import (
    check_landing_drift,
    infer_landing_workspace,
)


def _persona(pid, *, default_workspace=None, default_route=None):  # type: ignore[no-untyped-def]
    return ir.PersonaSpec(
        id=pid,
        label=pid.title(),
        default_workspace=default_workspace,
        default_route=default_route,
    )


def _ws(*names):  # type: ignore[no-untyped-def]
    return [ir.WorkspaceSpec(name=n) for n in names]


def _rhythm(persona, phases):  # type: ignore[no-untyped-def]
    # phases: list of (kind, [scene_surface, ...])
    return ir.RhythmSpec(
        name=f"{persona}_rhythm",
        persona=persona,
        phases=[
            ir.PhaseSpec(
                name=f"p{i}",
                kind=kind,
                scenes=[
                    ir.SceneSpec(name=f"s{j}", surface=surf) for j, surf in enumerate(surfaces)
                ],
            )
            for i, (kind, surfaces) in enumerate(phases)
        ],
    )


# ── infer_landing_workspace ──────────────────────────────────────────────


def test_infers_first_active_scene_workspace():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue", "detail"])])
    assert infer_landing_workspace(p, [r], _ws("queue", "detail")) == "queue"


def test_kind_unset_uses_first_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["queue"]), (None, ["reports"])])
    assert infer_landing_workspace(p, [r], _ws("queue", "reports")) == "queue"


def test_explicit_active_preferred_over_earlier_unmarked_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["onboard"]), (PhaseKind.ACTIVE, ["queue"])])
    assert infer_landing_workspace(p, [r], _ws("onboard", "queue")) == "queue"


def test_skips_onboarding_gate_offboarding_phases():
    p = _persona("agent")
    r = _rhythm(
        "agent",
        [
            (PhaseKind.ONBOARDING, ["welcome"]),
            (PhaseKind.GATE, ["verify"]),
            (None, ["queue"]),
        ],
    )
    assert infer_landing_workspace(p, [r], _ws("welcome", "verify", "queue")) == "queue"


def test_only_one_time_phases_infers_nothing():
    p = _persona("agent")
    r = _rhythm(
        "agent",
        [(PhaseKind.ONBOARDING, ["welcome"]), (PhaseKind.OFFBOARDING, ["bye"])],
    )
    assert infer_landing_workspace(p, [r], _ws("welcome", "bye")) is None


def test_bare_surface_not_a_workspace_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["ticket_list"])])  # a surface, no ws
    assert infer_landing_workspace(p, [r], _ws("queue", "reports")) is None


def test_no_rhythm_for_persona_infers_nothing():
    p = _persona("agent")
    r = _rhythm("manager", [(PhaseKind.ACTIVE, ["queue"])])  # different persona
    assert infer_landing_workspace(p, [r], _ws("queue")) is None


def test_multiple_rhythms_first_declared_wins():
    p = _persona("agent")
    r1 = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    r2 = _rhythm("agent", [(PhaseKind.ACTIVE, ["reports"])])
    assert infer_landing_workspace(p, [r1, r2], _ws("queue", "reports")) == "queue"


def test_empty_active_phase_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, [])])  # no scenes
    assert infer_landing_workspace(p, [r], _ws("queue")) is None


# ── check_landing_drift ──────────────────────────────────────────────────


def test_drift_warns_when_declared_contradicts_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    msg = check_landing_drift(p, [r], _ws("queue", "reports"))
    assert msg is not None and "reports" in msg and "queue" in msg


def test_drift_silent_when_declared_matches_rhythm():
    p = _persona("agent", default_workspace="queue")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p, [r], _ws("queue")) is None


def test_drift_silent_without_declaration_or_rhythm():
    p_nodecl = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p_nodecl, [r], _ws("queue")) is None
    p_norhythm = _persona("agent", default_workspace="queue")
    assert check_landing_drift(p_norhythm, [], _ws("queue")) is None


# ── integration: compute_persona_default_routes (Task 2) ─────────────────


def test_route_map_infers_when_default_workspace_unset():
    p = _persona("agent")  # no default_workspace, no default_route
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r])
    assert "agent" in routes
    assert "queue" in routes["agent"]


def test_route_map_declaration_wins_over_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])  # contradicts
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r])
    assert "reports" in routes["agent"] and "queue" not in routes["agent"]


def test_route_map_no_rhythm_is_unchanged_fallback():
    p = _persona("agent")
    routes = compute_persona_default_routes([p], _ws("first", "second"), [])
    assert "first" in routes["agent"]
