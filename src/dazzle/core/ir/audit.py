"""User-visible audit trail IR types (#956 cycle 1).

Distinct from the compliance pipeline: that captures evidence for
ISO 27001 / SOC 2 audits. This primitive captures *user-visible*
"who changed this row, when, and from what to what" history that
inventory / contract / CMS UIs typically need.

Cycle 1 ships the parsed surface. Cycle 2 auto-generates an
``AuditEntry`` entity (mirrors the AIJob / JobRun pattern). Cycle 3
adds repository hooks to capture diffs on update; cycle 4 renders a
``history`` region on detail surfaces; cycle 5 wires RBAC via
``show_to``; cycle 6 connects retention to the background-job
primitive (#953) for sweep.

DSL shape::

    audit on Manuscript:
      track: status, source_pdf, marking_result
      show_to: persona(teacher, admin)
      retention: 90d
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuditShowTo(BaseModel):
    """Who is allowed to see the audit history on the entity's detail
    surface. Cycle 5 wires this against the RBAC matrix; cycle 1 just
    captures the declaration.

    Attributes:
        kind: ``"persona"`` (cycle-1 only form) — list of persona names
            allowed to see history. Future kinds: ``"role"``, ``"all"``.
        personas: When ``kind == "persona"``, the persona names.
    """

    kind: str = "persona"
    personas: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class AuditSpec(BaseModel):
    """Audit-trail definition for a single entity (#956).

    Attributes:
        entity: Entity name being audited (e.g. "Manuscript").
        track: List of field names to capture old/new values for. Empty
            list means "track every field" — picked up by cycle 3's
            repository hook.
        show_to: Who can see the rendered history region. Cycle-5 RBAC
            integration; cycle 1 just captures.
        retention_days: How long to keep audit entries. 0 means "keep
            forever". Cycle-6 retention sweep reads this.
    """

    entity: str
    track: list[str] = Field(default_factory=list)
    show_to: AuditShowTo = Field(default_factory=AuditShowTo)
    retention_days: int = Field(default=0, ge=0, le=36_500)

    model_config = ConfigDict(frozen=True)


# =============================================================================
# AuditEntry System Entity Builder (#956 cycle 2)
# =============================================================================

# Field definitions for the auto-generated AuditEntry entity. Each
# tuple: ``(name, type_kind, modifiers, default)``. The shape mirrors
# the AIJob convention so the linker can build it via the shared
# ``_parse_field_type`` / ``_MODIFIER_MAP`` helpers.
#
# `before_value` and `after_value` are stored as text — JSON-encoded
# at write time by cycle-3's repository hook so any field type
# (string, number, datetime, FK uuid) can round-trip without a
# polymorphic column. Cycle-4's history region decodes for display.
AUDIT_ENTRY_FIELDS: list[tuple[str, str, list[str], str | None]] = [
    ("id", "uuid", ["pk"], None),
    ("entity_type", "str(200)", ["required"], None),
    ("entity_id", "str(200)", ["required"], None),
    ("field_name", "str(200)", ["required"], None),
    ("operation", "enum[create,update,delete]", ["required"], "update"),
    ("before_value", "text", [], None),
    ("after_value", "text", [], None),
    ("by_user_id", "str(200)", [], None),
    ("at", "datetime", ["required"], "now"),
]
