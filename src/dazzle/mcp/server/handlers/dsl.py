"""
DSL analysis tool handlers.

Handles DSL validation, module listing, entity/surface inspection,
pattern analysis, and linting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns

from ..state import get_active_project, is_dev_mode


def validate_dsl(project_root: Path) -> str:
    """Validate DSL files in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        result: dict[str, Any] = {
            "status": "valid",
            "project_path": str(project_root),
            "modules": len(modules),
            "entities": len(app_spec.domain.entities),
            "surfaces": len(app_spec.surfaces),
            "apis": len(app_spec.apis),
        }

        # Add project context in dev mode
        if is_dev_mode():
            result["project"] = get_active_project()

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps(
            {"status": "error", "project_path": str(project_root), "error": str(e)},
            indent=2,
        )


def list_modules(project_root: Path) -> str:
    """List all modules in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        parsed_modules = parse_modules(dsl_files)

        modules = {}
        for idx, module in enumerate(parsed_modules):
            modules[module.name] = {
                "file": str(dsl_files[idx].relative_to(project_root)),
                "dependencies": module.uses,
            }

        return json.dumps({"project_path": str(project_root), "modules": modules}, indent=2)
    except Exception as e:
        return json.dumps({"project_path": str(project_root), "error": str(e)}, indent=2)


def inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    entity_name = args.get("entity_name") or args.get("name")
    if not entity_name:
        return json.dumps({"error": "entity_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
        if not entity:
            return json.dumps({"error": f"Entity '{entity_name}' not found"})

        return json.dumps(
            {
                "name": entity.name,
                "description": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind),
                        "required": f.is_required,
                        "modifiers": [str(m) for m in f.modifiers],
                    }
                    for f in entity.fields
                ],
                "constraints": [str(c) for c in entity.constraints] if entity.constraints else [],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def inspect_surface(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a surface definition."""
    surface_name = args.get("surface_name") or args.get("name")
    if not surface_name:
        return json.dumps({"error": "surface_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
        if not surface:
            return json.dumps({"error": f"Surface '{surface_name}' not found"})

        return json.dumps(
            {
                "name": surface.name,
                "entity": surface.entity_ref,
                "mode": str(surface.mode),
                "description": surface.title,
                "sections": len(surface.sections) if surface.sections else 0,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def analyze_patterns(project_root: Path) -> str:
    """Analyze the project for patterns."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        crud_patterns = detect_crud_patterns(app_spec)
        integration_patterns = detect_integration_patterns(app_spec)

        return json.dumps(
            {
                "crud_patterns": [
                    {
                        "entity": p.entity_name,
                        "has_create": p.has_create,
                        "has_list": p.has_list,
                        "has_detail": p.has_detail,
                        "has_edit": p.has_edit,
                        "is_complete": p.is_complete,
                        "missing_operations": p.missing_operations,
                        "is_system_managed": p.is_system_managed,
                    }
                    for p in crud_patterns
                ],
                "integration_patterns": [
                    {
                        "name": p.integration_name,
                        "service": p.service_name,
                        "has_actions": p.has_actions,
                        "has_syncs": p.has_syncs,
                        "action_count": p.action_count,
                        "sync_count": p.sync_count,
                        "connected_entities": list(p.connected_entities or []),
                        "connected_surfaces": list(p.connected_surfaces or []),
                    }
                    for p in integration_patterns
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def export_frontend_spec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Export a framework-agnostic frontend specification from DSL."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Load sitespec (optional)
        sitespec = None
        try:
            from dazzle.core.sitespec_loader import load_sitespec

            sitespec = load_sitespec(project_root, use_defaults=True)
        except Exception:
            pass

        # Load stories (optional)
        stories = []
        try:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)
        except Exception:
            pass

        # Load test designs (optional)
        test_designs = []
        try:
            from dazzle.testing.test_design_persistence import load_test_designs

            test_designs = load_test_designs(project_root)
        except Exception:
            pass

        from dazzle.core.frontend_spec_export import export_frontend_spec

        fmt = args.get("format", "markdown")
        sections = args.get("sections")
        entities = args.get("entities")

        result = export_frontend_spec(
            app_spec, sitespec, stories, test_designs, fmt, sections, entities
        )
        return result
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def lint_project(project_root: Path, args: dict[str, Any]) -> str:
    """Run linting on the project."""
    extended = args.get("extended", False)

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        errors, warnings = lint_appspec(app_spec, extended=extended)

        return json.dumps(
            {
                "errors": len(errors),
                "warnings": len(warnings),
                "issues": [str(e) for e in errors] + [str(w) for w in warnings],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_unified_issues(project_root: Path, args: dict[str, Any]) -> str:
    """Get unified view of all issues from lint, compliance, and fidelity.

    Cross-references findings from multiple analysis tools, deduplicating
    by entity+field and showing which tools flagged each issue.
    """
    from dazzle.mcp.event_first_tools import infer_compliance_requirements

    extended = args.get("extended", False)

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Run lint
        lint_errors, lint_warnings = lint_appspec(app_spec, extended=extended)

        # Run compliance inference
        compliance = infer_compliance_requirements(app_spec)

        # Build unified issue map keyed by entity.field (or just message for global)
        issues: dict[str, dict[str, Any]] = {}

        # Parse lint messages to extract entity+field where possible
        for msg in lint_errors:
            key = _extract_issue_key(msg)
            if key not in issues:
                issues[key] = {
                    "key": key,
                    "severity": "error",
                    "sources": [],
                    "messages": [],
                }
            issues[key]["sources"].append("lint")
            issues[key]["messages"].append(msg)

        for msg in lint_warnings:
            key = _extract_issue_key(msg)
            if key not in issues:
                issues[key] = {
                    "key": key,
                    "severity": "warning",
                    "sources": [],
                    "messages": [],
                }
            if "lint" not in issues[key]["sources"]:
                issues[key]["sources"].append("lint")
            issues[key]["messages"].append(msg)

        # Add compliance findings
        for field_info in compliance.get("pii_fields", []):
            key = f"{field_info['entity']}.{field_info['field']}"
            if key not in issues:
                issues[key] = {
                    "key": key,
                    "severity": "info",
                    "sources": [],
                    "messages": [],
                }
            if "compliance" not in issues[key]["sources"]:
                issues[key]["sources"].append("compliance")
            issues[key]["messages"].append(
                f"PII field ({field_info['pattern']}): consider GDPR classification"
            )

        for field_info in compliance.get("financial_fields", []):
            key = f"{field_info['entity']}.{field_info['field']}"
            if key not in issues:
                issues[key] = {
                    "key": key,
                    "severity": "info",
                    "sources": [],
                    "messages": [],
                }
            if "compliance" not in issues[key]["sources"]:
                issues[key]["sources"].append("compliance")
            issues[key]["messages"].append(
                f"Financial field ({field_info['pattern']}): consider PCI-DSS"
            )

        for field_info in compliance.get("health_fields", []):
            key = f"{field_info['entity']}.{field_info['field']}"
            if key not in issues:
                issues[key] = {
                    "key": key,
                    "severity": "info",
                    "sources": [],
                    "messages": [],
                }
            if "compliance" not in issues[key]["sources"]:
                issues[key]["sources"].append("compliance")
            issues[key]["messages"].append(
                f"Health field ({field_info['pattern']}): consider HIPAA"
            )

        # Build cross-reference summary for issues flagged by multiple tools
        multi_source_issues = [i for i in issues.values() if len(i["sources"]) > 1]

        # Sort by severity then by key
        severity_order = {"error": 0, "warning": 1, "info": 2}
        sorted_issues = sorted(
            issues.values(),
            key=lambda x: (severity_order.get(x["severity"], 3), x["key"]),
        )

        return json.dumps(
            {
                "total_issues": len(issues),
                "error_count": len(lint_errors),
                "warning_count": len(lint_warnings),
                "compliance_findings": (
                    len(compliance.get("pii_fields", []))
                    + len(compliance.get("financial_fields", []))
                    + len(compliance.get("health_fields", []))
                ),
                "multi_source_count": len(multi_source_issues),
                "recommended_frameworks": compliance.get("recommended_frameworks", []),
                "issues": sorted_issues,
                "cross_references": [
                    {
                        "key": i["key"],
                        "flagged_by": i["sources"],
                        "hint": f"Flagged by {' and '.join(i['sources'])}. "
                        "Address the underlying issue to resolve all findings.",
                    }
                    for i in multi_source_issues
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _extract_issue_key(message: str) -> str:
    """Extract entity.field key from a lint message, or return the message."""
    import re

    # Try to extract "Entity 'X'" or "entity 'X'" pattern
    entity_match = re.search(r"[Ee]ntity ['\"](\w+)['\"]", message)
    field_match = re.search(r"[Ff]ield ['\"](\w+)['\"]", message)

    if entity_match and field_match:
        return f"{entity_match.group(1)}.{field_match.group(1)}"
    if entity_match:
        return entity_match.group(1)

    # Fallback: use a truncated version of the message as key
    return message[:80] if len(message) > 80 else message
