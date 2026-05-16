"""Guide-concordance linker pass (#1106 follow-up, v0.71.0).

Runs as a separate stage of ``build_appspec`` after surfaces have been
generated and the FK graph has been built. Validates that every guide's
stated next-action matches what the DSL actually models — drift becomes
a compile error, not a runtime surprise.

Four checks, in order:

1. **Attachment** — ``GuideStep.target`` resolves to a real surface +
   (optionally) an action / field / section that exists.
2. **Completion** — ``GuideStep.complete_on`` references a real event,
   surface, or field. Entity-lifecycle shorthand (``entity.X.created``)
   is recognised; hless topic.event refs are checked against the
   project's ``streams`` block; ``field_filled`` paths resolve to a
   real ``(entity, field)`` pair.
3. **CTA target** — ``cta_target`` is a real surface and the guide's
   audience persona has ``permit:`` access to it.
4. **Step-order integrity** — every name in ``GuideSpec.step_order``
   resolves to a step in ``GuideSpec.steps``. Duplicates fail. Steps
   not listed produce a warning string (not an error).

The pass returns ``(errors, warnings)`` — same shape as
``validate_references``. The caller raises ``LinkError`` if errors is
non-empty.

The audience predicate itself is NOT compiled here — it reuses the
``scope:`` predicate algebra and is recorded as a raw string in v0.71.0.
Predicate compilation lives in a later pass (v0.71.1) that runs after
the FK graph is built; for the MVP we only check that the persona
mentioned in the audience exists.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ir


# Recognised entity-lifecycle events. Any ``entity.<Name>.<lifecycle>``
# reference must use one of these lifecycle suffixes.
_ENTITY_LIFECYCLES = frozenset({"created", "updated", "deleted"})

# ``persona = <name>`` lifted out of an audience predicate. Multiple
# persona references in a single predicate are all surfaced.
_PERSONA_REF = re.compile(r"\bpersona\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")


def check_guide_concordance(
    guides: list[ir.GuideSpec],
    *,
    surfaces: list[ir.SurfaceSpec],
    entities: list[ir.EntitySpec],
    personas: list[ir.PersonaSpec],
    streams: list[ir.StreamSpec],
) -> tuple[list[str], list[str]]:
    """Run all four concordance checks. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    surface_by_name = {s.name: s for s in surfaces}
    entity_by_name = {e.name: e for e in entities}
    persona_ids = {p.id for p in personas}

    hless_events: set[str] = set()
    for stream in streams:
        topic = getattr(stream, "topic", None) or getattr(stream, "name", "")
        for ev in getattr(stream, "events", []) or []:
            ev_name = getattr(ev, "name", None) or getattr(ev, "event_type", "")
            if topic and ev_name:
                hless_events.add(f"{topic}.{ev_name}")

    for guide in guides:
        # ── audience persona ────────────────────────────────────────
        for match in _PERSONA_REF.finditer(guide.audience or ""):
            persona = match.group(1)
            if persona not in persona_ids:
                errors.append(
                    f"guide {guide.name!r}: audience references unknown "
                    f"persona {persona!r}; known personas: {sorted(persona_ids)}"
                )

        # ── step-order integrity ────────────────────────────────────
        step_names = {s.name for s in guide.steps}
        seen_in_order: set[str] = set()
        for name in guide.step_order:
            if name not in step_names:
                errors.append(
                    f"guide {guide.name!r}: step_order names {name!r} which is "
                    f"not declared in steps; declared steps: {sorted(step_names)}"
                )
            if name in seen_in_order:
                errors.append(f"guide {guide.name!r}: step_order lists {name!r} twice")
            seen_in_order.add(name)

        orphans = step_names - set(guide.step_order)
        for name in sorted(orphans):
            warnings.append(
                f"guide {guide.name!r}: step {name!r} is declared but not "
                "listed in step_order — orphan (never fires)"
            )

        # ── per-step attachment + completion + cta ──────────────────
        for step in guide.steps:
            _check_step_target(guide, step, surface_by_name, entity_by_name, errors)
            _check_step_completion(
                guide, step, surface_by_name, entity_by_name, hless_events, errors
            )
            _check_step_cta(guide, step, surface_by_name, errors)

    return errors, warnings


