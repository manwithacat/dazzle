"""``display: auto`` — infer a region's form from its data shape (#1492, UX-maturity 1a).

Generalises the ad-hoc EX-047/#1082 ``aggregate -> SUMMARY`` promotion (and the
kanban auto-promotion) into one resolver, extended with the temporal rule. The
region's existing display verbs all stay; this only adds the *chooser*.

Opt-in and zero-blast-radius: only a region that declares ``display: auto`` routes
through here. Returns an UPPERCASE display mode matching ``workspace_renderer``'s
``DISPLAY_TEMPLATE_MAP`` convention; falls back to ``LIST`` when no strong signal
applies (so ``auto`` is never worse than the old default).

Rules, in priority order:
- aggregate + 2-D grouping → ``PIVOT_TABLE``
- aggregate + 1-D grouping → ``BAR_CHART``
- aggregate, no grouping (scalar) → ``SUMMARY`` (the existing EX-047 case)
- source entity has a state machine (ordered states) → ``KANBAN``
- source entity has a *meaningful* temporal field (not an auto ``created_at`` /
  ``updated_at`` timestamp) → ``TIMELINE``
- else → ``LIST``
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir.fields import FieldModifier, FieldTypeKind

_TEMPORAL_KINDS = {FieldTypeKind.DATE, FieldTypeKind.DATETIME}
_AUTO_TIMESTAMP = {FieldModifier.AUTO_ADD, FieldModifier.AUTO_UPDATE}


def resolve_region_display_mode(region: Any, entities_by_name: dict[str, Any]) -> str:
    """The single dispatch decision for a region's concrete display mode.

    Returns an UPPERCASE mode matching ``workspace_renderer``'s
    ``DISPLAY_TEMPLATE_MAP`` convention. The form is inferred from the data
    shape (via :func:`resolve_auto_display`) when either:

    - the author wrote ``display: auto`` (explicit opt-in, #1492), or
    - the author wrote no ``display:`` at all (``display_unset`` — the #1492
      default-flip; raw default ``LIST`` that no one chose).

    An *explicit* ``display: list`` (or any other concrete verb) is authoritative
    and returned unchanged — the resolver never overrides an author's choice.
    This subsumes the prior ad-hoc ``unset aggregate -> SUMMARY`` promotion, since
    :func:`resolve_auto_display` returns ``SUMMARY`` for that shape.
    """
    raw: Any = getattr(region, "display", None)
    mode = (raw.value if hasattr(raw, "value") else str(raw)).upper()
    if mode == "AUTO" or (mode == "LIST" and getattr(region, "display_unset", False)):
        return resolve_auto_display(region, entities_by_name)
    return mode


def resolve_auto_display(region: Any, entities_by_name: dict[str, Any]) -> str:
    """Infer the concrete display mode for a ``display: auto`` region."""
    aggregates = getattr(region, "aggregates", None) or {}
    if aggregates:
        dims = _group_dims(region)
        if dims >= 2:
            return "PIVOT_TABLE"
        if dims == 1:
            return "BAR_CHART"
        return "SUMMARY"

    entity = entities_by_name.get(getattr(region, "source", "") or "")
    if entity is not None:
        if getattr(entity, "state_machine", None) is not None:
            return "KANBAN"
        if _has_meaningful_temporal(entity):
            return "TIMELINE"
    return "LIST"


def _group_dims(region: Any) -> int:
    dims = getattr(region, "group_by_dims", None)
    if dims:
        return len(dims)
    return 1 if getattr(region, "group_by", None) else 0


def _has_meaningful_temporal(entity: Any) -> bool:
    """A date/datetime field that isn't an auto created/updated timestamp."""
    for field in getattr(entity, "fields", None) or []:
        kind = getattr(getattr(field, "type", None), "kind", None)
        if kind not in _TEMPORAL_KINDS:
            continue
        if _AUTO_TIMESTAMP & set(getattr(field, "modifiers", None) or []):
            continue
        return True
    return False
