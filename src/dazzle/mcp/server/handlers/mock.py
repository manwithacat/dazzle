"""
Mock server management handlers.

Provides operations for managing vendor mock servers at runtime:
status, scenarios, fire_webhook, request_log, inject_error, scaffold_scenario.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .common import error_response, extract_progress, wrap_handler_errors

if TYPE_CHECKING:
    from dazzle.testing.vendor_mock.orchestrator import MockOrchestrator


def _get_orchestrator() -> MockOrchestrator | None:
    """Get the mock orchestrator from server state."""
    from dazzle.mcp.server.state import get_mock_orchestrator

    return get_mock_orchestrator()


# ---------------------------------------------------------------------------
# Impl functions (no MCP types, explicit params, return plain dicts)
# ---------------------------------------------------------------------------


def mock_scenarios_impl(
    *,
    action: str = "list",
    vendor: str | None = None,
    scenario_name: str | None = None,
) -> dict[str, Any]:
    """List, activate, or deactivate test scenarios."""
    orch = _get_orchestrator()

    if action == "list":
        from dazzle.testing.vendor_mock.scenarios import ScenarioEngine

        if orch is not None and vendor:
            app = orch.get_app(vendor)
            engine = getattr(app.state, "scenario_engine", None) or ScenarioEngine(
                project_root=orch.project_root
            )
        else:
            engine = ScenarioEngine(project_root=orch.project_root if orch else None)

        scenarios = engine.list_scenarios(vendor)
        active = engine.active_scenarios if hasattr(engine, "active_scenarios") else {}

        return {
            "scenarios": scenarios,
            "active": active,
            "count": len(scenarios),
        }

    if orch is None:
        return {"error": "No mock servers running. Start with 'dazzle serve --local'."}

    if not vendor:
        return {"error": "vendor parameter required for activate/deactivate"}

    if vendor not in orch.vendors:
        return {
            "error": f"Vendor '{vendor}' not found",
            "available": list(orch.vendors.keys()),
        }

    app = orch.get_app(vendor)
    engine = getattr(app.state, "scenario_engine", None)
    if engine is None:
        return {"error": f"No scenario engine for vendor '{vendor}'"}

    if action == "activate":
        if not scenario_name:
            return {"error": "scenario_name required for activate"}
        try:
            scenario = engine.load_scenario(vendor, scenario_name)
            return {
                "status": "activated",
                "vendor": vendor,
                "scenario": scenario.name,
                "description": scenario.description,
                "steps": len(scenario.steps),
            }
        except FileNotFoundError as e:
            return {"error": str(e)}

    elif action == "deactivate":
        engine.reset(vendor)
        return {"status": "deactivated", "vendor": vendor}

    return {"error": f"Unknown action: {action}. Use list, activate, or deactivate."}


def mock_fire_webhook_impl(
    *,
    vendor: str,
    event: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fire a webhook event to the running app."""
    from dazzle.testing.vendor_mock.webhooks import WebhookDispatcher

    dispatcher = WebhookDispatcher()

    try:
        events = dispatcher.list_events(vendor)
        if not events:
            return {
                "error": f"No webhook events defined for vendor '{vendor}'",
                "hint": "Add [webhooks] section to the pack TOML",
            }

        attempt = dispatcher.fire_sync(
            vendor,
            event,
            overrides=overrides,
        )

        return {
            "status": "delivered" if attempt.status_code else "failed",
            "vendor": vendor,
            "event": event,
            "target_url": attempt.target_url,
            "status_code": attempt.status_code,
            "elapsed_ms": round(attempt.elapsed_ms, 1),
            "error": attempt.error,
        }
    except ValueError as e:
        return {"error": str(e)}


def mock_inject_error_impl(
    *,
    vendor: str,
    operation: str,
    status: int = 500,
    body: Any = None,
    after_n: int | None = None,
) -> dict[str, Any]:
    """Inject an error response for a vendor operation."""
    orch = _get_orchestrator()
    if orch is None:
        return {"error": "No mock servers running"}

    if vendor not in orch.vendors:
        return {
            "error": f"Vendor '{vendor}' not found",
            "available": list(orch.vendors.keys()),
        }

    app = orch.get_app(vendor)
    engine = getattr(app.state, "scenario_engine", None)
    if engine is None:
        return {"error": f"No scenario engine for vendor '{vendor}'"}

    engine.inject_error(
        vendor,
        operation,
        status=status,
        body=body,
        after_n=after_n,
    )

    return {
        "status": "injected",
        "vendor": vendor,
        "operation": operation,
        "error_status": status,
        "after_n": after_n,
    }