def _check_step_target(
    guide: ir.GuideSpec,
    step: ir.GuideStep,
    surface_by_name: dict[str, ir.SurfaceSpec],
    entity_by_name: dict[str, ir.EntitySpec],
    errors: list[str],
) -> None:
    """Resolve ``GuideStep.target`` against the DSL.

    Recognised shapes:
      surface.<name>
      surface.<name>.action.<action_name>
      surface.<name>.field.<field_name>
      surface.<name>.section.<section_name>
    """
    target = step.target or ""
    parts = target.split(".")
    if len(parts) < 2 or parts[0] != "surface":
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: target {target!r} "
            "must start with 'surface.<name>'"
        )
        return

    surface_name = parts[1]
    surface = surface_by_name.get(surface_name)
    if surface is None:
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: target surface "
            f"{surface_name!r} does not exist"
        )
        return

    if len(parts) == 2:
        return  # whole-surface target — done

    if len(parts) != 4:
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: target {target!r} "
            "has unexpected shape; expected surface.<name>(.action|.field|"
            ".section).<id>"
        )
        return

    kind, ident = parts[2], parts[3]
    if kind == "action":
        if not any(a.name == ident for a in (surface.actions or [])):
            errors.append(
                f"guide {guide.name!r} step {step.name!r}: surface "
                f"{surface_name!r} has no action {ident!r}"
            )
    elif kind == "section":
        if not any(s.name == ident for s in (surface.sections or [])):
            errors.append(
                f"guide {guide.name!r} step {step.name!r}: surface "
                f"{surface_name!r} has no section {ident!r}"
            )
    elif kind == "field":
        # Resolve via the surface's entity (each section names entity fields).
        entity_ref = getattr(surface, "entity_ref", None)
        if entity_ref:
            entity = entity_by_name.get(entity_ref)
            if entity is not None and not any(f.name == ident for f in entity.fields):
                errors.append(
                    f"guide {guide.name!r} step {step.name!r}: surface "
                    f"{surface_name!r} (entity {entity_ref!r}) has no field {ident!r}"
                )
    else:
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: target {target!r} "
            f"has unknown sub-kind {kind!r}; expected action|field|section"
        )


def _check_step_completion(
    guide: ir.GuideSpec,
    step: ir.GuideStep,
    surface_by_name: dict[str, ir.SurfaceSpec],
    entity_by_name: dict[str, ir.EntitySpec],
    hless_events: set[str],
    errors: list[str],
) -> None:
    """Resolve ``GuideStep.complete_on``.

    Only EVENT and FIELD_FILLED kinds need cross-reference checks;
    CLICK and DISMISS are validated by the parser (no payload).
    """
    co = step.complete_on
    kind = co.kind.value if hasattr(co.kind, "value") else str(co.kind)

    if kind == "event":
        ref = co.event_ref or ""
        if not ref:
            errors.append(f"guide {guide.name!r} step {step.name!r}: complete_on event missing ref")
            return
        # Entity lifecycle shape: entity.<Name>.<lifecycle>
        if ref.startswith("entity."):
            parts = ref.split(".")
            if len(parts) != 3:
                errors.append(
                    f"guide {guide.name!r} step {step.name!r}: complete_on "
                    f"event ref {ref!r} malformed; expected "
                    "entity.<Name>.<created|updated|deleted>"
                )
                return
            ent_name, lifecycle = parts[1], parts[2]
            if ent_name not in entity_by_name:
                errors.append(
                    f"guide {guide.name!r} step {step.name!r}: complete_on "
                    f"event references unknown entity {ent_name!r}"
                )
            if lifecycle not in _ENTITY_LIFECYCLES:
                errors.append(
                    f"guide {guide.name!r} step {step.name!r}: complete_on "
                    f"event lifecycle {lifecycle!r} not one of "
                    f"{sorted(_ENTITY_LIFECYCLES)}"
                )
            return
        # hless topic.event shape — must appear in the streams index.
        if hless_events and ref not in hless_events:
            errors.append(
                f"guide {guide.name!r} step {step.name!r}: complete_on event "
                f"{ref!r} not declared in any hless stream; known events: "
                f"{sorted(hless_events) or '(none)'}"
            )

    elif kind == "field_filled":
        path = co.field_filled or ""
        parts = path.split(".")
        if len(parts) != 4 or parts[0] != "surface" or parts[2] != "field":
            errors.append(
                f"guide {guide.name!r} step {step.name!r}: field_filled "
                f"path {path!r} must be surface.<name>.field.<field_name>"
            )
            return
        surface = surface_by_name.get(parts[1])
        if surface is None:
            errors.append(
                f"guide {guide.name!r} step {step.name!r}: field_filled "
                f"surface {parts[1]!r} does not exist"
            )
            return
        entity_ref = getattr(surface, "entity_ref", None)
        if entity_ref:
            entity = entity_by_name.get(entity_ref)
            if entity is not None and not any(f.name == parts[3] for f in entity.fields):
                errors.append(
                    f"guide {guide.name!r} step {step.name!r}: field_filled "
                    f"references unknown field {parts[3]!r} on entity "
                    f"{entity_ref!r}"
                )


def _check_step_cta(
    guide: ir.GuideSpec,
    step: ir.GuideStep,
    surface_by_name: dict[str, ir.SurfaceSpec],
    errors: list[str],
) -> None:
    """``cta_target`` must point at a real surface.

    Permit-access check (does the audience persona have access?) is
    deferred to v0.71.1 — needs the predicate algebra compiled. For
    v0.71.0 we only validate existence; an inaccessible-surface CTA
    will surface at runtime as a 403 and that's a separate failure
    mode worth seeing in development.
    """
    if not step.cta_target:
        return
    if not step.cta_target.startswith("surface."):
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: cta_target "
            f"{step.cta_target!r} must start with 'surface.<name>'"
        )
        return
    name = step.cta_target.removeprefix("surface.").split(".")[0]
    if name not in surface_by_name:
        errors.append(
            f"guide {guide.name!r} step {step.name!r}: cta_target surface {name!r} does not exist"
        )
