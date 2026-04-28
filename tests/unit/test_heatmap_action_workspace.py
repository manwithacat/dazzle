"""Tests for the v0.61.86 (#916) heatmap `action: <workspace_name>` fix.

A `display: heatmap` region with `action: <workspace_name>` should route
row clicks to that workspace (with the row's identifier as `context_id`),
not to the source-record detail drawer. The previous behaviour silently
downgraded the action because the routing code only looked at `surfaces`,
never `workspaces`.

Three layers:
  1. The workspace_renderer's action-resolution loop now checks
     `app_spec.workspaces` BEFORE `app_spec.surfaces`.
  2. When a workspace match is found, the URL pattern is
     `/app/workspaces/<name>?context_id={id}` — the heatmap template
     replaces `{id}` literally with the row identifier, so the final
     emitted URL is the workspace's app-shell URL with the row's
     identifier passed via the standard `context_id` query param.
  3. Workspace match takes precedence over surface match on collision
     (workspaces and surfaces share a namespace in DSL, so be explicit).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"

entity Pupil:
  id: uuid pk
  name: str(50)

entity MarkingResult:
  id: uuid pk
  pupil: ref Pupil
  ao: str(10)
  score: float

workspace pupil_dashboard "Pupil Dashboard":
  context_selector:
    label: "Pupil"
    entity: Pupil
  pupil_overview:
    source: Pupil
    display: detail

workspace teacher_workspace "Teacher Workspace":
  pupil_ao_heatmap:
    source: MarkingResult
    display: heatmap
    rows: pupil
    columns: ao
    action: pupil_dashboard
    aggregate:
      avg_score: avg(score)
"""


class TestActionWorkspaceRouting:
    def _heatmap_action_url(self, src: str) -> str:
        from types import SimpleNamespace

        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        module = _parse(src)
        teacher = next(ws for ws in module.workspaces if ws.name == "teacher_workspace")
        # The renderer only reads .workspaces, .surfaces, .entities off
        # the AppSpec for action-resolution + FK plumbing — a duck-typed
        # namespace is enough to exercise the workspace-name lookup
        # without dragging in AppSpec's full validation schema.
        appspec = SimpleNamespace(
            workspaces=list(module.workspaces),
            surfaces=list(module.surfaces),
            entities=list(module.entities),
            domain=SimpleNamespace(entities=list(module.entities)),
        )
        ctx = build_workspace_context(teacher, app_spec=appspec)
        # First region is the heatmap
        return ctx.regions[0].action_url

    def test_action_workspace_routes_to_workspace_url(self) -> None:
        """`action: pupil_dashboard` (a workspace name) → URL pattern is
        `/app/workspaces/pupil_dashboard?context_id={id}` (the heatmap
        template substitutes `{id}` with the row identifier later)."""
        url = self._heatmap_action_url(_BASE_DSL)
        assert url == "/app/workspaces/pupil_dashboard?context_id={id}"

    def test_no_action_falls_back_to_source_entity_detail(self) -> None:
        """When `action:` is absent, the existing default kicks in:
        link rows to the source-entity detail view."""
        src = _BASE_DSL.replace("    action: pupil_dashboard\n", "")
        url = self._heatmap_action_url(src)
        # Default: source entity (`MarkingResult`) detail URL
        assert "markingresult" in url.lower() or url.startswith("/app/")
        # Crucially, NOT the workspace URL
        assert "/app/workspaces/" not in url
