"""Widget annotation relevance rules for capability discovery.

Scans create/edit surfaces for fields with widget-capable types but no
``widget=`` annotation, returning Relevance items for each match.
"""

import re
from typing import Any

from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec

from .models import Relevance

# Modes where widget suggestions are meaningful
_EDIT_MODES = {SurfaceMode.CREATE, SurfaceMode.EDIT}

# Name patterns for widget heuristics (compiled once)
_TAGS_RE = re.compile(r"tag|label|keyword", re.IGNORECASE)
_COLOR_RE = re.compile(r"color", re.IGNORECASE)
_SLIDER_RE = re.compile(r"score|rating|priority|level", re.IGNORECASE)


def check_widget_relevance(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
) -> list[Relevance]:
    """Return Relevance items for fields that would benefit from a widget annotation.

    Only fires for ``mode: create`` and ``mode: edit`` surfaces.  For each
    surface element that has no ``widget`` key in its options the corresponding
    entity field is looked up and tested against the rule table below:

    * ``text`` → ``widget=rich_text``
    * ``ref`` (no source) → ``widget=combobox``
    * ``str`` name matches *tag|label|keyword* → ``widget=tags``
    * ``date`` / ``datetime`` → ``widget=picker``
    * ``str(7)`` name matches *color* → ``widget=color``
    * ``int`` name matches *score|rating|priority|level* → ``widget=slider``

    Args:
        entities: List of EntitySpec objects.
        surfaces: List of SurfaceSpec objects.

    Returns:
        A list of Relevance instances, one per matching (surface, field) pair.
    """
    # Build entity lookup: name → EntitySpec
    entity_map = {e.name: e for e in entities}

    results: list[Relevance] = []

    for surface in surfaces:
        if surface.mode not in _EDIT_MODES:
            continue

        if not surface.entity_ref:
            continue

        entity = entity_map.get(surface.entity_ref)
        if entity is None:
            continue

        for section in surface.sections:
            for element in section.elements:
                # Skip if widget already annotated
                if "widget" in element.options:
                    continue

                field = entity.get_field(element.field_name)
                if field is None:
                    continue

                relevance = _match_rules(field, element.options, surface.name)
                if relevance is not None:
                    results.append(relevance)

    return results


def _match_rules(
    field: FieldSpec,
    options: dict[str, Any],
    surface_name: str,
) -> Relevance | None:
    """Apply widget rules to a single field and return a Relevance or None."""
    kind = field.type.kind
    name = field.name

    # text → rich_text
    if kind == FieldTypeKind.TEXT:
        return _make(name, kind, surface_name, "widget=rich_text", "widget_rich_text")

    # ref, no source → combobox
    if kind == FieldTypeKind.REF and "source" not in options:
        return _make(name, kind, surface_name, "widget=combobox", "widget_combobox")

    # date / datetime → picker
    if kind in (FieldTypeKind.DATE, FieldTypeKind.DATETIME):
        return _make(name, kind, surface_name, "widget=picker", "widget_picker")

    # str(7) + color name → color picker
    if kind == FieldTypeKind.STR and field.type.max_length == 7 and _COLOR_RE.search(name):
        return _make(name, kind, surface_name, "widget=color", "widget_color")

    # str + tag/label/keyword name → tags
    if kind == FieldTypeKind.STR and _TAGS_RE.search(name):
        return _make(name, kind, surface_name, "widget=tags", "widget_tags")

    # int + score/rating/priority/level name → slider
    if kind == FieldTypeKind.INT and _SLIDER_RE.search(name):
        return _make(name, kind, surface_name, "widget=slider", "widget_slider")

    return None


def _make(
    field_name: str,
    kind: FieldTypeKind,
    surface_name: str,
    capability: str,
    kg_key: str,
) -> Relevance:
    return Relevance(
        context=f"field '{field_name}' ({kind}) on surface '{surface_name}'",
        capability=capability,
        category="widget",
        examples=[],
        kg_entity=f"capability:{kg_key}",
    )
