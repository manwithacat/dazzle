"""Tests for discovery(coherence) — authenticated UX coherence checks."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

# ── Fixtures ─────────────────────────────────────────────────────────


def _make_persona(pid: str, default_workspace: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=pid, name=pid, description="", default_workspace=default_workspace)


def _make_entity(name: str, access: Any | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, title=name, fields=[], state_machine=None, access=access)


def _make_surface(
    name: str,
    entity_ref: str | None = None,
    mode: str = "list",
    access: Any | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=name,
        mode=mode,
        entity_ref=entity_ref,
        entity=entity_ref,
        sections=[],
        actions=[],
        access=access,
        ux=None,
    )


def _make_workspace(name: str, regions: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, regions=regions or [], access=None)


def _make_region(name: str, source: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, source=source)


def _make_story(story_id: str, actor: str, scope: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        story_id=story_id,
        id=story_id,
        actor=actor,
        title=story_id,
        description="",
        scope=scope or [],
        conditions=[],
    )


def _make_appspec(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="test_app",
        domain=SimpleNamespace(entities=kwargs.get("entities", [])),
        surfaces=kwargs.get("surfaces", []),
        personas=kwargs.get("personas", []),
        workspaces=kwargs.get("workspaces", []),
        processes=kwargs.get("processes", []),
        experiences=kwargs.get("experiences", []),
        stories=kwargs.get("stories", []),
    )


# ── Score Computation ────────────────────────────────────────────────


class TestScoreComputation:
    def test_perfect_score(self) -> None:
        from dazzle.mcp.server.handlers.discovery import _compute_coherence_score

        assert _compute_coherence_score(0) == 100

    def test_one_error_deducts_20(self) -> None:
        from dazzle.mcp.server.handlers.discovery import _compute_coherence_score

        assert _compute_coherence_score(20) == 80

    def test_floor_at_zero(self) -> None:
        from dazzle.mcp.server.handlers.discovery import _compute_coherence_score

        assert _compute_coherence_score(999) == 0


# ── Handler Integration ──────────────────────────────────────────────


class TestAppCoherenceHandler:
    def _run(self, appspec: SimpleNamespace, persona: str | None = None) -> dict[str, Any]:
        from dazzle.mcp.server.handlers.discovery import app_coherence_handler

        args: dict[str, Any] = {}
        if persona:
            args["persona"] = persona

        with patch(
            "dazzle.mcp.server.handlers.discovery.status.load_project_appspec",
            return_value=appspec,
        ):
            result = app_coherence_handler(project_path=SimpleNamespace(), args=args)

        return json.loads(result)

    def test_clean_app_scores_100(self) -> None:
        """All entities in workspace → perfect coherence."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
        )
        result = self._run(appspec)
        assert result["overall_score"] == 100
        assert result["persona_count"] == 1
        admin = result["personas"][0]
        assert admin["persona"] == "admin"
        assert admin["coherence_score"] == 100

    def test_missing_workspace_reduces_score(self) -> None:
        """Persona with no workspace gets workspace_binding failure."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin")],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
        )
        result = self._run(appspec)
        admin = result["personas"][0]
        assert admin["coherence_score"] < 100
        check_names = [c["check"] for c in admin["checks"]]
        assert "workspace_binding" in check_names
        ws_check = next(c for c in admin["checks"] if c["check"] == "workspace_binding")
        assert ws_check["status"] == "fail"

    def test_out_of_workspace_entities_no_penalty(self) -> None:
        """Entities outside the persona's workspace don't reduce the score.

        Over-exposure is workspace-scoped: entities outside the persona's workspace
        are handled by route-level access control and don't affect coherence score.
        """
        appspec = _make_appspec(
            entities=[_make_entity("Task"), _make_entity("AdminConfig")],
            personas=[_make_persona("customer", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[_make_story("S1", actor="customer", scope=["Task"])],
        )
        result = self._run(appspec)
        customer = result["personas"][0]
        assert customer["coherence_score"] == 100

    def test_persona_filter(self) -> None:
        """Only the requested persona is analyzed."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[
                _make_persona("admin", default_workspace="main"),
                _make_persona("viewer", default_workspace="main"),
            ],
            workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[
                _make_story("S1", actor="admin", scope=["Task"]),
                _make_story("S2", actor="viewer", scope=["Task"]),
            ],
        )
        result = self._run(appspec, persona="admin")
        assert result["persona_count"] == 1
        assert result["personas"][0]["persona"] == "admin"

    def test_standard_checks_always_present(self) -> None:
        """Standard checks are present even when passed."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
        )
        result = self._run(appspec)
        admin = result["personas"][0]
        check_names = {c["check"] for c in admin["checks"]}
        assert "workspace_binding" in check_names
        assert "nav_filtering" in check_names
        assert "surface_access" in check_names
        assert "story_coverage" in check_names

    def test_skipped_personas_reported(self) -> None:
        """Personas with no stories and no workspace are reported as skipped."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[
                _make_persona("admin", default_workspace="main"),
                _make_persona("ghost"),  # No stories, no workspace
            ],
            workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
            surfaces=[_make_surface("task_list", entity_ref="Task")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
        )
        result = self._run(appspec)
        assert "ghost" in result["skipped_personas"]

    def test_overall_score_is_average(self) -> None:
        """Overall score averages across all personas."""
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[
                # admin: has workspace → good score
                _make_persona("admin", default_workspace="admin_dash"),
                # customer: no workspace binding → score < 100
                _make_persona("customer"),
            ],
            workspaces=[
                _make_workspace(
                    "admin_dash",
                    regions=[_make_region("r1", source="Task")],
                ),
            ],
            surfaces=[
                _make_surface("task_list", entity_ref="Task"),
            ],
            stories=[
                _make_story("S1", actor="admin", scope=["Task"]),
                _make_story("S2", actor="customer", scope=["Task"]),
            ],
        )
        result = self._run(appspec)
        # Admin: workspace bound, entities covered → 100
        # Customer: no workspace → workspace_binding failure → < 100
        # Overall should be the average
        admin_score = next(p for p in result["personas"] if p["persona"] == "admin")[
            "coherence_score"
        ]
        cust_score = next(p for p in result["personas"] if p["persona"] == "customer")[
            "coherence_score"
        ]
        assert admin_score == 100
        assert cust_score < 100
        expected_avg = round((admin_score + cust_score) / 2)
        assert result["overall_score"] == expected_avg
