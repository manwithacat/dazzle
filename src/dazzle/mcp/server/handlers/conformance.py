"""Conformance tool handlers — query DSL conformance cases and coverage.

Provides 4 operations:
- summary: run derivation pipeline, return coverage metric and per-entity case counts
- cases: return cases for a specific entity
- gaps: find entities with permit blocks but no scope blocks
- monitor_status: return current conformance monitor state (if installed)
"""

import json
import logging
from pathlib import Path
from typing import Any

from .common import error_response, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


@wrap_handler_errors
def conformance_summary_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run derivation pipeline, return coverage metric and per-entity case counts."""
    from dazzle.conformance.plugin import build_conformance_report, collect_conformance_cases

    auth_enabled: bool = args.get("auth_enabled", True)
    cases, _fixtures = collect_conformance_cases(project_root, auth_enabled=auth_enabled)
    report = build_conformance_report(cases)
    return json.dumps(report, indent=2)


@wrap_handler_errors
def conformance_cases_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Return conformance cases for a specific entity."""
    from dazzle.conformance.plugin import collect_conformance_cases

    entity_name: str | None = args.get("entity_name")
    if not entity_name:
        return error_response("entity_name is required")

    auth_enabled: bool = args.get("auth_enabled", True)
    cases, _fixtures = collect_conformance_cases(project_root, auth_enabled=auth_enabled)

    entity_cases = [c for c in cases if c.entity == entity_name]
    if not entity_cases:
        return error_response(f"No conformance cases found for entity: {entity_name}")

    return json.dumps(
        {
            "entity": entity_name,
            "cases": [
                {
                    "persona": c.persona,
                    "operation": c.operation,
                    "expected_status": c.expected_status,
                    "expected_rows": c.expected_rows,
                    "scope_type": c.scope_type.value
                    if hasattr(c.scope_type, "value")
                    else str(c.scope_type),
                    "description": c.description,
                    "test_id": c.test_id,
                }
                for c in entity_cases
            ],
            "total": len(entity_cases),
        },
        indent=2,
    )


@wrap_handler_errors
def conformance_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Find entities with permit blocks but no scope blocks (conformance gaps)."""
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(project_root)
    gaps = []

    for entity in getattr(appspec, "entities", []):
        access = getattr(entity, "access", None)
        if access is None:
            continue

        permissions = getattr(access, "permissions", [])
        scopes = getattr(access, "scopes", [])

        has_permits = any(getattr(p, "effect", "permit") == "permit" for p in permissions)
        has_scopes = len(scopes) > 0

        if has_permits and not has_scopes:
            gaps.append(
                {
                    "entity": entity.name,
                    "has_permits": True,
                    "has_scopes": False,
                }
            )

    return json.dumps({"gaps": gaps, "total": len(gaps)}, indent=2)


@wrap_handler_errors
def conformance_monitor_status_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Return the current conformance monitor state.

    If a ConformanceMonitor has been installed (e.g. during a test scenario),
    returns the current observations and comparison report. Otherwise returns
    an empty status.
    """
    from dazzle.rbac.audit import get_audit_sink

    sink = get_audit_sink()

    # Check if current sink is an InMemoryAuditSink (monitor installed)
    from dazzle.rbac.audit import InMemoryAuditSink

    if isinstance(sink, InMemoryAuditSink):
        return json.dumps(
            {
                "monitor_installed": True,
                "observations": len(sink.records),
                "records": [r.to_dict() for r in sink.records[-20:]],
            },
            indent=2,
            default=str,
        )

    return json.dumps({"monitor_installed": False, "observations": 0}, indent=2)
