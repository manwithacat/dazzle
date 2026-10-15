"""Tests for discovery(coherence) — authenticated UX coherence checks."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

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
    return SimpleNamespace(name=name, regions=regions or [], access=None, nav_groups=[])


def _make_region(name: str, source: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, source=source)


def _make_story(story_id: str, actor: str, scope: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        story_id=story_id,
        id=story_id,
        persona=actor,
        title=story_id,
        description="",
        entities=scope or [],
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


# Score = 100 - deductions, clamped to 0..100.
@pytest.mark.parametrize(
    ("deductions", "score"),
    [
        pytest.param(0, 100, id="no-deductions-perfect"),
        pytest.param(20, 80, id="one-error-deducts-20"),
        pytest.param(999, 0, id="floor-at-zero"),
    ],
)
def test_coherence_score(deductions: int, score: int) -> None:
    from dazzle.mcp.server.handlers.discovery import _compute_coherence_score

    assert _compute_coherence_score(deductions) == score


# ── Handler Integration ──────────────────────────────────────────────


def _clean_appspec(*personas: SimpleNamespace, stories: list[Any] | None = None) -> SimpleNamespace:
    """One Task entity, a ``main`` workspace sourcing it, and a Task list surface."""
    return _make_appspec(
        entities=[_make_entity("Task"), _make_entity("AdminConfig")],
        personas=list(personas),
        workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
        surfaces=[_make_surface("task_list", entity_ref="Task")],
        stories=stories if stories is not None else [_make_story("S1", "admin", ["Task"])],
    )


def _run(appspec: SimpleNamespace, persona: str | None = None) -> dict[str, Any]:
    from dazzle.mcp.server.handlers.discovery import app_coherence_handler

    args: dict[str, Any] = {"persona": persona} if persona else {}
    with patch(
        "dazzle.mcp.server.handlers.discovery.status.load_project_appspec",
        return_value=appspec,
    ):
        result = app_coherence_handler(project_path=SimpleNamespace(), args=args)
    return json.loads(result)


def test_clean_app_scores_100_with_all_standard_checks() -> None:
    """All entities in the workspace → perfect coherence; the four standard checks are
    reported even when they pass. ``AdminConfig`` sits outside the workspace and does
    not reduce the score (over-exposure is route-level, not coherence)."""
    result = _run(_clean_appspec(_make_persona("admin", default_workspace="main")))
    assert result["overall_score"] == 100
    assert result["persona_count"] == 1
    admin = result["personas"][0]
    assert admin["persona"] == "admin"
    assert admin["coherence_score"] == 100
    assert {c["check"] for c in admin["checks"]} >= {
        "workspace_binding",
        "nav_filtering",
        "surface_access",
        "story_coverage",
    }


def test_missing_workspace_fails_binding_and_overall_is_average() -> None:
    """A persona with no workspace fails ``workspace_binding``; the overall score is the
    rounded average of persona scores."""
    appspec = _clean_appspec(
        _make_persona("admin", default_workspace="main"),
        _make_persona("customer"),
        stories=[_make_story("S1", "admin", ["Task"]), _make_story("S2", "customer", ["Task"])],
    )
    result = _run(appspec)
    by_persona = {p["persona"]: p for p in result["personas"]}
    customer = by_persona["customer"]
    ws_check = next(c for c in customer["checks"] if c["check"] == "workspace_binding")
    assert ws_check["status"] == "fail"
    assert by_persona["admin"]["coherence_score"] == 100
    assert customer["coherence_score"] == 80  # one error = -20
    assert result["overall_score"] == 90


def test_persona_filter_and_skipped_personas() -> None:
    """``persona`` narrows the analysis; personas with no stories and no workspace are
    reported as skipped rather than scored."""
    appspec = _clean_appspec(
        _make_persona("admin", default_workspace="main"),
        _make_persona("viewer", default_workspace="main"),
        _make_persona("ghost"),
        stories=[_make_story("S1", "admin", ["Task"]), _make_story("S2", "viewer", ["Task"])],
    )
    assert "ghost" in _run(appspec)["skipped_personas"]
    filtered = _run(appspec, persona="admin")
    assert filtered["persona_count"] == 1
    assert filtered["personas"][0]["persona"] == "admin"
