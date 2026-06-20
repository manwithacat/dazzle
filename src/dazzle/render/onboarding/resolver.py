"""Active-step resolution for guided onboarding (v0.71.2).

Given a (user, surface) pair, returns the guide step (if any) that
should render as an overlay on this page-load. Pure functions plus a
single repository-backed entry point.

Algorithm:

1. **Audience match.** Walk every ``GuideSpec`` in the AppSpec.
   Match the user's persona against the guide's ``audience``
   predicate. v0.71.2 supports the simple ``persona = <id>`` shape
   only — full predicate compilation arrives in v0.71.x once the
   predicate algebra is wired through. Multi-clause audiences match
   if any ``persona = <id>`` clause matches the user's persona.

2. **Progression lookup.** For each candidate guide, fetch the
   user's ``OnboardingProgress`` row. Skip guides marked complete.

3. **Next-step selection.** Walk the guide's ``step_order``; pick
   the first step that's not in ``completed_steps`` AND not in
   ``dismissed_steps``.

4. **Surface filter.** Return the step iff its ``target`` resolves
   to the surface the caller is rendering. Whole-surface targets
   (``surface.<name>``) match any page for that surface;
   action / field / section targets also match — the caller's page
   is the same surface, the inner element is a positioning hint
   the renderer or v0.71.3 client JS will act on.

Returns ``(GuideSpec, GuideStep)`` or ``None``. The caller composes
this with :func:`dazzle.http.runtime.onboarding.renderer.render_step`
to get the HTML.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from .state import OnboardingProgress

if TYPE_CHECKING:
    from dazzle.core import ir


class OnboardingStateLookup(Protocol):
    """Subset of ``OnboardingStateRepository`` the resolver needs.

    Protocol-typed so the render layer doesn't have to import the
    concrete repository class (which lives in ``dazzle.http``). Any
    object with a matching ``get`` method satisfies this contract —
    the real repository, an in-memory test double, or a mock.
    """

    def get(
        self, user_id: str, guide_name: str, guide_version: int = 1
    ) -> OnboardingProgress | None: ...


_PERSONA_CLAUSE = re.compile(r"\bpersona\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")


def _audience_matches_persona(audience: str, user_persona: str) -> bool:
    """Return True if the audience predicate names ``user_persona``.

    v0.71.2 simple matcher: any ``persona = <id>`` clause in the
    predicate counts as a match. Predicates without a persona clause
    (e.g. ``entity.Task.count = 0``) return True conservatively — a
    misnamed predicate is the predicate compiler's problem, not the
    resolver's. The v0.71.3 wiring will replace this with the real
    compiled predicate evaluator.
    """
    matches = [m.group(1) for m in _PERSONA_CLAUSE.finditer(audience or "")]
    if not matches:
        return True
    return user_persona in matches


def _step_target_matches_surface(step_target: str, surface_name: str) -> bool:
    """Return True iff the step's ``target`` resolves to ``surface_name``.

    Recognised shapes (consistent with the concordance check):
    - ``surface.<name>``                              — whole-surface
    - ``surface.<name>.action.<action_name>``         — action
    - ``surface.<name>.field.<field_name>``           — field
    - ``surface.<name>.section.<section_name>``       — section
    """
    if not step_target.startswith("surface."):
        return False
    parts = step_target.split(".")
    if len(parts) < 2:
        return False
    return parts[1] == surface_name


def _select_next_step(
    guide: ir.GuideSpec,
    progress: OnboardingProgress | None,
) -> ir.GuideStep | None:
    """Pick the first step in ``step_order`` that isn't completed or
    dismissed. Returns ``None`` if every step has been resolved one way
    or the other."""
    completed = set(progress.completed_steps) if progress else set()
    dismissed = set(progress.dismissed_steps) if progress else set()
    by_name = {s.name: s for s in guide.steps}
    for name in guide.step_order:
        if name in completed or name in dismissed:
            continue
        step = by_name.get(name)
        if step is not None:
            return step
    return None


def resolve_active_step(
    *,
    user_id: str,
    user_persona: str,
    surface_name: str,
    app: ir.AppSpec,
    repo: OnboardingStateLookup,
) -> tuple[ir.GuideSpec, ir.GuideStep] | None:
    """Walk the guides, find the one applicable to (user, surface).

    Returns ``(guide, step)`` if a step should render on this page,
    else ``None``. Stops at the first match — guides are evaluated
    in declaration order, so author intent (declare the most
    important guide first) controls priority.
    """
    for guide in app.guides:
        if not _audience_matches_persona(guide.audience, user_persona):
            continue
        progress = repo.get(user_id=user_id, guide_name=guide.name, guide_version=1)
        if progress is not None and progress.is_complete:
            continue
        step = _select_next_step(guide, progress)
        if step is None:
            continue
        if _step_target_matches_surface(step.target, surface_name):
            return guide, step
    return None
