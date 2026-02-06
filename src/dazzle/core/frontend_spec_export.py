"""
Frontend specification export for DAZZLE.

Generates a framework-agnostic frontend specification from DSL data,
suitable for React/Vue/etc. handoff. Includes TypeScript interfaces,
route maps, component inventories, state machines, API contracts,
workspace layouts, and test acceptance criteria.
"""

from __future__ import annotations

import json
from typing import Any

from .ir.appspec import AppSpec
from .ir.fields import FieldModifier, FieldTypeKind
from .ir.sitespec import SiteSpec
from .ir.stories import StorySpec
from .ir.test_design import TestDesignSpec

# FieldTypeKind → TypeScript type string
FIELD_TYPE_MAP: dict[str, str] = {
    FieldTypeKind.UUID: "string",
    FieldTypeKind.STR: "string",
    FieldTypeKind.TEXT: "string",
    FieldTypeKind.EMAIL: "string",
    FieldTypeKind.URL: "string",
    FieldTypeKind.TIMEZONE: "string",
    FieldTypeKind.INT: "number",
    FieldTypeKind.DECIMAL: "number",
    FieldTypeKind.MONEY: "number",
    FieldTypeKind.BOOL: "boolean",
    FieldTypeKind.DATE: "Date",
    FieldTypeKind.DATETIME: "Date",
    FieldTypeKind.JSON: "Record<string, unknown>",
    FieldTypeKind.FILE: "string",
    FieldTypeKind.REF: "string",
    FieldTypeKind.HAS_MANY: "string[]",
    FieldTypeKind.HAS_ONE: "string",
    FieldTypeKind.BELONGS_TO: "string",
    FieldTypeKind.EMBEDS: "Record<string, unknown>",
}

ALL_SECTIONS = [
    "typescript_interfaces",
    "route_map",
    "component_inventory",
    "state_machines",
    "api_contract",
    "workspace_layouts",
    "test_criteria",
]


def export_frontend_spec(
    appspec: AppSpec,
    sitespec: SiteSpec | None,
    stories: list[StorySpec],
    test_designs: list[TestDesignSpec],
    fmt: str = "markdown",
    sections: list[str] | None = None,
    entities_filter: list[str] | None = None,
) -> str:
    """Export a framework-agnostic frontend specification.

    Args:
        appspec: Linked application specification.
        sitespec: Site specification (may be None).
        stories: Story specifications.
        test_designs: Test design specifications.
        fmt: Output format - "markdown" or "json".
        sections: Which sections to include (None = all).
        entities_filter: Filter to specific entity names (None = all).

    Returns:
        Formatted specification string.
    """
    active_sections = sections if sections else ALL_SECTIONS
    data: dict[str, Any] = {}

    if "typescript_interfaces" in active_sections:
        data["typescript_interfaces"] = _build_typescript_interfaces(appspec, entities_filter)
    if "route_map" in active_sections:
        data["route_map"] = _build_route_map(appspec, sitespec)
    if "component_inventory" in active_sections:
        data["component_inventory"] = _build_component_inventory(appspec, entities_filter)
    if "state_machines" in active_sections:
        data["state_machines"] = _build_state_machines(appspec, entities_filter)
    if "api_contract" in active_sections:
        data["api_contract"] = _build_api_contract(appspec, entities_filter)
    if "workspace_layouts" in active_sections:
        data["workspace_layouts"] = _build_workspace_layouts(appspec, sitespec)
    if "test_criteria" in active_sections:
        data["test_criteria"] = _build_test_criteria(stories, test_designs, entities_filter)

    if fmt == "json":
        return _format_json(data)
    return _format_markdown(data, appspec)


# =============================================================================
# Section Builders
# =============================================================================


def _filter_entities(appspec: AppSpec, entities_filter: list[str] | None) -> list[Any]:
    """Return filtered entity list."""
    if entities_filter:
        return [e for e in appspec.domain.entities if e.name in entities_filter]
    return list(appspec.domain.entities)


