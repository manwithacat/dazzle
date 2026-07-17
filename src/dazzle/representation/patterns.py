"""Named representation pattern catalogue (#1617).

Agents and tools reason in these IDs — not free-text “polymorphism”.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class PatternId(StrEnum):
    """Stable pattern identifiers for decide / classify / prove / docs."""

    EXPLICIT_REF = "rel.explicit_ref"
    EXCLUSIVE_FKS = "rel.exclusive_fks"
    TPT_SUBTYPE = "rel.tpt_subtype"
    POLY_REF = "rel.poly_ref"
    JSON_EXTENSION = "rel.json_extension"
    STI = "rel.sti"
    EAV = "rel.eav"
    HOST_EXTENSION = "rel.host_extension"


# Full catalogue: when / not when / integrity / render / docs anchors.
PATTERN_CATALOGUE: dict[str, dict[str, Any]] = {
    PatternId.EXPLICIT_REF: {
        "id": PatternId.EXPLICIT_REF,
        "layer": "default",
        "summary": "Single parent type via typed `ref Entity`",
        "when": ["Exactly one parent entity type", "FK graph and scope must be static"],
        "not_when": ["2–4 alternative parents", "Shared child of many parents"],
        "dsl": "field: ref Parent",
        "integrity": ["optional required: on the ref", "orphan checks via dazzle db verify"],
        "render": ["open: Parent via field", "format_cell / related columns"],
        "rbac": ["scope along the FK path"],
        "docs": ["data-representation#default-opinionated", "entities#relationships"],
    },
    PatternId.EXCLUSIVE_FKS: {
        "id": PatternId.EXCLUSIVE_FKS,
        "layer": "hatch",
        "summary": "Sparse exclusive nullable FKs (product poly, not poly_ref)",
        "when": [
            "2–4 alternative parent types",
            "Journey hub needs first non-null open hop",
            "Not true ISA (no mixed-kind list of the parents themselves)",
        ],
        "not_when": [
            "Shared Comment/Attachment pointing at many parent kinds → poly_ref",
            "True ISA with shared base columns → subtype_of",
        ],
        "dsl": (
            "nullable refs + invariant: a != null or b != null [or c…] "
            "+ open: first_non_null(a, b, c)"
        ),
        "integrity": [
            "at-least-one-anchor invariant",
            "dazzle db verify → unanchored + exclusive_conflict",
        ],
        "render": ["open: first_non_null(...)", "never host multi-target open patch"],
        "rbac": ["scope each ref path or scope after hop entity is chosen"],
        "docs": ["data-representation#exclusive-fks-integrity-1617-phase-1"],
    },
    PatternId.TPT_SUBTYPE: {
        "id": PatternId.TPT_SUBTYPE,
        "layer": "hatch",
        "summary": "Table-per-type true ISA via subtype_of:",
        "when": [
            "True IS-A",
            "Subtype-specific NOT NULL columns",
            "Need polymorphic mixed-kind lists of the base",
        ],
        "not_when": ["Variants never listed together", "Lifecycle states (use state machine)"],
        "dsl": "entity Child: subtype_of: Base",
        "integrity": ["linker subtype rules", "id not redeclared on child"],
        "render": ["subtype_panel:", "base list surfaces"],
        "rbac": ["compose base + child grants"],
        "docs": ["data-representation", "ADR-0026"],
        "counter_prior": "subtype_polymorphism_default",
    },
    PatternId.POLY_REF: {
        "id": PatternId.POLY_REF,
        "layer": "hatch",
        "summary": "Typed poly_ref name [T1, T2] with closed targets + scope selector",
        "when": [
            "Shared child points at many parent kinds (Comment, Attachment, Audit, AIJob)",
            "Four-question interrogation for poly fails (≈5% of proposals)",
        ],
        "not_when": [
            "2–4 exclusive parents on one row → exclusive_fks",
            "Hand-rolled subject_type + subject_id without poly_ref",
        ],
        "dsl": "subject: poly_ref [A, B]  + scope subject[A].path",
        "integrity": ["closed targets uuid-pk", "no bare subject.x without selector"],
        "render": ["resolve via type column", "list/detail via target display"],
        "rbac": ["name[Type].path scope; dazzle db explain-scope"],
        "docs": ["counter-priors/polymorphic-associations", "ADR-0042"],
        "counter_prior": "polymorphic_associations",
    },
    PatternId.JSON_EXTENSION: {
        "id": PatternId.JSON_EXTENSION,
        "layer": "hatch",
        "summary": "Core columns normalized; tenant/feature bag in json/JSONB",
        "when": ["Tenant-variable shape", "Feature flags / extension payload without schema churn"],
        "not_when": ["Business keys only in JSON (no query/FK integrity)", "Unbounded growth dump"],
        "dsl": "extensions: json  # core FKs stay typed columns",
        "integrity": ["keep identity/FKs outside JSON", "optional GIN later (Phase 2)"],
        "render": [
            "do not dump raw JSON on every list column",
            "dedicated extension widgets later",
        ],
        "rbac": ["scope via core entity FKs, not JSON paths (v1)"],
        "docs": ["data-representation#escape-hatch-ladder"],
    },
    PatternId.STI: {
        "id": PatternId.STI,
        "layer": "discouraged",
        "summary": "Single table + type discriminator + sparse subtype columns",
        "when": ["Rare; related subtypes with very sparse columns"],
        "not_when": ["Prefer TPT or exclusive FKs or separate entities first"],
        "dsl": "# no first-class STI keyword — smell, not product",
        "integrity": ["lint when overused"],
        "render": ["ad-hoc"],
        "rbac": ["fragile"],
        "docs": ["data-representation#escape-hatch-ladder"],
    },
    PatternId.EAV: {
        "id": PatternId.EAV,
        "layer": "last_resort",
        "summary": "Classic EAV joins — prefer JSONB projections instead",
        "when": ["Almost never in framework core"],
        "not_when": ["Custom fields → json_extension"],
        "dsl": "# not a product hatch",
        "integrity": ["n/a"],
        "render": ["n/a"],
        "rbac": ["n/a"],
        "docs": ["data-representation#escape-hatch-ladder"],
    },
    PatternId.HOST_EXTENSION: {
        "id": PatternId.HOST_EXTENSION,
        "layer": "dual_lock",
        "summary": "Host owns extension schema; framework owns core",
        "when": ["Dual-lock vertical needs shape outside DSL product surface"],
        "not_when": ["Journey open-via / exclusive parents — use framework hatches"],
        "dsl": "# host services/routes; document boundary",
        "integrity": ["host responsibility"],
        "render": ["optional # dazzle:returns fragment"],
        "rbac": ["host + framework compose carefully"],
        "docs": ["data-representation#escape-hatch-ladder"],
    },
}


def list_patterns() -> list[dict[str, Any]]:
    """Return catalogue rows in stable ID order."""
    return [PATTERN_CATALOGUE[pid] for pid in PatternId]
