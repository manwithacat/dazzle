"""Experience-shell renderer (Phase 4, v0.67.71).

Renders the experience-flow inner HTML in Python, with the rich step
bodies (form, detail, table) still served by Jinja sub-templates. The
outer shell — title, step progress indicator, transition buttons,
ready/placeholder branches — runs entirely in Python via `html.escape`.

This isolates `experience_routes.py` from any direct Jinja imports
(it now imports `render_experience_inner_html` from here) and keeps
the remaining Jinja surface concentrated in one module pending the
form_field / detail_view / filterable_table migrations.

The legacy `experience/_content.html` Jinja template is retired —
the outer shell rendering is owned here, and each rich-step branch
calls `render_fragment` for its specific sub-template inline.
"""

from __future__ import annotations

import html as _html_mod
from typing import Any


def _render_transition_button(tr: Any) -> str:
    """Inline mirror of `macros/experience_transition.html`."""
    style = _html_mod.escape(str(getattr(tr, "style", None) or "default"), quote=True)
    url = _html_mod.escape(str(getattr(tr, "url", "") or ""), quote=True)
    label = _html_mod.escape(str(getattr(tr, "label", "") or ""), quote=False)
    return (
        '<button type="button" '  # nosemgrep
        f'class="dz-experience-transition" '
        f'data-dz-transition-style="{style}" '
        f'hx-post="{url}" '
        f'hx-target="body" '
        f'hx-swap="innerHTML">'
        f"{label}</button>"
    )


def _render_transitions_row(
    transitions: list[Any],
    *,
    skip_success: bool = False,
    centered: bool = False,
) -> str:
    if not transitions:
        return ""
    parts: list[str] = []
    for tr in transitions:
        event = str(getattr(tr, "event", "") or "")
        if skip_success and event == "success":
            continue
        parts.append(_render_transition_button(tr))
    if not parts:
        return ""
    cls = "dz-experience-actions"
    if centered:
        cls += " dz-experience-actions-centered"
    return f'<div class="{cls}">{"".join(parts)}</div>'


def _render_step_progress(experience: Any) -> str:
    """Step progress indicator — the `<ol class="dz-steps">` strip."""
    steps = list(getattr(experience, "steps", None) or [])
    if len(steps) <= 1:
        return ""
    items: list[str] = []
    for idx, step in enumerate(steps):
        is_last = idx == len(steps) - 1
        name_attr = _html_mod.escape(str(getattr(step, "name", "") or ""), quote=True)
        title = _html_mod.escape(str(getattr(step, "title", "") or ""), quote=False)
        is_current = bool(getattr(step, "is_current", False))
        is_completed = bool(getattr(step, "is_completed", False)) or is_current
        item_cls = "dz-steps-item"
        if not is_last:
            item_cls += " is-not-last"
        current_attr = ' aria-current="step"' if is_current else ""
        completed_cls = " is-completed" if is_completed else ""
        connector = ""
        if not is_last:
            connector_cls = " is-completed" if getattr(step, "is_completed", False) else ""
            connector = f'<div class="dz-steps-connector{connector_cls}"></div>'
        items.append(
            f'<li class="{item_cls}" data-dz-exp-step="{name_attr}"{current_attr}>'  # nosemgrep
            '<div class="dz-steps-row">'
            f'<span class="dz-steps-circle{completed_cls}">{idx + 1}</span>'
            f'<span class="dz-steps-label{completed_cls}">{title}</span>'
            "</div>"
            f"{connector}"
            "</li>"
        )
    return f'<ol class="dz-steps">{"".join(items)}</ol>'


def _render_step_body(experience: Any) -> str:
    """Dispatch to the right step-body renderer.

    Form/detail/table step bodies still go through Jinja sub-templates
    (`components/detail_view.html`, `components/filterable_table.html`,
    plus the form_field macro chain). Simple branches (ready,
    placeholder, non-surface) inline in Python.
    """
    current_step_attr = _html_mod.escape(
        str(getattr(experience, "current_step", "") or ""), quote=True
    )
    page_context = getattr(experience, "page_context", None)
    transitions = list(getattr(experience, "transitions", None) or [])

    if page_context is None:
        # Non-surface step (process/integration)
        placeholder = (
            '<div class="dz-experience-placeholder">'
            '<div class="dz-experience-placeholder-title">Step in progress</div>'
            '<p class="dz-experience-placeholder-body">'
            "This step is being processed. Please wait or continue."
            "</p>"
            "</div>"
        )
        actions = _render_transitions_row(transitions, centered=True)
        return (
            f'<div class="dz-experience-step" data-dz-exp-current="{current_step_attr}">'
            f"{placeholder}{actions}"
            "</div>"
        )

    ctx_form = getattr(page_context, "form", None)
    ctx_detail = getattr(page_context, "detail", None)
    ctx_table = getattr(page_context, "table", None)

    if ctx_form is not None:
        # Form step — render through Jinja for now (form_field macro chain).
        from dazzle_ui.runtime.template_renderer import render_fragment

        body = render_fragment(  # nosemgrep
            "experience/_step_form.html",
            experience=experience,
            ctx=page_context,
        )
    elif ctx_detail is not None:
        from dazzle_ui.runtime.template_renderer import render_fragment

        body_inner = render_fragment(  # nosemgrep
            "components/detail_view.html",
            **(page_context.model_dump() if hasattr(page_context, "model_dump") else {}),
        )
        actions = _render_transitions_row(transitions)
        body = f"{body_inner}{actions}"
    elif ctx_table is not None:
        from dazzle_ui.runtime.template_renderer import render_fragment

        body_inner = render_fragment(  # nosemgrep
            "components/filterable_table.html",
            **(page_context.model_dump() if hasattr(page_context, "model_dump") else {}),
        )
        actions = _render_transitions_row(transitions)
        body = f"{body_inner}{actions}"
    else:
        ready = (
            '<div class="dz-experience-ready" role="alert"><span>This step is ready.</span></div>'
        )
        actions = _render_transitions_row(transitions)
        body = f"{ready}{actions}"

    return f'<div class="dz-experience-step" data-dz-exp-current="{current_step_attr}">{body}</div>'


def render_experience_inner_html(experience: Any) -> str:
    """Render the experience-flow inner HTML (Phase 4, v0.67.71).

    Replaces `render_fragment("experience/_content.html", experience=...)`.
    The outer shell (title, step progress, container) is Python; step
    bodies dispatch to typed branches or Jinja sub-templates.
    """
    name_attr = _html_mod.escape(str(getattr(experience, "name", "") or ""), quote=True)
    title = _html_mod.escape(str(getattr(experience, "title", "") or ""), quote=False)
    progress = _render_step_progress(experience)
    body = _render_step_body(experience)
    return (
        f'<div data-dz-experience="{name_attr}" class="dz-experience">'  # nosemgrep
        f'<h2 class="dz-experience-title">{title}</h2>'
        f"{progress}"
        f"{body}"
        "</div>"
    )