def _build_typescript_interfaces(
    appspec: AppSpec, entities_filter: list[str] | None
) -> list[dict[str, Any]]:
    """Build TypeScript interface definitions for entities."""
    result = []
    for entity in _filter_entities(appspec, entities_filter):
        fields = []
        for f in entity.fields:
            ts_type = _resolve_ts_type(f)
            comments = []
            if f.is_primary_key:
                comments.append("pk")
            if f.is_required:
                comments.append("required")
            if f.type.readonly:
                comments.append("readonly")
            if FieldModifier.AUTO_ADD in f.modifiers:
                comments.append("auto_add")
            if FieldModifier.AUTO_UPDATE in f.modifiers:
                comments.append("auto_update")

            fields.append(
                {
                    "name": f.name,
                    "ts_type": ts_type,
                    "optional": not f.is_required and not f.is_primary_key,
                    "comments": comments,
                }
            )

        # Add state machine status as union type if present
        interface_data: dict[str, Any] = {
            "name": entity.name,
            "title": entity.title,
            "fields": fields,
        }
        if entity.state_machine:
            interface_data["status_union"] = {
                "field": entity.state_machine.status_field,
                "states": list(entity.state_machine.states),
            }
        result.append(interface_data)
    return result


def _resolve_ts_type(field: Any) -> str:
    """Resolve a field to its TypeScript type string."""
    kind = field.type.kind

    # Enum → union literal
    if kind == FieldTypeKind.ENUM and field.type.enum_values:
        return " | ".join(f'"{v}"' for v in field.type.enum_values)

    return FIELD_TYPE_MAP.get(kind, "unknown")


def _build_route_map(appspec: AppSpec, sitespec: SiteSpec | None) -> list[dict[str, Any]]:
    """Derive route map from workspaces and surfaces."""
    routes: list[dict[str, Any]] = []

    # Derive app routes from surfaces grouped by entity
    entity_surfaces: dict[str, list[Any]] = {}
    for surface in appspec.surfaces:
        entity_name = surface.entity_ref or "general"
        entity_surfaces.setdefault(entity_name, []).append(surface)

    for entity_name, surfaces in entity_surfaces.items():
        slug = _pluralize(entity_name.lower())
        # Find workspace that contains this entity
        workspace_slug = _find_workspace_for_entity(appspec, entity_name)
        base = f"/{workspace_slug}/{slug}" if workspace_slug else f"/{slug}"

        for surface in surfaces:
            mode = surface.mode.value
            access = _extract_surface_access(surface)

            if mode == "list":
                routes.append(
                    {
                        "path": base,
                        "surface": surface.name,
                        "mode": mode,
                        "entity": entity_name,
                        "access": access,
                    }
                )
            elif mode == "view":
                routes.append(
                    {
                        "path": f"{base}/:id",
                        "surface": surface.name,
                        "mode": "detail",
                        "entity": entity_name,
                        "access": access,
                    }
                )
            elif mode == "create":
                routes.append(
                    {
                        "path": f"{base}/new",
                        "surface": surface.name,
                        "mode": mode,
                        "entity": entity_name,
                        "access": access,
                    }
                )
            elif mode == "edit":
                routes.append(
                    {
                        "path": f"{base}/:id/edit",
                        "surface": surface.name,
                        "mode": mode,
                        "entity": entity_name,
                        "access": access,
                    }
                )
            else:
                routes.append(
                    {
                        "path": f"{base}/{surface.name}",
                        "surface": surface.name,
                        "mode": mode,
                        "entity": entity_name,
                        "access": access,
                    }
                )

    # Add sitespec public routes
    if sitespec:
        for page in sitespec.pages:
            routes.append(
                {
                    "path": page.route,
                    "surface": None,
                    "mode": "page",
                    "entity": None,
                    "access": {"public": True},
                }
            )

    return routes


def _find_workspace_for_entity(appspec: AppSpec, entity_name: str) -> str | None:
    """Find the workspace that contains regions referencing this entity."""
    for ws in appspec.workspaces:
        for region in ws.regions:
            if region.source == entity_name:
                return ws.name
    return None


def _extract_surface_access(surface: Any) -> dict[str, Any]:
    """Extract access control info from a surface."""
    if surface.access:
        return {
            "require_auth": surface.access.require_auth,
            "allow_personas": surface.access.allow_personas,
        }
    return {"require_auth": False, "allow_personas": []}


def _pluralize(name: str) -> str:
    """Naive pluralization for URL slugs."""
    if name.endswith("s"):
        return name + "es"
    if name.endswith("y") and name[-2:] not in ("ay", "ey", "oy", "uy"):
        return name[:-1] + "ies"
    return name + "s"


