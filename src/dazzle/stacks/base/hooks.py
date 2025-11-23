"""
Hook system for backend extensibility.

Hooks allow backends to run custom logic before and after code generation:
- Pre-build: Validation, setup, initialization
- Post-build: Provisioning, formatting, deployment
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ...core import ir


class HookPhase(Enum):
    """When a hook runs."""

    PRE_BUILD = "pre_build"
    POST_BUILD = "post_build"


@dataclass
class HookContext:
    """
    Context passed to hooks during execution.

    Provides access to:
    - AppSpec being generated
    - Output directory
    - Backend name
    - Generation options
    - Artifacts from generators and previous hooks
    """

    spec: ir.AppSpec
    output_dir: Path
    backend_name: str
    options: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def add_artifact(self, key: str, value: Any) -> None:
        """Add an artifact to the context for later hooks to access."""
        self.artifacts[key] = value

    def get_artifact(self, key: str, default: Any = None) -> Any:
        """Get an artifact from the context."""
        return self.artifacts.get(key, default)


@dataclass
class HookResult:
    """
    Result from hook execution.

    Attributes:
        success: Whether hook executed successfully
        message: Human-readable message about what happened
        artifacts: New data to add to context for subsequent hooks
        display_to_user: Whether to show this result to the user
        stop_on_failure: Whether to abort build if this hook fails
    """

    success: bool
    message: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    display_to_user: bool = False
    stop_on_failure: bool = True

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.message}"


class Hook(ABC):
    """
    Base class for all hooks.

    Hooks are executed at specific points in the build process:
    - Pre-build: Before any code generation
    - Post-build: After all code generation

    Example:
        class CreateSuperuserHook(Hook):
            name = "create_superuser"
            description = "Create Django admin user"
            phase = HookPhase.POST_BUILD

            def execute(self, context: HookContext) -> HookResult:
                # Generate credentials
                password = secrets.token_urlsafe(16)
                # Write to file
                # Return result
                return HookResult(
                    success=True,
                    message="Admin user created",
                    artifacts={"admin_password": password},
                    display_to_user=True
                )
    """

    name: str = "unnamed_hook"
    description: str = "No description"
    phase: HookPhase = HookPhase.POST_BUILD
    enabled: bool = True

    @abstractmethod
    def execute(self, context: HookContext) -> HookResult:
        """
        Execute the hook logic.

        Args:
            context: Hook context with spec, output_dir, and artifacts

        Returns:
            HookResult indicating success/failure and any artifacts
        """
        pass

    def should_run(self, context: HookContext) -> bool:
        """
        Determine if this hook should run.

        Override to add conditional logic (e.g., only run in production).

        Args:
            context: Hook context

        Returns:
            True if hook should execute, False to skip
        """
        return self.enabled

    def __str__(self) -> str:
        return f"{self.name} ({self.phase.value}): {self.description}"


class HookManager:
    """
    Manages hook registration and execution.

    Backends use this to:
    - Register hooks
    - Run all hooks for a phase
    - Collect and display results
    """

    def __init__(self):
        self._hooks: dict[HookPhase, list[Hook]] = {
            HookPhase.PRE_BUILD: [],
            HookPhase.POST_BUILD: [],
        }

    def register(self, hook: Hook) -> None:
        """Register a hook for its phase."""
        self._hooks[hook.phase].append(hook)

    def register_many(self, hooks: list[Hook]) -> None:
        """Register multiple hooks."""
        for hook in hooks:
            self.register(hook)

    def run_phase(self, phase: HookPhase, context: HookContext) -> list[HookResult]:
        """
        Run all hooks for a specific phase.

        Args:
            phase: Which phase to run (PRE_BUILD or POST_BUILD)
            context: Hook context

        Returns:
            List of HookResults from all executed hooks
        """
        results = []
        hooks = self._hooks[phase]

        for hook in hooks:
            if not hook.should_run(context):
                continue

            try:
                result = hook.execute(context)
                results.append(result)

                # Add hook artifacts to context for subsequent hooks
                for key, value in result.artifacts.items():
                    context.add_artifact(key, value)

                # Stop if hook failed and requested stop
                if not result.success and result.stop_on_failure:
                    break

            except Exception as e:
                # Hook execution failed with exception
                result = HookResult(
                    success=False,
                    message=f"Hook '{hook.name}' failed: {str(e)}",
                    display_to_user=True,
                    stop_on_failure=True,
                )
                results.append(result)
                break

        return results

    def get_hooks(self, phase: HookPhase) -> list[Hook]:
        """Get all hooks for a phase."""
        return self._hooks[phase]

    def has_hooks(self, phase: HookPhase) -> bool:
        """Check if any hooks are registered for a phase."""
        return len(self._hooks[phase]) > 0
