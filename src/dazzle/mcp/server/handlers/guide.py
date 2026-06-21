"""MCP handlers for guided-onboarding inspection (v0.71.7).

Stateless reads only, per ADR-0002 — writes (mark step complete /
dismissed) stay on the HTTP routes shipped in v0.71.2 since they
need an authenticated user identity.

Operations:

- ``list`` — every guide declared in the AppSpec with audience +
  step count + ordering. Cheap overview for agents picking what
  to inspect next.
- ``get`` — one guide's full structure (steps, audience, completion
  criteria, CTA targets). Caller passes ``name``.
- ``concordance`` — runs the linker's concordance check in isolation
  against the AppSpec, returns errors + warnings. Same shape as
  ``dazzle validate`` for guides only; useful when an agent wants
  to verify a guide they're authoring before committing the DSL.
- ``narrate`` — materialises the linear narrative of one guide as
  ordered ``(step_name, kind, title, body, target)`` rows. The
  agent-readable equivalent of the rendered overlay sequence.
"""

import json
import logging
from pathlib import Path
from typing import Any

from .common import error_response, load_project_appspec, wrap_handler_errors

logger = logging.getLogger(__name__)


@wrap_handler_errors
def guide_list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Summary of every guide. Agents call this first to discover
    what's declared."""
    appspec = load_project_appspec(project_root)
    guides = getattr(appspec, "guides", None) or []
    payload = [
        {
            "name": g.name,
            "title": g.title,
            "audience": g.audience,
            "step_count": len(g.steps),
            "step_order": list(g.step_order),
            "has_on_complete": g.on_complete is not None,
        }
        for g in guides
    ]
    return json.dumps({"guides": payload, "total": len(payload)}, indent=2)


@wrap_handler_errors
def guide_get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Full IR for one guide. Caller passes ``name``."""
    name = args.get("name", "")
    if not name:
        return error_response("'name' argument is required")
    appspec = load_project_appspec(project_root)
    guides = getattr(appspec, "guides", None) or []
    spec = next((g for g in guides if g.name == name), None)
    if spec is None:
        return error_response(f"Unknown guide: {name!r}; known: {[g.name for g in guides]}")
    return json.dumps(spec.model_dump(mode="json"), indent=2)


@wrap_handler_errors
def guide_concordance_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run the concordance check (#1106 follow-up) in isolation.

    Returns the same ``(errors, warnings)`` shape ``dazzle validate``
    produces internally. Agents use this to verify a guide they're
    authoring before committing the DSL.
    """
    appspec = load_project_appspec(project_root)
    from dazzle.core.guide_concordance import check_guide_concordance

    errors, warnings = check_guide_concordance(
        getattr(appspec, "guides", None) or [],
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    return json.dumps(
        {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        },
        indent=2,
    )


@wrap_handler_errors
def guide_narrate_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Linear narrative for one guide — agent-readable equivalent of
    the rendered overlay sequence.

    Returns the steps in ``step_order``, each row carrying
    ``(name, kind, title, body, target, complete_on, cta_target)``.
    Orphan steps (declared but not in step_order) are returned in
    a separate list. Useful for materialising the guide's intent
    without running the renderer.
    """
    name = args.get("name", "")
    if not name:
        return error_response("'name' argument is required")
    appspec = load_project_appspec(project_root)
    guides = getattr(appspec, "guides", None) or []
    spec = next((g for g in guides if g.name == name), None)
    if spec is None:
        return error_response(f"Unknown guide: {name!r}; known: {[g.name for g in guides]}")

    by_name = {s.name: s for s in spec.steps}
    ordered_rows: list[dict[str, Any]] = []
    for step_name in spec.step_order:
        step = by_name.get(step_name)
        if step is None:
            continue
        ordered_rows.append(_step_to_row(step))

    orphan_rows = [_step_to_row(s) for s in spec.steps if s.name not in set(spec.step_order)]
    return json.dumps(
        {
            "name": spec.name,
            "title": spec.title,
            "audience": spec.audience,
            "steps_in_order": ordered_rows,
            "orphan_steps": orphan_rows,
            "on_complete": spec.on_complete.model_dump(mode="json")
            if spec.on_complete is not None
            else None,
        },
        indent=2,
    )


def _step_to_row(step: Any) -> dict[str, Any]:
    """Flatten one ``GuideStep`` into the narrate-output shape."""
    co = step.complete_on
    co_kind = co.kind.value if hasattr(co.kind, "value") else str(co.kind)
    co_payload: dict[str, Any] = {"kind": co_kind}
    if co.event_ref:
        co_payload["event_ref"] = co.event_ref
    if co.field_filled:
        co_payload["field_filled"] = co.field_filled
    return {
        "name": step.name,
        "kind": step.kind.value if hasattr(step.kind, "value") else str(step.kind),
        "title": step.title,
        "body": step.body,
        "target": step.target,
        "placement": step.placement,
        "cta_label": step.cta_label,
        "cta_target": step.cta_target,
        "audience_when": step.audience_when,
        "complete_on": co_payload,
    }
