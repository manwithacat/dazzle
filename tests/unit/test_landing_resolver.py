"""#1558 (2a → L4): rhythm-based answer-first landing inference + drift.

`infer_landing_route` picks the persona's landing ROUTE from its rhythm (first
active-phase scene naming a workspace → its root route, or a list-mode surface →
its list route) when `default_workspace` is unset; `check_landing_drift` warns
when a declared landing contradicts the rhythm.
"""

from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.page import app_paths
from dazzle.page.converters.workspace_converter import compute_persona_default_routes
from dazzle.page.runtime.landing_resolver import (
    check_landing_drift,
    infer_landing_route,
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


def _surface(name, entity, mode=SurfaceMode.LIST):  # type: ignore[no-untyped-def]
    return ir.SurfaceSpec(name=name, mode=mode, entity_ref=entity)


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


def _ws_route(name):  # type: ignore[no-untyped-def]
    return f"/app/workspaces/{name}"


# ── infer_landing_route: workspace targets ───────────────────────────────


def test_infers_first_active_scene_workspace():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue", "detail"])])
    assert infer_landing_route(p, [r], _ws("queue", "detail"), []) == _ws_route("queue")


def test_kind_unset_uses_first_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["queue"]), (None, ["reports"])])
    assert infer_landing_route(p, [r], _ws("queue", "reports"), []) == _ws_route("queue")


def test_explicit_active_preferred_over_earlier_unmarked_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["onboard"]), (PhaseKind.ACTIVE, ["queue"])])
    assert infer_landing_route(p, [r], _ws("onboard", "queue"), []) == _ws_route("queue")


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
    assert infer_landing_route(p, [r], _ws("welcome", "verify", "queue"), []) == _ws_route("queue")


def test_only_one_time_phases_infers_nothing():
    p = _persona("agent")
    r = _rhythm(
        "agent",
        [(PhaseKind.ONBOARDING, ["welcome"]), (PhaseKind.OFFBOARDING, ["bye"])],
    )
    assert infer_landing_route(p, [r], _ws("welcome", "bye"), []) is None


# ── infer_landing_route: list-surface targets ────────────────────────────


def test_infers_list_surface_route_via_entity_slug():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["ticket_list"])])
    surfaces = [_surface("ticket_list", "Ticket")]
    expected = app_paths.list_path("/app", app_paths.entity_slug("Ticket"))
    assert infer_landing_route(p, [r], _ws("queue"), surfaces) == expected


def test_non_list_surface_does_not_resolve():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["ticket_detail"])])
    surfaces = [_surface("ticket_detail", "Ticket", mode=SurfaceMode.VIEW)]
    assert infer_landing_route(p, [r], _ws("queue"), surfaces) is None


def test_unknown_target_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["nowhere"])])
    assert infer_landing_route(p, [r], _ws("queue"), [_surface("ticket_list", "Ticket")]) is None


def test_no_rhythm_for_persona_infers_nothing():
    p = _persona("agent")
    r = _rhythm("manager", [(PhaseKind.ACTIVE, ["queue"])])  # different persona
    assert infer_landing_route(p, [r], _ws("queue"), []) is None


def test_multiple_rhythms_first_declared_wins():
    p = _persona("agent")
    r1 = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    r2 = _rhythm("agent", [(PhaseKind.ACTIVE, ["reports"])])
    assert infer_landing_route(p, [r1, r2], _ws("queue", "reports"), []) == _ws_route("queue")


def test_empty_active_phase_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, [])])  # no scenes
    assert infer_landing_route(p, [r], _ws("queue"), []) is None


# ── check_landing_drift ──────────────────────────────────────────────────


def test_drift_warns_when_declared_contradicts_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    msg = check_landing_drift(p, [r], _ws("queue", "reports"), [])
    assert msg is not None and "reports" in msg and "queue" in msg


def test_drift_silent_when_declared_matches_rhythm():
    p = _persona("agent", default_workspace="queue")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p, [r], _ws("queue"), []) is None


def test_drift_silent_without_declaration_or_rhythm():
    p_nodecl = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p_nodecl, [r], _ws("queue"), []) is None
    p_norhythm = _persona("agent", default_workspace="queue")
    assert check_landing_drift(p_norhythm, [], _ws("queue"), []) is None


# ── integration: compute_persona_default_routes (Task 2) ─────────────────


def test_route_map_infers_when_default_workspace_unset():
    p = _persona("agent")  # no default_workspace, no default_route
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r], [])
    assert routes.get("agent") == _ws_route("queue")


def test_route_map_infers_list_surface_landing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["ticket_list"])])
    surfaces = [_surface("ticket_list", "Ticket")]
    routes = compute_persona_default_routes([p], _ws("queue"), [r], surfaces)
    assert routes.get("agent") == app_paths.list_path("/app", app_paths.entity_slug("Ticket"))


def test_route_map_declaration_wins_over_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])  # contradicts
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r], [])
    assert "reports" in routes["agent"] and "queue" not in routes["agent"]


def test_route_map_no_rhythm_is_unchanged_fallback():
    p = _persona("agent")
    routes = compute_persona_default_routes([p], _ws("first", "second"), [], [])
    assert "first" in routes["agent"]