def _build_component_inventory(
    appspec: AppSpec, entities_filter: list[str] | None
) -> list[dict[str, Any]]:
    """Build component inventory from surfaces."""
    result = []
    for surface in appspec.surfaces:
        if entities_filter and surface.entity_ref and surface.entity_ref not in entities_filter:
            continue

        sections = []
        for section in surface.sections:
            fields = []
            for element in section.elements:
                field_info: dict[str, Any] = {
                    "name": element.field_name,
                    "label": element.label,
                }
                if element.options:
                    field_info["options"] = element.options
                # Resolve field type from entity
                if surface.entity_ref:
                    entity = appspec.get_entity(surface.entity_ref)
                    if entity:
                        for ef in entity.fields:
                            if ef.name == element.field_name:
                                field_info["type"] = ef.type.kind.value
                                break
                fields.append(field_info)
            sections.append(
                {
                    "name": section.name,
                    "title": section.title,
                    "fields": fields,
                }
            )

        component: dict[str, Any] = {
            "name": surface.name,
            "title": surface.title,
            "mode": surface.mode.value,
            "entity": surface.entity_ref,
            "sections": sections,
        }
        if hasattr(surface, "ux") and surface.ux:
            ux = surface.ux
            ux_info: dict[str, Any] = {}
            if ux.sort:
                ux_info["sort"] = [str(s) for s in ux.sort]
            if getattr(ux, "filter", None):
                ux_info["filter"] = list(ux.filter)
            if ux.search:
                ux_info["search"] = list(ux.search)
            if ux.empty_message:
                ux_info["empty_message"] = ux.empty_message
            if ux.attention_signals:
                ux_info["attention_signals"] = len(ux.attention_signals)
            if ux.persona_variants:
                ux_info["personas"] = [p.persona for p in ux.persona_variants]
            if ux_info:
                component["ux"] = ux_info
        result.append(component)
    return result


def _build_state_machines(
    appspec: AppSpec, entities_filter: list[str] | None
) -> list[dict[str, Any]]:
    """Build Mermaid state diagrams for entities with state machines."""
    result = []
    for entity in _filter_entities(appspec, entities_filter):
        if not entity.state_machine:
            continue

        sm = entity.state_machine
        lines = ["stateDiagram-v2"]
        # Initial state
        if sm.states:
            lines.append(f"    [*] --> {sm.states[0]}")

        for t in sm.transitions:
            label_parts = []
            for g in t.guards:
                if g.requires_field:
                    label_parts.append(f"requires {g.requires_field}")
                elif g.requires_role:
                    label_parts.append(f"role({g.requires_role})")
                elif g.condition:
                    label_parts.append(g.condition)

            from_state = t.from_state if t.from_state != "*" else "[*]"
            label = " / ".join(label_parts) if label_parts else ""
            if label:
                lines.append(f"    {from_state} --> {t.to_state} : {label}")
            else:
                lines.append(f"    {from_state} --> {t.to_state}")

        result.append(
            {
                "entity": entity.name,
                "status_field": sm.status_field,
                "states": list(sm.states),
                "mermaid": "\n".join(lines),
            }
        )
    return result


def _build_api_contract(
    appspec: AppSpec, entities_filter: list[str] | None
) -> list[dict[str, Any]]:
    """Infer CRUD API endpoints from entities."""
    result = []
    for entity in _filter_entities(appspec, entities_filter):
        slug = _pluralize(entity.name.lower())
        base = f"/api/{slug}"
        endpoints = [
            {
                "method": "GET",
                "path": base,
                "description": f"List {entity.name} records",
                "response": f"{entity.name}[]",
            },
            {
                "method": "POST",
                "path": base,
                "description": f"Create {entity.name}",
                "request": entity.name,
                "response": entity.name,
            },
            {
                "method": "GET",
                "path": f"{base}/{{id}}",
                "description": f"Get {entity.name} by ID",
                "response": entity.name,
            },
            {
                "method": "PUT",
                "path": f"{base}/{{id}}",
                "description": f"Update {entity.name}",
                "request": entity.name,
                "response": entity.name,
            },
            {
                "method": "DELETE",
                "path": f"{base}/{{id}}",
                "description": f"Delete {entity.name}",
                "response": "void",
            },
        ]

        # Add state transition endpoints
        if entity.state_machine:
            endpoints.append(
                {
                    "method": "POST",
                    "path": f"{base}/{{id}}/transitions",
                    "description": f"Trigger state transition on {entity.name}",
                    "request": '{"to_state": string}',
                    "response": entity.name,
                }
            )

        result.append(
            {
                "entity": entity.name,
                "base_path": base,
                "endpoints": endpoints,
            }
        )
    return result


