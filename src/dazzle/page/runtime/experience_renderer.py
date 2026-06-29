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
used to be Jinja sub-templates (now fully inline Python).
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


def _render_form_step_body(experience: Any, page_context: Any) -> str:
    """Inline-render the form-step body (Phase 4, v0.67.74).

    Replaces `experience/_step_form.html`. Composes:
      - `<form>` element with HTMX wiring (hx-post/hx-put; body posts
        form-urlencoded — json-enc was dropped in the htmx 4 migration)
      - empty `#form-errors` slot (htmx_error_response swaps content)
      - optional form_stepper (when sections are declared)
      - form fields rendered via `form_renderer.render_form_field`
      - submit button + transition buttons (excluding `success` event)
    """
    from dazzle.page.runtime.form_renderer import render_form_field, render_form_stepper

    form = getattr(page_context, "form", None)
    if form is None:
        return ""

    entity_name_attr = _html_mod.escape(str(getattr(form, "entity_name", "") or ""), quote=True)
    mode = str(getattr(form, "mode", "") or "")
    mode_attr = _html_mod.escape(mode, quote=True)
    method = str(getattr(form, "method", "") or "post").lower()
    action_url_attr = _html_mod.escape(str(getattr(form, "action_url", "") or ""), quote=True)
    hx_method = "put" if method == "put" else "post"
    submit_label = "Save & Continue" if mode == "edit" else "Submit"

    initial_values = getattr(form, "initial_values", None) or {}

    sections = getattr(form, "sections", None) or []
    if sections:
        stepper_html = render_form_stepper(form)
        stage_blocks: list[str] = []
        for idx, section in enumerate(sections):
            section_title = (
                section.get("title", "")
                if isinstance(section, dict)
                else getattr(section, "title", "")
            )
            section_title_html = _html_mod.escape(str(section_title or ""), quote=False)
            fields = (
                section.get("fields", [])
                if isinstance(section, dict)
                else getattr(section, "fields", None) or []
            )
            field_html = "".join(render_form_field(f, initial_values) for f in fields)
            hide_style = ' style="display:none"' if idx > 0 else ""
            stage_blocks.append(
                f'<div class="dz-wizard-stage" data-dz-stage="{idx}"{hide_style}>'  # nosemgrep
                f'<h3 class="dz-experience-stage-title">{section_title_html}</h3>'
                f"{field_html}"
                "</div>"
            )
        fields_body = stepper_html + "".join(stage_blocks)
    else:
        fields_body = "".join(
            render_form_field(f, initial_values) for f in (getattr(form, "fields", None) or [])
        )

    transition_buttons = "".join(
        _render_transition_button(tr)
        for tr in (getattr(experience, "transitions", None) or [])
        if str(getattr(tr, "event", "") or "") != "success"
    )

    return (
        '<div class="dz-experience-form-shell">'
        f'<form data-dazzle-form="{entity_name_attr}" '  # nosemgrep
        f'data-dazzle-form-mode="{mode_attr}" '
        f'hx-{hx_method}="{action_url_attr}" '
        f'hx-target="body" '
        f'hx-swap="innerHTML" '
        # htmx 4 migration: dropped hx-target-422/5* (response-targets ext gone;
        # the server's HX-Retarget header routes validation errors to
        # #form-errors), the forced application/json header + hx-ext="json-enc"
        # (htmx 4 posts url-encoded, which the handler now accepts).
        f'class="dz-experience-form-body">'
        '<div id="form-errors"></div>'
        f"{fields_body}"
        '<div class="dz-experience-actions">'
        # htmx 4: native hx-disabled-elt replaces the loading-states ext's
        # data-loading-disable; the native htmx-request class covers styling.
        '<button type="submit" class="dz-button dz-button-primary" '
        'hx-disabled-elt="this">'
        f"{submit_label}</button>"
        f"{transition_buttons}"
        "</div></form></div>"
    )


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


def _render_step_body(experience: Any, table_step_html: str = "") -> str:
    """Dispatch to the right step-body renderer.

    Form/detail bodies render via the typed Python renderers; a table-step
    body is pre-rendered by the http route (`table_step_html`) through the
    substrate, since the page layer cannot import the http dispatch seam
    (ADR-0049 Task 6). Simple branches (ready, placeholder, non-surface)
    inline in Python.
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
        # Form step — fully inline-rendered (v0.67.74).
        body = _render_form_step_body(experience, page_context)
    elif ctx_detail is not None:
        # Phase 4 (v0.67.75): inline-render via detail_renderer.
        from dazzle.page.runtime.detail_renderer import render_detail_view

        body_inner = render_detail_view(ctx_detail)
        actions = _render_transitions_row(transitions)
        body = f"{body_inner}{actions}"
    elif ctx_table is not None:
        # ADR-0049 Task 6: the experience table-step renders through the typed
        # substrate now (the legacy table_renderer is deleted). The http route
        # pre-renders the substrate list (it owns the dispatch seam, respecting
        # the page↛http import contract) and passes the HTML in via
        # `table_step_html`. Empty string means the route couldn't render it
        # (no services / no surface) — emit a loud placeholder rather than a
        # blank step (D4: no silent legacy fallback).
        if table_step_html:
            body_inner = table_step_html
        else:
            body_inner = (
                '<div class="dz-experience-ready" role="alert">'
                "<span>This list step could not be rendered.</span></div>"
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


def render_experience_inner_html(experience: Any, *, table_step_html: str = "") -> str:
    """Render the experience-flow inner HTML (Phase 4, v0.67.71).

    Replaces the legacy `experience/_content.html` Jinja render call.
    The outer shell (title, step progress, container) is Python; step
    bodies render via the typed renderers. A table-step body is rendered
    through the substrate by the http route and passed in as
    `table_step_html` (ADR-0049 Task 6 — the page layer cannot reach the
    http dispatch seam).
    """
    name_attr = _html_mod.escape(str(getattr(experience, "name", "") or ""), quote=True)
    title = _html_mod.escape(str(getattr(experience, "title", "") or ""), quote=False)
    progress = _render_step_progress(experience)
    body = _render_step_body(experience, table_step_html)
    return (
        f'<div data-dz-experience="{name_attr}" class="dz-experience">'  # nosemgrep
        f'<h2 class="dz-experience-title">{title}</h2>'
        f"{progress}"
        f"{body}"
        "</div>"
    )
