"""
Experience compiler — converts ExperienceSpec + state into template context.

Builds the ExperienceContext needed to render a single step of an
experience flow, including the progress indicator, transition buttons,
and the inner PageContext for the step's surface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.experiences import StepKind
from dazzle_ui.converters.template_compiler import compile_surface_to_context
from dazzle_ui.runtime.template_context import (
    ExperienceContext,
    ExperienceStepContext,
    ExperienceTransitionContext,
    PageContext,
)

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, ExperienceSpec, SurfaceSpec
    from dazzle_ui.runtime.experience_state import ExperienceState

logger = logging.getLogger(__name__)

# Maps transition event names to (label, button style)
_EVENT_STYLES: dict[str, tuple[str, str]] = {
    "success": ("Continue", "primary"),
    "continue": ("Continue", "primary"),
    "approve": ("Approve", "primary"),
    "failure": ("Report Issue", "error"),
    "cancel": ("Cancel", "ghost"),
    "back": ("Back", "ghost"),
    "reject": ("Reject", "error"),
    "skip": ("Skip", "ghost"),
}


def _find_surface(appspec: AppSpec, name: str) -> SurfaceSpec | None:
    """Look up a surface by name in the appspec."""
    for surface in appspec.surfaces:
        if surface.name == name:
            return surface
    return None


def _find_entity(appspec: AppSpec, entity_ref: str) -> EntitySpec | None:
    """Look up an entity by name in the appspec domain."""
    if appspec.domain:
        return appspec.domain.get_entity(entity_ref)
    return None


def _evaluate_when_for_progress(when_expr: str, data: dict) -> bool:
    """Lightweight when-guard check for progress bar display.

    Re-implements the same logic as ``_evaluate_when_guard`` in
    ``experience_routes`` to avoid a cross-module import.
    """
    for op in ("!=", ">=", "<=", "=", ">", "<"):
        if f" {op} " in when_expr:
            left, right = when_expr.split(f" {op} ", 1)
            left = left.strip()
            right = right.strip()
            resolved = _resolve_prefill_expression(left, data)
            if resolved is None:
                return False
            rval: Any
            if right.lower() == "true":
                rval = True
            elif right.lower() == "false":
                rval = False
            elif right.startswith('"') and right.endswith('"'):
                rval = right[1:-1]
            else:
                try:
                    rval = int(right)
                except ValueError:
                    try:
                        rval = float(right)
                    except ValueError:
                        rval = right
            if op == "=":
                return resolved == rval
            elif op == "!=":
                return resolved != rval
            elif op == ">":
                return resolved > rval
            elif op == "<":
                return resolved < rval
            elif op == ">=":
                return resolved >= rval
            elif op == "<=":
                return resolved <= rval
            break
    return True


def _resolve_prefill_expression(expression: str, data: dict) -> Any:
    """Resolve a prefill expression against state data.

    - String literal (starts/ends with ``"``): strip quotes, return string.
    - Dotted path (``context.X.Y``): navigate ``data["X"]["Y"]``.
    """
    if expression.startswith('"') and expression.endswith('"'):
        return expression[1:-1]
    # Dotted path resolution
    parts = expression.split(".")
    if parts and parts[0] == "context":
        parts = parts[1:]
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def compile_experience_context(
    experience: ExperienceSpec,
    state: ExperienceState,
    appspec: AppSpec,
    app_prefix: str = "",
) -> ExperienceContext:
    """Compile an ExperienceSpec + current state into a renderable ExperienceContext.

    Args:
        experience: The experience specification from IR.
        state: Current flow state (step, completed steps, data).
        appspec: Full application spec for surface/entity lookup.
        app_prefix: URL prefix for page routes (e.g. "/app").

    Returns:
        ExperienceContext ready for template rendering.
    """
    exp_base = f"{app_prefix}/experiences/{experience.name}"

    # Build step progress indicators
    steps: list[ExperienceStepContext] = []
    for step in experience.steps:
        step_title = step.name.replace("_", " ").title()
        # Mark conditional steps as skipped if their guard evaluates to false
        is_skipped = False
        if step.when and step.name != state.step:
            is_skipped = not _evaluate_when_for_progress(step.when, state.data)
        steps.append(
            ExperienceStepContext(
                name=step.name,
                title=step_title,
                is_current=step.name == state.step,
                is_completed=step.name in state.completed,
                is_skipped=is_skipped,
                url=f"{exp_base}/{step.name}",
            )
        )

    # Get the current step spec
    current_step = experience.get_step(state.step)

    # Build transition buttons for the current step
    transitions: list[ExperienceTransitionContext] = []
    if current_step:
        for tr in current_step.transitions:
            label, style = _EVENT_STYLES.get(
                tr.event, (tr.event.replace("_", " ").title(), "primary")
            )
            transitions.append(
                ExperienceTransitionContext(
                    event=tr.event,
                    label=label,
                    style=style,
                    url=f"{exp_base}/{state.step}?event={tr.event}",
                )
            )

    # Compile the inner page context for the current step's surface
    page_context: PageContext | None = None
    if current_step and current_step.kind == StepKind.SURFACE and current_step.surface:
        surface = _find_surface(appspec, current_step.surface)
        if surface:
            entity = _find_entity(appspec, surface.entity_ref) if surface.entity_ref else None
            page_context = compile_surface_to_context(surface, entity, app_prefix=app_prefix)
            # Rewrite form action URL to point to the experience transition endpoint
            if page_context.form:
                page_context.form = page_context.form.model_copy(
                    update={
                        "action_url": f"{exp_base}/{state.step}?event=success",
                        "cancel_url": f"{exp_base}/{state.step}?event=cancel"
                        if any(t.event == "cancel" for t in current_step.transitions)
                        else f"{app_prefix}/",
                    }
                )
                # Resolve prefill expressions into form initial_values
                if current_step.prefills:
                    prefill_values = dict(page_context.form.initial_values)
                    for pf in current_step.prefills:
                        resolved = _resolve_prefill_expression(pf.expression, state.data)
                        if resolved is not None:
                            prefill_values[pf.field] = resolved
                    page_context.form = page_context.form.model_copy(
                        update={"initial_values": prefill_values}
                    )

    return ExperienceContext(
        name=experience.name,
        title=experience.title or experience.name.replace("_", " ").title(),
        steps=steps,
        current_step=state.step,
        transitions=transitions,
        page_context=page_context,
    )
