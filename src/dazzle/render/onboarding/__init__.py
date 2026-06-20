"""Pure-Python helpers for guided onboarding (v0.71.3).

Split out of ``dazzle.http.runtime.onboarding`` so the UI layer can
import them without crossing the architectural boundary
(``dazzle.page.*`` must not import ``dazzle.http.*``). The DB-bound
repository + FastAPI routes stay in ``back``.

Contents:

- :class:`OnboardingProgress` — frozen dataclass for one
  ``onboarding_state`` row.
- :func:`render_step`, :func:`has_builder`,
  :class:`UnknownStepKindError` — HTML emission for guide steps.
- :func:`resolve_active_step` — pick the active step for a given
  ``(user, surface)`` against the AppSpec.
"""

from .renderer import UnknownStepKindError, has_builder, render_step
from .resolver import resolve_active_step
from .state import OnboardingProgress

__all__ = [
    "OnboardingProgress",
    "UnknownStepKindError",
    "has_builder",
    "render_step",
    "resolve_active_step",
]
