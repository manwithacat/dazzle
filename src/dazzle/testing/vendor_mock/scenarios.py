"""
Scenario engine for vendor mock edge case testing.

Loads named test scenarios (e.g., "kyc_rejected", "payment_failed") that
override default mock behaviour with specific responses, error codes, delays,
and sequenced multi-step flows.
"""

from __future__ import annotations

import asyncio
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default scenario directory: alongside this module
_SCENARIOS_DIR = Path(__file__).parent / "scenarios"


@dataclass
class StepOverride:
    """A single step override within a scenario.

    Attributes:
        operation: The API operation name to override.
        response_override: Dict of field values to inject into the response.
        status_override: HTTP status code to return (None = use default).
        delay_ms: Artificial delay in milliseconds before responding.
        call_index: Which call number this applies to (0-indexed, None = all).
    """

    operation: str
    response_override: dict[str, Any] = field(default_factory=dict)
    status_override: int | None = None
    delay_ms: int = 0
    call_index: int | None = None


@dataclass
class Scenario:
    """A named test scenario for a vendor mock.

    Attributes:
        name: Scenario identifier (e.g. "kyc_rejected").
        description: Human-readable description.
        vendor: API pack name (e.g. "sumsub_kyc").
        steps: Ordered list of step overrides.
    """

    name: str
    description: str
    vendor: str
    steps: list[StepOverride] = field(default_factory=list)


@dataclass
class ErrorInjection:
    """An ad-hoc error injection for a specific operation.

    Attributes:
        status: HTTP status code to return.
        body: Response body override.
        delay_ms: Delay before responding.
        after_n: Number of successful calls before triggering (None = immediate).
    """

    status: int = 500
    body: dict[str, Any] = field(default_factory=lambda: {"error": "Injected error"})
    delay_ms: int = 0
    after_n: int | None = None


