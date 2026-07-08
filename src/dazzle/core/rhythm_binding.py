"""Rhythm scene binding derivation (#1559 slice 3).

A scene that cites a story need not re-declare ``surface`` / ``action`` /
``entity`` — the cited story already implies them. This module derives the
omitted fields so a rhythm can be a thin *temporal ordering over story
references* rather than a re-description of behaviour already captured in the
story.

Rules:

- **Explicit always wins.** A field the author wrote is never overridden.
- **entity / action are exact** — they come straight from the story
  (``entities[0]`` and a trigger→verb map), so they are fully traceable.
- **surface derivation is LOUD on ambiguity.** A surface is derived only when
  exactly one surface serves the ``(entity, mode)`` the story implies. Zero or
  more-than-one candidates is a hard error asking for an explicit ``on:`` —
  never a silent guess. This keeps an inferred binding either obviously correct
  or a clear ask, which is what keeps the derivation traceable (the MDE
  hidden-derivation failure mode).

Derivation runs once, at link time, and rebuilds the affected ``SceneSpec``s so
every downstream consumer (fidelity, gaps, composition, KG seeding) sees a fully
resolved scene with no special-casing.
"""

from __future__ import annotations

from .ir.rhythm import RhythmSpec
from .ir.stories import StorySpec, StoryTrigger
from .ir.surfaces import SurfaceMode, SurfaceSpec

# The surface mode a persona uses to perform each trigger.
_TRIGGER_MODE: dict[StoryTrigger, SurfaceMode] = {
    StoryTrigger.FORM_SUBMITTED: SurfaceMode.CREATE,
    StoryTrigger.STATUS_CHANGED: SurfaceMode.VIEW,
    StoryTrigger.USER_CLICK: SurfaceMode.LIST,
}

# The default action verb (standard vocabulary) each trigger implies.
_TRIGGER_ACTION: dict[StoryTrigger, str] = {
    StoryTrigger.FORM_SUBMITTED: "submit",
    StoryTrigger.STATUS_CHANGED: "submit",
    StoryTrigger.USER_CLICK: "browse",
}


def resolve_rhythm(
    rhythm: RhythmSpec,
    surfaces: dict[str, SurfaceSpec],
    stories: dict[str, StorySpec],
) -> tuple[RhythmSpec, list[str]]:
    """Derive omitted scene bindings from cited stories.

    Returns the (possibly rebuilt) rhythm plus any derivation errors — an
    ambiguous or underivable surface for a story-only scene.
    """
    by_entity_mode: dict[tuple[str, SurfaceMode], list[str]] = {}
    for surface in surfaces.values():
        if surface.entity_ref:
            by_entity_mode.setdefault((surface.entity_ref, surface.mode), []).append(surface.name)

    errors: list[str] = []
    changed = False
    new_phases = []
    for phase in rhythm.phases:
        new_scenes = []
        for scene in phase.scenes:
            update, scene_errors = _derive_scene(scene, rhythm.name, stories, by_entity_mode)
            errors.extend(scene_errors)
            if update:
                new_scenes.append(scene.model_copy(update=update))
                changed = True
            else:
                new_scenes.append(scene)
        new_phases.append(phase.model_copy(update={"scenes": new_scenes}))

    if not changed:
        return rhythm, errors
    return rhythm.model_copy(update={"phases": new_phases}), errors


def _derive_scene(
    scene: object,
    rhythm_name: str,
    stories: dict[str, StorySpec],
    by_entity_mode: dict[tuple[str, SurfaceMode], list[str]],
) -> tuple[dict[str, object], list[str]]:
    """Compute the field updates + errors for one scene. Empty update = no
    derivation (explicit, story-less, or unresolvable story)."""
    story_ref = getattr(scene, "story", None)
    if not story_ref:
        return {}, []
    story = stories.get(story_ref)
    if story is None:
        # The unknown-story reference is reported by the linker's own check;
        # don't derive (and don't pile on a second error) here.
        return {}, []

    update: dict[str, object] = {}

    entity = getattr(scene, "entity", None) or (story.entities[0] if story.entities else None)
    if entity and entity != getattr(scene, "entity", None):
        update["entity"] = entity

    if not getattr(scene, "actions", None):
        verb = _TRIGGER_ACTION.get(story.trigger)
        if verb:
            update["actions"] = [verb]

    errors: list[str] = []
    if getattr(scene, "surface", None) is None:
        surface, surface_error = _derive_surface(scene, rhythm_name, story, entity, by_entity_mode)
        if surface is not None:
            update["surface"] = surface
        if surface_error:
            errors.append(surface_error)

    return update, errors


def _derive_surface(
    scene: object,
    rhythm_name: str,
    story: StorySpec,
    entity: str | None,
    by_entity_mode: dict[tuple[str, SurfaceMode], list[str]],
) -> tuple[str | None, str | None]:
    """Derive the surface for a story-only scene, or return a loud error."""
    prefix = f"Rhythm '{rhythm_name}' scene '{scene.name}' cites story '{story.story_id}'"  # type: ignore[attr-defined]
    mode = _TRIGGER_MODE.get(story.trigger)
    if entity is None or mode is None:
        return None, (
            f"{prefix} but no surface can be derived "
            f"(trigger '{story.trigger.value}' has no default surface, or the story "
            f"names no entity) — add an explicit `on:`."
        )
    candidates = by_entity_mode.get((entity, mode), [])
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, (
            f"{prefix} but no {mode.value} surface exists for entity '{entity}' — "
            f"add an explicit `on:`."
        )
    return None, (
        f"{prefix} but {len(candidates)} {mode.value} surfaces serve entity '{entity}' "
        f"({sorted(candidates)}) — add an explicit `on:`."
    )
