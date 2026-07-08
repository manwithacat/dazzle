"""Rhythm scene binding derivation (#1559 slice 3).

A scene citing a story may omit surface/action/entity; they are derived from the
story. Surface derivation is loud on ambiguity (never a silent guess).
"""

from types import SimpleNamespace

from dazzle.core.ir.rhythm import PhaseSpec, RhythmSpec, SceneSpec
from dazzle.core.ir.stories import StorySpec, StoryTrigger
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.core.rhythm_binding import resolve_rhythm


def _surface(name, entity, mode):
    return SimpleNamespace(name=name, entity_ref=entity, mode=mode)


def _story(sid, entities, trigger):
    return StorySpec(story_id=sid, title=sid, persona="p", trigger=trigger, entities=entities)


def _one_scene_rhythm(scene):
    return RhythmSpec(name="r", persona="p", phases=[PhaseSpec(name="ph", scenes=[scene])])


def _resolved_scene(rhythm, surfaces, stories):
    out, errs = resolve_rhythm(rhythm, surfaces, stories)
    return out.phases[0].scenes[0], errs


def test_derive_full_from_story():
    surfaces = {"device_create": _surface("device_create", "Device", SurfaceMode.CREATE)}
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.FORM_SUBMITTED)}
    scene, errs = _resolved_scene(
        _one_scene_rhythm(SceneSpec(name="s", story="ST-1")), surfaces, stories
    )
    assert errs == []
    assert scene.surface == "device_create"
    assert scene.actions == ["submit"]
    assert scene.entity == "Device"


def test_explicit_values_win():
    surfaces = {
        "device_create": _surface("device_create", "Device", SurfaceMode.CREATE),
        "device_edit": _surface("device_edit", "Device", SurfaceMode.EDIT),
    }
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.FORM_SUBMITTED)}
    scene = SceneSpec(
        name="s", surface="device_edit", actions=["review"], entity="Widget", story="ST-1"
    )
    resolved, errs = _resolved_scene(_one_scene_rhythm(scene), surfaces, stories)
    assert errs == []
    assert (resolved.surface, resolved.actions, resolved.entity) == (
        "device_edit",
        ["review"],
        "Widget",
    )


def test_trigger_maps_to_list_and_browse():
    surfaces = {"device_list": _surface("device_list", "Device", SurfaceMode.LIST)}
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.USER_CLICK)}
    scene, errs = _resolved_scene(
        _one_scene_rhythm(SceneSpec(name="s", story="ST-1")), surfaces, stories
    )
    assert errs == []
    assert scene.surface == "device_list"
    assert scene.actions == ["browse"]


def test_loud_when_no_matching_surface():
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.FORM_SUBMITTED)}
    scene, errs = _resolved_scene(_one_scene_rhythm(SceneSpec(name="s", story="ST-1")), {}, stories)
    assert scene.surface is None
    assert len(errs) == 1
    assert "no create surface exists for entity 'Device'" in errs[0]


def test_loud_when_surface_ambiguous():
    surfaces = {
        "a": _surface("a", "Device", SurfaceMode.CREATE),
        "b": _surface("b", "Device", SurfaceMode.CREATE),
    }
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.FORM_SUBMITTED)}
    scene, errs = _resolved_scene(
        _one_scene_rhythm(SceneSpec(name="s", story="ST-1")), surfaces, stories
    )
    assert scene.surface is None
    assert len(errs) == 1
    assert "surfaces serve entity 'Device'" in errs[0]


def test_loud_when_trigger_has_no_surface_mode():
    stories = {"ST-1": _story("ST-1", ["Device"], StoryTrigger.CRON_DAILY)}
    scene, errs = _resolved_scene(_one_scene_rhythm(SceneSpec(name="s", story="ST-1")), {}, stories)
    assert scene.surface is None
    assert len(errs) == 1
    assert "no surface can be derived" in errs[0]


def test_unknown_story_defers_to_linker():
    """A missing story is the linker's error to report — the resolver stays
    quiet (and derives nothing) rather than piling on a second error."""
    scene, errs = _resolved_scene(_one_scene_rhythm(SceneSpec(name="s", story="ST-404")), {}, {})
    assert scene.surface is None
    assert errs == []