def _build_workspace_layouts(appspec: AppSpec, sitespec: SiteSpec | None) -> list[dict[str, Any]]:
    """Build workspace layout descriptions."""
    result = []
    for ws in appspec.workspaces:
        access = None
        if ws.access:
            access = {
                "level": ws.access.level.value,
                "allow_personas": ws.access.allow_personas,
            }

        regions = []
        for region in ws.regions:
            regions.append(
                {
                    "name": region.name,
                    "source": region.source,
                    "display": region.display.value,
                    "filter": str(region.filter) if region.filter else None,
                    "limit": region.limit,
                }
            )

        result.append(
            {
                "name": ws.name,
                "title": ws.title,
                "purpose": ws.purpose,
                "stage": ws.stage,
                "access": access,
                "regions": regions,
            }
        )

    # Add sitespec navigation structure
    if sitespec:
        nav_entry: dict[str, Any] = {
            "name": "_site_navigation",
            "title": "Site Navigation",
            "purpose": "Public site shell navigation",
            "stage": None,
            "access": {"level": "public", "allow_personas": []},
            "regions": [],
            "navigation": {
                "public": [{"label": n.label, "href": n.href} for n in sitespec.layout.nav.public],
                "authenticated": [
                    {"label": n.label, "href": n.href} for n in sitespec.layout.nav.authenticated
                ],
            },
        }
        result.append(nav_entry)

    return result


def _build_test_criteria(
    stories: list[StorySpec],
    test_designs: list[TestDesignSpec],
    entities_filter: list[str] | None,
) -> list[dict[str, Any]]:
    """Build test acceptance criteria from stories and test designs."""
    result: list[dict[str, Any]] = []

    # From stories
    for story in stories:
        if entities_filter and not any(e in entities_filter for e in story.scope):
            continue

        criteria: dict[str, Any] = {
            "source": "story",
            "id": story.story_id,
            "title": story.title,
            "actor": story.actor,
            "scope": list(story.scope),
        }

        # given/when/then
        if story.given:
            criteria["given"] = [c.expression for c in story.given]
        if story.when:
            criteria["when"] = [c.expression for c in story.when]
        if story.then:
            criteria["then"] = [c.expression for c in story.then]
        if story.constraints:
            criteria["constraints"] = list(story.constraints)

        result.append(criteria)

    # From test designs
    for td in test_designs:
        if entities_filter and not any(e in entities_filter for e in td.entities):
            continue

        result.append(
            {
                "source": "test_design",
                "id": td.test_id,
                "title": td.title,
                "persona": td.persona,
                "steps": [s.action for s in td.steps],
                "expected_outcomes": list(td.expected_outcomes),
                "entities": list(td.entities),
            }
        )

    return result


# =============================================================================
# Formatters
# =============================================================================


def _format_json(data: dict[str, Any]) -> str:
    """Format sections data as JSON."""
    return json.dumps(data, indent=2, default=str)


