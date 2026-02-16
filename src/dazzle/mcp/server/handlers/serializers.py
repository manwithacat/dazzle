"""
Canonical serialization helpers for DSL IR types.

Provides consistent JSON-serializable representations of StorySpec,
TestDesignSpec, EntitySpec, and SurfaceSpec used across all MCP handlers.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Story serialization
# =============================================================================


_STORY_SUMMARY_FIELDS = {"story_id", "title", "actor", "status", "scope"}

_STORY_FULL_FIELDS = {
    "story_id",
    "title",
    "actor",
    "trigger",
    "scope",
    "preconditions",
    "happy_path_outcome",
    "side_effects",
    "constraints",
    "variants",
    "status",
    "created_at",
    "accepted_at",
}


def serialize_story_summary(story: StorySpec) -> dict[str, Any]:
    """Compact story summary: ID, title, actor, status, scope.

    Used by default in list/propose responses to reduce context window usage.
    """
    return story.model_dump(mode="json", include=_STORY_SUMMARY_FIELDS)


def serialize_story(story: StorySpec) -> dict[str, Any]:
    """Full story serialization — the canonical format for story responses."""
    return story.model_dump(mode="json", include=_STORY_FULL_FIELDS)


# =============================================================================
# Test design serialization
# =============================================================================


_TD_SUMMARY_FIELDS = {"test_id", "title", "persona", "status"}

_TD_FULL_FIELDS = {
    "test_id",
    "title",
    "description",
    "persona",
    "scenario",
    "trigger",
    "steps",
    "expected_outcomes",
    "entities",
    "surfaces",
    "tags",
    "status",
    "implementation_path",
    "notes",
}


def serialize_test_design_summary(td: Any) -> dict[str, Any]:
    """Compact test design summary: ID, title, persona, status."""
    result: dict[str, Any] = td.model_dump(mode="json", include=_TD_SUMMARY_FIELDS)
    return result


def serialize_test_design(td: Any) -> dict[str, Any]:
    """Full test design serialization with steps, outcomes, and metadata."""
    result: dict[str, Any] = td.model_dump(mode="json", include=_TD_FULL_FIELDS)
    return result


# =============================================================================
# Entity serialization
# =============================================================================


def serialize_entity_summary(entity: Any) -> dict[str, Any]:
    """Compact entity summary: name, title, field count, state machine presence."""
    info: dict[str, Any] = {
        "name": entity.name,
        "title": entity.title,
        "field_count": len(entity.fields),
        "has_state_machine": entity.state_machine is not None,
    }
    if entity.state_machine:
        info["states"] = entity.state_machine.states
    return info


def serialize_entity_detail(entity: Any) -> dict[str, Any]:
    """Full entity detail: all fields, state machine with transitions."""
    info: dict[str, Any] = {
        "name": entity.name,
        "title": entity.title,
        "fields": [
            {
                "name": f.name,
                "type": str(f.type.kind.value) if f.type.kind else str(f.type),
                "required": f.is_required,
            }
            for f in entity.fields
        ],
    }
    if entity.state_machine:
        sm = entity.state_machine
        info["state_machine"] = {
            "field": sm.status_field,
            "states": sm.states,
            "transitions": [
                {
                    "from": t.from_state,
                    "to": t.to_state,
                    "trigger": t.trigger.value if t.trigger else None,
                }
                for t in sm.transitions
            ],
        }
    return info


# =============================================================================
# Surface / UX serialization
# =============================================================================


def serialize_ux_summary(ux: Any) -> dict[str, Any]:
    """Compact UX spec summary for surface serialization."""
    info: dict[str, Any] = {}
    if ux.sort:
        info["sort"] = [str(s) for s in ux.sort]
    if ux.filter:
        info["filter"] = list(ux.filter)
    if ux.search:
        info["search"] = list(ux.search)
    if ux.empty_message:
        info["empty_message"] = ux.empty_message
    if ux.attention_signals:
        info["attention_signals"] = len(ux.attention_signals)
    if ux.persona_variants:
        info["personas"] = [p.persona for p in ux.persona_variants]
    return info


def serialize_surface_summary(surface: Any) -> dict[str, Any]:
    """Compact surface summary: name, title, entity, mode."""
    info: dict[str, Any] = {
        "name": surface.name,
        "title": surface.title,
        "entity": surface.entity_ref,
        "mode": surface.mode.value if surface.mode else None,
    }
    if hasattr(surface, "ux") and surface.ux:
        info["ux"] = serialize_ux_summary(surface.ux)
    return info


def serialize_surface_detail(surface: Any) -> dict[str, Any]:
    """Full surface detail: includes sections, fields, and UX metadata."""
    info: dict[str, Any] = {
        "name": surface.name,
        "title": surface.title,
        "entity": surface.entity_ref,
        "mode": surface.mode.value if surface.mode else None,
    }
    if hasattr(surface, "sections") and surface.sections:
        info["sections"] = [
            {
                "name": sec.name,
                "fields": [
                    {"name": f.name, "title": getattr(f, "title", f.name)}
                    for f in (sec.fields if hasattr(sec, "fields") else [])
                ],
            }
            for sec in surface.sections
        ]
    if hasattr(surface, "ux") and surface.ux:
        info["ux"] = serialize_ux_summary(surface.ux)
    return info


# =============================================================================
# Generic response helpers
# =============================================================================


def list_response(items: list[Any], **extra: Any) -> str:
    """Build standard JSON list response with count."""
    payload: dict[str, Any] = {"count": len(items), "items": items}
    payload.update(extra)
    return json.dumps(payload, indent=2)


def success_response(data: Any, **extra: Any) -> str:
    """Build standard JSON success response."""
    payload: dict[str, Any] = {"result": data}
    payload.update(extra)
    return json.dumps(payload, indent=2)