class ScenarioEngine:
    """Manages scenario loading, activation, and request interception.

    The engine is attached to a mock app and consulted on each request.
    If a matching scenario step or error injection is found, it overrides
    the default CRUD behaviour.

    Args:
        scenarios_dir: Directory containing scenario TOML files.
            Defaults to the built-in scenarios/ directory.
        project_root: Optional project root for project-local scenarios.
            Checks ``<project_root>/.dazzle/scenarios/`` first.
    """

    def __init__(
        self,
        scenarios_dir: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._scenarios_dir = scenarios_dir or _SCENARIOS_DIR
        self._project_root = project_root
        self._active: dict[str, Scenario] = {}  # vendor → active scenario
        self._call_counts: dict[str, int] = {}  # operation → call count
        self._errors: dict[str, ErrorInjection] = {}  # operation → injection
        self._latency: dict[str, int] = {}  # operation → delay_ms

    def _resolve_scenario_path(self, vendor: str, scenario_name: str) -> Path:
        """Resolve scenario TOML path, checking project-local dir first."""
        if self._project_root is not None:
            project_path = (
                self._project_root / ".dazzle" / "scenarios" / vendor / f"{scenario_name}.toml"
            )
            if project_path.exists():
                return project_path
        builtin_path = self._scenarios_dir / vendor / f"{scenario_name}.toml"
        if builtin_path.exists():
            return builtin_path
        raise FileNotFoundError(f"Scenario not found: {vendor}/{scenario_name}.toml")

    def load_scenario(self, vendor: str, scenario_name: str) -> Scenario:
        """Load and activate a named scenario.

        Args:
            vendor: API pack name (e.g. "sumsub_kyc").
            scenario_name: Scenario name (e.g. "kyc_rejected").

        Returns:
            The loaded Scenario.

        Raises:
            FileNotFoundError: If the scenario TOML file doesn't exist.
        """
        path = self._resolve_scenario_path(vendor, scenario_name)

        with open(path, "rb") as f:
            data = tomllib.load(f)

        scenario_data = data.get("scenario", {})
        steps = []
        for step_data in data.get("steps", []):
            steps.append(
                StepOverride(
                    operation=step_data["operation"],
                    response_override=step_data.get("response_override", {}),
                    status_override=step_data.get("status_override"),
                    delay_ms=step_data.get("delay_ms", 0),
                    call_index=step_data.get("call_index"),
                )
            )

        scenario = Scenario(
            name=scenario_data.get("name", scenario_name),
            description=scenario_data.get("description", ""),
            vendor=scenario_data.get("vendor", vendor),
            steps=steps,
        )

        self._active[vendor] = scenario
        self._call_counts.clear()
        logger.info("Loaded scenario '%s' for vendor '%s'", scenario_name, vendor)
        return scenario

    def reset(self, vendor: str | None = None) -> None:
        """Reset to default behaviour.

        Args:
            vendor: Specific vendor to reset, or None for all.
        """
        if vendor:
            self._active.pop(vendor, None)
            # Clear operation-level overrides for this vendor's operations
            ops_to_clear = [k for k in self._errors if k.startswith(f"{vendor}:")]
            for k in ops_to_clear:
                del self._errors[k]
            ops_to_clear = [k for k in self._latency if k.startswith(f"{vendor}:")]
            for k in ops_to_clear:
                del self._latency[k]
        else:
            self._active.clear()
            self._errors.clear()
            self._latency.clear()
        self._call_counts.clear()

    def inject_error(
        self,
        vendor: str,
        operation: str,
        *,
        status: int = 500,
        body: dict[str, Any] | None = None,
        after_n: int | None = None,
    ) -> None:
        """Inject an error for a specific operation.

        Args:
            vendor: API pack name.
            operation: Operation name from the API pack.
            status: HTTP status code to return.
            body: Response body (defaults to generic error).
            after_n: Number of successful calls before triggering.
        """
        key = f"{vendor}:{operation}"
        self._errors[key] = ErrorInjection(
            status=status,
            body=body or {"error": "Injected error", "status": status},
            after_n=after_n,
        )

    def inject_latency(self, vendor: str, operation: str, *, delay_ms: int) -> None:
        """Add artificial latency to an operation.

        Args:
            vendor: API pack name.
            operation: Operation name.
            delay_ms: Delay in milliseconds.
        """
        key = f"{vendor}:{operation}"
        self._latency[key] = delay_ms

    async def intercept(
        self,
        vendor: str,
        operation: str,
        response_data: dict[str, Any],
        status: int,
    ) -> tuple[dict[str, Any], int]:
        """Check for scenario overrides and apply them.

        Called by the mock handler after the default CRUD logic produces
        a response. Returns the (potentially modified) response data and
        status code.

        Args:
            vendor: API pack name.
            operation: Operation name.
            response_data: Default response from CRUD logic.
            status: Default HTTP status code.

        Returns:
            Tuple of (response_data, status_code), potentially overridden.
        """
        # Track call count
        count_key = f"{vendor}:{operation}"
        count = self._call_counts.get(count_key, 0)
        self._call_counts[count_key] = count + 1

        # Check latency injection
        latency_key = f"{vendor}:{operation}"
        if latency_key in self._latency:
            delay = self._latency[latency_key]
            if delay > 0:
                await asyncio.sleep(delay / 1000.0)

        # Check error injection
        error_key = f"{vendor}:{operation}"
        if error_key in self._errors:
            injection = self._errors[error_key]
            if injection.after_n is None or count >= injection.after_n:
                if injection.delay_ms > 0:
                    await asyncio.sleep(injection.delay_ms / 1000.0)
                return dict(injection.body), injection.status

        # Check active scenario
        scenario = self._active.get(vendor)
        if scenario:
            for step in scenario.steps:
                if step.operation != operation:
                    continue

                # Check call_index filter
                if step.call_index is not None and count != step.call_index:
                    continue

                # Apply delay
                if step.delay_ms > 0:
                    await asyncio.sleep(step.delay_ms / 1000.0)

                # Apply status override
                if step.status_override is not None:
                    status = step.status_override

                # Apply response overrides (merge into existing data)
                if step.response_override:
                    response_data = {**response_data, **step.response_override}

                break  # Use first matching step

        return response_data, status

    def _scenario_dirs(self) -> list[Path]:
        """Return scenario directories to scan (project-local first)."""
        dirs: list[Path] = []
        if self._project_root is not None:
            project_dir = self._project_root / ".dazzle" / "scenarios"
            if project_dir.is_dir():
                dirs.append(project_dir)
        if self._scenarios_dir.exists():
            dirs.append(self._scenarios_dir)
        return dirs

    def list_scenarios(self, vendor: str | None = None) -> list[str]:
        """List available scenario names.

        Args:
            vendor: Filter by vendor, or None for all.

        Returns:
            List of "vendor/scenario_name" strings (deduplicated).
        """
        seen: set[str] = set()
        results: list[str] = []
        for scenarios_dir in self._scenario_dirs():
            if vendor:
                vendor_dir = scenarios_dir / vendor
                if vendor_dir.is_dir():
                    for f in sorted(vendor_dir.glob("*.toml")):
                        key = f"{vendor}/{f.stem}"
                        if key not in seen:
                            seen.add(key)
                            results.append(key)
            else:
                for vendor_dir in sorted(scenarios_dir.iterdir()):
                    if vendor_dir.is_dir():
                        for f in sorted(vendor_dir.glob("*.toml")):
                            key = f"{vendor_dir.name}/{f.stem}"
                            if key not in seen:
                                seen.add(key)
                                results.append(key)
        return sorted(results)

    @property
    def active_scenarios(self) -> dict[str, str]:
        """Currently active scenarios, keyed by vendor → scenario name."""
        return {v: s.name for v, s in self._active.items()}
