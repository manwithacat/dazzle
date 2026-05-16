"""Runtime support for the guided-onboarding feature (v0.71.1).

This package owns:

- ``OnboardingStateRepository`` — Postgres data layer for per-user
  guide progression. The schema is managed by the standard Dazzle
  migration flow (the ``OnboardingState`` framework entity gets a
  table when the project runs ``dazzle db upgrade``).
- (v0.71.2+) typed Fragment renderer + page wiring that consumes the
  repository to render overlays at request time.

The framework entity is declared in
``dazzle.core.ir.onboarding_state.ONBOARDING_STATE_FIELDS`` and
auto-injected by the linker when at least one ``guide`` block is
declared.
"""

from .renderer import UnknownStepKindError, has_builder, render_step
from .resolver import resolve_active_step
from .routes import create_onboarding_routes
from .state_repository import OnboardingProgress, OnboardingStateRepository

__all__ = [
    "OnboardingProgress",
    "OnboardingStateRepository",
    "UnknownStepKindError",
    "create_onboarding_routes",
    "has_builder",
    "render_step",
    "resolve_active_step",
]
