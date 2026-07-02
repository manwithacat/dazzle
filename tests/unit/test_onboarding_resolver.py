"""Tests for the active-step resolver (v0.71.2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.core import ir
from dazzle.render.onboarding.resolver import (
    _audience_matches_persona,
    _select_next_step,
    _step_target_matches_surface,
    resolve_active_step,
)
from dazzle.render.onboarding.state import OnboardingProgress

# ---------------------------------------------------------------------------
# Persona matcher
# ---------------------------------------------------------------------------


# One contract: does the audience predicate's persona clause admit the
# user's persona? (audience, user_persona) → matches.
@pytest.mark.parametrize(
    ("audience", "user_persona", "matches"),
    [
        pytest.param("persona = admin", "admin", True, id="persona-clause-includes-user"),
        pytest.param(
            "persona = admin or persona = member",
            "member",
            True,
            id="or-clauses-match-any",
        ),
        pytest.param("persona = admin", "member", False, id="user-persona-not-listed"),
        # A predicate that uses entity-state aggregates but no persona clause
        # should match — the persona compiler is the resolver's business, not
        # v0.71.2's. False positives here are caught at the next layer.
        pytest.param(
            "entity.Task.count = 0",
            "admin",
            True,
            id="no-persona-clause-matches-conservatively",
        ),
        pytest.param("", "admin", True, id="empty-string-matches"),
    ],
)
def test_audience_matches_persona(audience: str, user_persona: str, matches: bool) -> None:
    assert _audience_matches_persona(audience, user_persona) is matches


# ---------------------------------------------------------------------------
# Target → surface matcher
# ---------------------------------------------------------------------------


# One contract: does a step target (surface.<name>[.action|.field...])
# belong to the surface being rendered? (target, surface_name) → matches.
@pytest.mark.parametrize(
    ("target", "surface_name", "matches"),
    [
        pytest.param("surface.task_list", "task_list", True, id="whole-surface"),
        pytest.param(
            "surface.task_list.action.create",
            "task_list",
            True,
            id="action-matches-parent-surface",
        ),
        pytest.param(
            "surface.task_create.field.title",
            "task_create",
            True,
            id="field-matches-parent-surface",
        ),
        pytest.param("surface.task_list", "task_create", False, id="surface-name-mismatch"),
        pytest.param("entity.Task", "task_list", False, id="non-surface-prefix-rejected"),
    ],
)
def test_step_target_matches_surface(target: str, surface_name: str, matches: bool) -> None:
    assert _step_target_matches_surface(target, surface_name) is matches


# ---------------------------------------------------------------------------
# Next-step picker
# ---------------------------------------------------------------------------


def _step(name: str) -> ir.GuideStep:
    return ir.GuideStep(
        name=name,
        kind=ir.GuideStepKind.POPOVER,
        title=name,
        body="b",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )


def _guide(steps: list[ir.GuideStep], audience: str = "persona = admin") -> ir.GuideSpec:
    return ir.GuideSpec(
        name="g",
        title="g",
        audience=audience,
        steps=steps,
        step_order=[s.name for s in steps],
    )


# One contract: the picker walks step_order and returns the first step
# that is neither completed nor dismissed — None once all are resolved.
# ``completed=None`` means "no progress row at all" (progress is None).
@pytest.mark.parametrize(
    ("n_steps", "completed", "dismissed", "expected"),
    [
        pytest.param(3, None, None, "s1", id="first-when-no-progress"),
        pytest.param(3, ["s1"], [], "s2", id="skips-completed"),
        pytest.param(3, [], ["s1", "s2"], "s3", id="skips-dismissed"),
        pytest.param(2, ["s1"], ["s2"], None, id="none-when-all-resolved"),
    ],
)
def test_select_next_step(
    n_steps: int,
    completed: list[str] | None,
    dismissed: list[str] | None,
    expected: str | None,
) -> None:
    guide = _guide([_step(f"s{i}") for i in range(1, n_steps + 1)])
    progress = (
        None
        if completed is None
        else OnboardingProgress(
            id="r",
            user_id="u",
            guide_name="g",
            guide_version=1,
            current_step=None,
            completed_steps=completed,
            dismissed_steps=dismissed or [],
        )
    )
    result = _select_next_step(guide, progress)
    assert (result.name if result is not None else None) == expected


# ---------------------------------------------------------------------------
# Top-level resolver
# ---------------------------------------------------------------------------


def _app(guides: list[ir.GuideSpec]) -> ir.AppSpec:
    """Build a minimal AppSpec shape with just guides populated. Other
    required fields get empty defaults via SimpleNamespace stand-ins
    since the resolver only reads ``app.guides``."""
    return SimpleNamespace(guides=guides)  # type: ignore[return-value]


def test_resolver_returns_step_when_guide_matches_user_and_surface() -> None:
    guide = _guide([_step("s1")])
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    result = resolve_active_step(
        user_id="u1",
        user_persona="admin",
        surface_name="task_list",
        app=_app([guide]),
        repo=repo,
    )
    assert result is not None
    g, s = result
    assert g.name == "g"
    assert s.name == "s1"


def test_resolver_returns_none_when_audience_mismatch() -> None:
    guide = _guide([_step("s1")], audience="persona = admin")
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    result = resolve_active_step(
        user_id="u1",
        user_persona="member",  # not admin
        surface_name="task_list",
        app=_app([guide]),
        repo=repo,
    )
    assert result is None


def test_resolver_returns_none_when_target_surface_mismatch() -> None:
    guide = _guide([_step("s1")])
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    result = resolve_active_step(
        user_id="u1",
        user_persona="admin",
        surface_name="other_surface",  # step targets task_list
        app=_app([guide]),
        repo=repo,
    )
    assert result is None


def test_resolver_skips_completed_guide() -> None:
    guide = _guide([_step("s1")])
    repo = MagicMock()
    repo.get = MagicMock(
        return_value=OnboardingProgress(
            id="r",
            user_id="u1",
            guide_name="g",
            guide_version=1,
            current_step=None,
            completed_at=__import__("datetime").datetime.now(),
        )
    )
    result = resolve_active_step(
        user_id="u1",
        user_persona="admin",
        surface_name="task_list",
        app=_app([guide]),
        repo=repo,
    )
    assert result is None


def test_resolver_walks_guides_in_declaration_order() -> None:
    """First matching guide wins — author intent controls priority."""
    g1 = ir.GuideSpec(
        name="first",
        title="first",
        audience="persona = admin",
        steps=[_step("a")],
        step_order=["a"],
    )
    g2 = ir.GuideSpec(
        name="second",
        title="second",
        audience="persona = admin",
        steps=[_step("b")],
        step_order=["b"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    result = resolve_active_step(
        user_id="u1",
        user_persona="admin",
        surface_name="task_list",
        app=_app([g1, g2]),
        repo=repo,
    )
    assert result is not None
    assert result[0].name == "first"
