"""
Mock server implementations behind the ``dazzle mock`` CLI.

scenarios, fire_webhook, inject_error, scaffold_scenario. (The MCP ``mock``
tool was removed in flense ship I.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
        return {"error": "No mock servers running. Start with 'dazzle serve'."}

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