def mock_scaffold_scenario_impl(
    *,
    vendor: str = "my_vendor",
    name: str = "custom_scenario",
) -> dict[str, Any]:
    """Generate a scenario TOML template."""
    toml_content = f'''# Scenario: {name}
# Vendor: {vendor}

[scenario]
name = "{name}"
description = ""
vendor = "{vendor}"

# Steps override default mock responses for specific operations.
# Each step targets an operation from the API pack.

[[steps]]
operation = "example_operation"

[steps.response_override]
status = "error"
message = "Simulated failure"

# status_override = 500    # Override HTTP status code
# delay_ms = 2000          # Add artificial delay
# call_index = 0           # Only apply to Nth call (0-indexed)
'''

    save_path = f".dazzle/scenarios/{vendor}/{name}.toml"

    return {
        "toml": toml_content,
        "save_path": save_path,
        "hint": f"Save to {save_path} in your project directory",
    }


@wrap_handler_errors
def mock_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List mock servers with ports, URLs, and health."""
    progress = extract_progress(args)
    progress.log_sync("Checking mock server status...")

    orch = _get_orchestrator()
    if orch is None:
        return json.dumps(
            {
                "running": False,
                "message": "No mock servers running. Start with 'dazzle serve --local' on a project that uses API packs.",
                "hint": 'Declare a service with spec: inline "pack:<name>" in your DSL to enable auto-mocking.',
            },
            indent=2,
        )

    health = orch.health_check()
    vendors = []
    for name, mock in orch.vendors.items():
        vendors.append(
            {
                "pack_name": name,
                "provider": mock.provider,
                "port": mock.port,
                "base_url": mock.base_url,
                "env_var": mock.env_var,
                "healthy": health.get(name, False),
            }
        )

    return json.dumps(
        {
            "running": orch.is_running,
            "vendor_count": len(vendors),
            "vendors": vendors,
        },
        indent=2,
    )


@wrap_handler_errors
def mock_scenarios_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List, activate, or deactivate test scenarios."""
    progress = extract_progress(args)
    action = args.get("action", "list")
    progress.log_sync(f"Mock scenarios: {action}...")
    result = mock_scenarios_impl(
        action=action,
        vendor=args.get("vendor"),
        scenario_name=args.get("scenario_name"),
    )
    if "error" in result and action != "list":
        return error_response(result["error"])
    return json.dumps(result, indent=2)


@wrap_handler_errors
def mock_fire_webhook_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Fire a webhook event to the running app."""
    progress = extract_progress(args)
    vendor = args.get("vendor")
    event = args.get("event")

    if not vendor:
        return error_response("vendor parameter required")
    if not event:
        return error_response("event parameter required")

    progress.log_sync(f"Firing webhook {vendor}/{event}...")
    result = mock_fire_webhook_impl(
        vendor=vendor,
        event=event,
        overrides=args.get("overrides"),
    )
    if "error" in result and "hint" not in result:
        return error_response(result["error"])
    return json.dumps(result, indent=2)


@wrap_handler_errors
def mock_request_log_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Query recorded requests for a vendor mock."""
    progress = extract_progress(args)
    vendor = args.get("vendor")
    method_filter = args.get("method")
    path_filter = args.get("path")
    limit = args.get("limit", 20)

    progress.log_sync("Querying mock request log...")

    orch = _get_orchestrator()
    if orch is None:
        return error_response("No mock servers running")

    if vendor and vendor not in orch.vendors:
        return json.dumps(
            {
                "error": f"Vendor '{vendor}' not found",
                "available": list(orch.vendors.keys()),
            }
        )

    results: list[dict[str, Any]] = []
    vendors_to_check = [vendor] if vendor else list(orch.vendors.keys())

    for v in vendors_to_check:
        try:
            store = orch.get_store(v)
            log = getattr(store, "request_log", [])
            for entry in log:
                if method_filter and entry.get("method", "").upper() != method_filter.upper():
                    continue
                if path_filter and path_filter not in entry.get("path", ""):
                    continue
                results.append({"vendor": v, **entry})
        except (KeyError, AttributeError):
            continue

    # Sort by timestamp descending and limit
    results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    results = results[:limit]

    return json.dumps(
        {
            "count": len(results),
            "requests": results,
        },
        indent=2,
    )


@wrap_handler_errors
def mock_inject_error_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Inject an error response for a vendor operation."""
    progress = extract_progress(args)
    vendor = args.get("vendor")
    operation = args.get("operation_name")

    if not vendor:
        return error_response("vendor parameter required")
    if not operation:
        return error_response("operation_name parameter required")

    progress.log_sync(f"Injecting error for {vendor}/{operation}...")
    result = mock_inject_error_impl(
        vendor=vendor,
        operation=operation,
        status=args.get("status_code", 500),
        body=args.get("body"),
        after_n=args.get("after_n"),
    )
    if "error" in result:
        return error_response(result["error"]) if "available" not in result else json.dumps(result)
    return json.dumps(result, indent=2)


@wrap_handler_errors
def mock_scaffold_scenario_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Generate a scenario TOML template."""
    progress = extract_progress(args)
    vendor = args.get("vendor", "my_vendor")
    name = args.get("scenario_name", "custom_scenario")

    progress.log_sync(f"Scaffolding scenario {vendor}/{name}...")
    result = mock_scaffold_scenario_impl(vendor=vendor, name=name)
    return json.dumps(result, indent=2)
