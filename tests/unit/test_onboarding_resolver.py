"""Tests for the active-step resolver (v0.71.2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_audience_matches_when_persona_clause_includes_user() -> None:
    assert _audience_matches_persona("persona = admin", "admin") is True


def test_audience_with_or_clauses_matches_any() -> None:
    assert _audience_matches_persona("persona = admin or persona = member", "member") is True


def test_audience_excludes_when_user_persona_not_listed() -> None:
    assert _audience_matches_persona("persona = admin", "member") is False


def test_audience_with_no_persona_clause_matches_conservatively() -> None:
    """A predicate that uses entity-state aggregates but no persona
    clause should match — the persona compiler is the resolver's
    business, not v0.71.2's. False positives here are caught at the
    next layer."""
    assert _audience_matches_persona("entity.Task.count = 0", "admin") is True


def test_audience_empty_string_matches() -> None:
    assert _audience_matches_persona("", "admin") is True


# ---------------------------------------------------------------------------
# Target → surface matcher
# ---------------------------------------------------------------------------


def test_target_whole_surface_matches() -> None:
    assert _step_target_matches_surface("surface.task_list", "task_list") is True


def test_target_action_matches_parent_surface() -> None:
    assert _step_target_matches_surface("surface.task_list.action.create", "task_list") is True


def test_target_field_matches_parent_surface() -> None:
    assert _step_target_matches_surface("surface.task_create.field.title", "task_create") is True


def test_target_mismatch_surface_name() -> None:
    assert _step_target_matches_surface("surface.task_list", "task_create") is False


def test_target_non_surface_prefix_rejected() -> None:
    assert _step_target_matches_surface("entity.Task", "task_list") is False


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


def test_select_next_step_first_when_no_progress() -> None:
    guide = _guide([_step("s1"), _step("s2"), _step("s3")])
    assert _select_next_step(guide, None).name == "s1"


def test_select_next_step_skips_completed() -> None:
    guide = _guide([_step("s1"), _step("s2"), _step("s3")])
    progress = OnboardingProgress(
        id="r",
        user_id="u",
        guide_name="g",
        guide_version=1,
        current_step=None,
        completed_steps=["s1"],
    )
    assert _select_next_step(guide, progress).name == "s2"


def test_select_next_step_skips_dismissed() -> None:
    guide = _guide([_step("s1"), _step("s2"), _step("s3")])
    progress = OnboardingProgress(
        id="r",
        user_id="u",
        guide_name="g",
        guide_version=1,
        current_step=None,
        dismissed_steps=["s1", "s2"],
    )
    assert _select_next_step(guide, progress).name == "s3"


def test_select_next_step_returns_none_when_all_resolved() -> None:
    guide = _guide([_step("s1"), _step("s2")])
    progress = OnboardingProgress(
        id="r",
        user_id="u",
        guide_name="g",
        guide_version=1,
        current_step=None,
        completed_steps=["s1"],
        dismissed_steps=["s2"],
    )
    assert _select_next_step(guide, progress) is None


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
