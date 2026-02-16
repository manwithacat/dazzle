"""DSL validation and linting handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

from ...state import get_active_project, is_dev_mode
from ..common import extract_progress, load_project_appspec, wrap_handler_errors
from ..text_utils import extract_issue_key

logger = logging.getLogger(__name__)


@wrap_handler_errors
def validate_dsl(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """Validate DSL files in the project."""
    progress = extract_progress(args)
    try:
        progress.log_sync("Loading project DSL...")
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


@wrap_handler_errors
def list_modules(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """List all modules in the project."""
    progress = extract_progress(args)
    progress.log_sync("Listing project modules...")
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


@wrap_handler_errors
def lint_project(project_root: Path, args: dict[str, Any]) -> str:
    """Run linting on the project."""
    progress = extract_progress(args)
    extended = args.get("extended", False)

    progress.log_sync("Loading project DSL...")
    app_spec = load_project_appspec(project_root)

    progress.log_sync("Running lint checks...")
    errors, warnings = lint_appspec(app_spec, extended=extended)

    return json.dumps(
        {
            "errors": len(errors),
            "warnings": len(warnings),
            "issues": [str(e) for e in errors] + [str(w) for w in warnings],
        },
        indent=2,
    )


@wrap_handler_errors
def get_unified_issues(project_root: Path, args: dict[str, Any]) -> str:
    """Get unified view of all issues from lint, compliance, and fidelity.

    Cross-references findings from multiple analysis tools, deduplicating
    by entity+field and showing which tools flagged each issue.
    """
    from dazzle.mcp.event_first_tools import infer_compliance_requirements

    progress = extract_progress(args)
    extended = args.get("extended", False)

    progress.log_sync("Loading project DSL...")
    app_spec = load_project_appspec(project_root)

    # Run lint
    progress.log_sync("Running lint checks...")
    lint_errors, lint_warnings = lint_appspec(app_spec, extended=extended)

    # Run compliance inference
    progress.log_sync("Inferring compliance requirements...")
    compliance = infer_compliance_requirements(app_spec)

    # Build unified issue map keyed by entity.field (or just message for global)
    issues: dict[str, dict[str, Any]] = {}

    # Parse lint messages to extract entity+field where possible
    for msg in lint_errors:
        key = extract_issue_key(msg)
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
        key = extract_issue_key(msg)
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
        issues[key]["messages"].append(f"Health field ({field_info['pattern']}): consider HIPAA")

    # Build cross-reference summary for issues flagged by multiple tools
    progress.log_sync("Cross-referencing findings...")
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
