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


class TestCapturePlanAccessFiltering1536:
    """#1536 follow-on: the plan pairs personas only with workspaces they
    can access (same source of truth as the nav builder), so captures show
    real signed-in screens instead of denial pages. ``include_denied=True``
    restores the full product for auditing the denial pages themselves."""

    @staticmethod
    def _appspec():
        from types import SimpleNamespace

        from dazzle.core.ir import PersonaSpec
        from dazzle.core.ir.workspaces import (
            WorkspaceAccessLevel,
            WorkspaceAccessSpec,
            WorkspaceSpec,
        )

        admin_ws = WorkspaceSpec(
            name="admin_ws",
            title="Admin",
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA, allow_personas=["admin"]
            ),
        )
        open_ws = WorkspaceSpec(name="open_ws", title="Open")
        return SimpleNamespace(
            workspaces=[admin_ws, open_ws],
            personas=[
                PersonaSpec(id="admin", label="Admin"),
                PersonaSpec(id="viewer", label="Viewer"),
            ],
            archetypes=None,
        )

    def test_denied_combos_are_skipped_by_default(self) -> None:
        from dazzle.qa.capture import build_capture_plan

        targets = build_capture_plan(self._appspec())
        combos = {(t.persona, t.workspace) for t in targets}
        assert ("admin", "admin_ws") in combos
        assert ("admin", "open_ws") in combos
        assert ("viewer", "open_ws") in combos
        assert ("viewer", "admin_ws") not in combos

    def test_include_denied_restores_full_product(self) -> None:
        from dazzle.qa.capture import build_capture_plan

        targets = build_capture_plan(self._appspec(), include_denied=True)
        combos = {(t.persona, t.workspace) for t in targets}
        assert ("viewer", "admin_ws") in combos
        assert len(combos) == 4
