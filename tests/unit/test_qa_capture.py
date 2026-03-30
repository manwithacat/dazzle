"""Tests for dazzle.qa.capture — planning logic (no browser required)."""

from unittest.mock import MagicMock

from dazzle.qa.capture import CaptureTarget, build_capture_plan

# =============================================================================
# CaptureTarget
# =============================================================================


def test_capture_target_fields() -> None:
    """CaptureTarget has persona, workspace, and url fields."""
    target = CaptureTarget(
        persona="teacher",
        workspace="teacher_workspace",
        url="/app/workspaces/teacher_workspace",
    )
    assert target.persona == "teacher"
    assert target.workspace == "teacher_workspace"
    assert target.url == "/app/workspaces/teacher_workspace"


# =============================================================================
# build_capture_plan
# =============================================================================


def _make_appspec(workspace_names: list[str], persona_names: list[str]) -> MagicMock:
    """Build a mock AppSpec with workspaces and archetypes."""
    workspaces = []
    for name in workspace_names:
        ws = MagicMock()
        ws.name = name
        workspaces.append(ws)

    personas = []
    for name in persona_names:
        p = MagicMock()
        p.name = name
        p.id = name
        personas.append(p)

    appspec = MagicMock()
    appspec.workspaces = workspaces
    appspec.archetypes = personas
    return appspec


def test_build_capture_plan_produces_targets() -> None:
    """build_capture_plan creates one CaptureTarget per (persona, workspace) pair."""
    appspec = _make_appspec(
        workspace_names=["teacher_workspace", "admin_workspace"],
        persona_names=["teacher", "admin"],
    )
    targets = build_capture_plan(appspec)

    assert len(targets) == 4  # 2 personas × 2 workspaces

    combos = {(t.persona, t.workspace) for t in targets}
    assert ("teacher", "teacher_workspace") in combos
    assert ("teacher", "admin_workspace") in combos
    assert ("admin", "teacher_workspace") in combos
    assert ("admin", "admin_workspace") in combos

    # Each target URL follows the expected pattern
    for t in targets:
        assert t.url == f"/app/workspaces/{t.workspace}"


def test_build_capture_plan_empty_workspaces_returns_empty() -> None:
    """build_capture_plan returns [] when there are no workspaces."""
    appspec = _make_appspec(workspace_names=[], persona_names=["teacher"])
    targets = build_capture_plan(appspec)
    assert targets == []


def test_build_capture_plan_empty_personas_returns_empty() -> None:
    """build_capture_plan returns [] when there are no personas."""
    appspec = _make_appspec(workspace_names=["teacher_workspace"], persona_names=[])
    targets = build_capture_plan(appspec)
    assert targets == []


def test_build_capture_plan_persona_id_fallback() -> None:
    """build_capture_plan falls back to .id when .name is missing."""
    ws = MagicMock()
    ws.name = "my_workspace"

    persona = MagicMock(spec=[])  # no attributes — getattr returns default
    persona.id = "agent"  # only .id is set
    # Ensure .name is not present
    del persona.name

    appspec = MagicMock()
    appspec.workspaces = [ws]
    appspec.archetypes = [persona]

    targets = build_capture_plan(appspec)
    assert len(targets) == 1
    assert targets[0].persona == "agent"


def test_build_capture_plan_reads_personas_attr() -> None:
    """build_capture_plan reads .personas when .archetypes is missing (#763)."""
    ws = MagicMock()
    ws.name = "dashboard"

    persona = MagicMock()
    persona.name = "admin"
    persona.id = "admin"

    appspec = MagicMock(spec=[])
    appspec.workspaces = [ws]
    appspec.personas = [persona]
    # archetypes is NOT set — simulates real DSL AppSpec

    targets = build_capture_plan(appspec)
    assert len(targets) == 1
    assert targets[0].persona == "admin"
    assert targets[0].workspace == "dashboard"