def _format_markdown(data: dict[str, Any], appspec: AppSpec) -> str:
    """Format sections data as Markdown."""
    lines: list[str] = []
    lines.append(f"# Frontend Specification: {appspec.title or appspec.name}")
    lines.append("")

    if "typescript_interfaces" in data:
        lines.append("## TypeScript Interfaces")
        lines.append("")
        for iface in data["typescript_interfaces"]:
            lines.append(f"### {iface['name']}")
            if iface.get("title"):
                lines.append(f"_{iface['title']}_")
            lines.append("")
            lines.append("```typescript")
            lines.append(f"interface {iface['name']} {{")
            for f in iface["fields"]:
                comment = ""
                if f["comments"]:
                    comment = f"  // {', '.join(f['comments'])}"
                optional = "?" if f["optional"] else ""
                lines.append(f"  {f['name']}{optional}: {f['ts_type']};{comment}")
            if iface.get("status_union"):
                su = iface["status_union"]
                union = " | ".join(f'"{s}"' for s in su["states"])
                lines.append(f"  // Status type: {su['field']}: {union}")
            lines.append("}")
            lines.append("```")
            lines.append("")

    if "route_map" in data:
        lines.append("## Route Map")
        lines.append("")
        lines.append("| Path | Surface | Mode | Entity | Auth |")
        lines.append("|------|---------|------|--------|------|")
        for r in data["route_map"]:
            auth = (
                "public"
                if r["access"].get("public")
                else (
                    ", ".join(r["access"].get("allow_personas", []))
                    or ("required" if r["access"].get("require_auth") else "none")
                )
            )
            surf = r["surface"] or "-"
            ent = r["entity"] or "-"
            lines.append(f"| `{r['path']}` | {surf} | {r['mode']} | {ent} | {auth} |")
        lines.append("")

    if "component_inventory" in data:
        lines.append("## Component Inventory")
        lines.append("")
        for comp in data["component_inventory"]:
            lines.append(f"### {comp['name']} ({comp['mode']})")
            if comp.get("title"):
                lines.append(f"_{comp['title']}_")
            if comp.get("entity"):
                lines.append(f"Entity: `{comp['entity']}`")
            lines.append("")
            for section in comp["sections"]:
                lines.append(f"**Section: {section['name']}**")
                if section.get("title"):
                    lines.append(f"_{section['title']}_")
                for field in section["fields"]:
                    type_str = f" ({field['type']})" if field.get("type") else ""
                    lines.append(f"- `{field['name']}`{type_str}: {field.get('label', '')}")
                lines.append("")

    if "state_machines" in data:
        lines.append("## State Machines")
        lines.append("")
        for sm in data["state_machines"]:
            lines.append(f"### {sm['entity']}")
            lines.append(f"Status field: `{sm['status_field']}`")
            lines.append(f"States: {', '.join(f'`{s}`' for s in sm['states'])}")
            lines.append("")
            lines.append("```mermaid")
            lines.append(sm["mermaid"])
            lines.append("```")
            lines.append("")

    if "api_contract" in data:
        lines.append("## API Contract")
        lines.append("")
        for contract in data["api_contract"]:
            lines.append(f"### {contract['entity']}")
            lines.append(f"Base path: `{contract['base_path']}`")
            lines.append("")
            lines.append("| Method | Path | Description | Request | Response |")
            lines.append("|--------|------|-------------|---------|----------|")
            for ep in contract["endpoints"]:
                req = ep.get("request", "-")
                resp = ep.get("response", "-")
                lines.append(
                    f"| {ep['method']} | `{ep['path']}` | {ep['description']} | {req} | {resp} |"
                )
            lines.append("")

    if "workspace_layouts" in data:
        lines.append("## Workspace Layouts")
        lines.append("")
        for ws in data["workspace_layouts"]:
            lines.append(f"### {ws['name']}")
            if ws.get("title"):
                lines.append(f"_{ws['title']}_")
            if ws.get("purpose"):
                lines.append(f"Purpose: {ws['purpose']}")
            if ws.get("access"):
                lines.append(f"Access: {ws['access'].get('level', 'n/a')}")
            lines.append("")
            if ws.get("navigation"):
                lines.append("**Navigation:**")
                for nav_type, items in ws["navigation"].items():
                    lines.append(f"- {nav_type}: {', '.join(n['label'] for n in items)}")
                lines.append("")
            for region in ws.get("regions", []):
                lines.append(
                    f"- **{region['name']}**: {region.get('source', 'n/a')} ({region['display']})"
                )
            lines.append("")

    if "test_criteria" in data:
        lines.append("## Test Acceptance Criteria")
        lines.append("")
        for tc in data["test_criteria"]:
            source_label = "Story" if tc["source"] == "story" else "Test Design"
            lines.append(f"### [{tc['id']}] {tc['title']} ({source_label})")
            if tc.get("actor"):
                lines.append(f"Actor: {tc['actor']}")
            if tc.get("persona"):
                lines.append(f"Persona: {tc['persona']}")
            lines.append("")
            if tc.get("given"):
                lines.append("**Given:**")
                for g in tc["given"]:
                    lines.append(f"- {g}")
            if tc.get("when"):
                lines.append("**When:**")
                for w in tc["when"]:
                    lines.append(f"- {w}")
            if tc.get("then"):
                lines.append("**Then:**")
                for t in tc["then"]:
                    lines.append(f"- {t}")
            if tc.get("steps"):
                lines.append("**Steps:**")
                for s in tc["steps"]:
                    lines.append(f"- {s}")
            if tc.get("expected_outcomes"):
                lines.append("**Expected:**")
                for o in tc["expected_outcomes"]:
                    lines.append(f"- {o}")
            lines.append("")

    return "\n".join(lines)
