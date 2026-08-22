"""Mermaid ER source for ``display: diagram`` regions (oral #166)."""

from __future__ import annotations

from typing import Any


def compute_diagram_data(app_spec: Any) -> str:
    """Generate a Mermaid ``erDiagram`` from AppSpec domain entities.

    Live HTTP typed-primitive ``display: diagram`` used to dump empty
    "No entity relationships" while Device/Tester refs existed, because
    it never called the page compile-time builder. Leftover ``zzz`` is
    not an entity and is not invented.
    """
    if app_spec is None:
        return ""
    domain = getattr(app_spec, "domain", None)
    if domain is None:
        return ""
    lines = ["erDiagram"]
    entities = getattr(domain, "entities", [])
    entity_names = {e.name for e in entities}
    for entity in entities:
        if getattr(entity, "domain", "") == "platform":
            continue
        lines.append(f"    {entity.name} {{")
        for field in entity.fields[:8]:
            kind = getattr(field.type, "kind", "str")
            kind_str = kind.value if hasattr(kind, "value") else str(kind)
            lines.append(f"        {kind_str} {field.name}")
        if len(entity.fields) > 8:
            lines.append(f"        string _plus_{len(entity.fields) - 8}_more")
        lines.append("    }")
    for entity in entities:
        if getattr(entity, "domain", "") == "platform":
            continue
        for field in entity.fields:
            ref = getattr(field.type, "ref_entity", None)
            if ref and ref in entity_names:
                lines.append(f"    {entity.name} }}o--|| {ref} : {field.name}")
    return "\n".join(lines)
