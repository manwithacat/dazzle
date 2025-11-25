"""
Stack registry and preset definitions for DAZZLE.

Stacks are technology combinations that generate applications.
A stack can be a preset (like 'micro' or 'django_next') or a custom
list of stack implementations (what used to be called "backends").

User-facing terminology: "stack"
Internal implementation: Backend class
"""

from dataclasses import dataclass

from .errors import DazzleError


class StackError(DazzleError):
    """Raised when stack operations fail."""

    pass


@dataclass
class StackPreset:
    """
    A preset stack configuration.

    Stacks are ordered lists of backends that work together
    to generate a complete application.
    """

    name: str
    description: str
    backends: list[str]
    example_dsl: str | None = None  # For demo command


# Default stack for demo command
DEFAULT_DEMO_STACK = "micro"


# Built-in stack presets
BUILTIN_STACKS: dict[str, StackPreset] = {
    "micro": StackPreset(
        name="micro",
        description="Single Django app with SQLite (easiest to deploy on Heroku/Vercel)",
        backends=["django_micro_modular"],
        example_dsl="simple_task",
    ),
    "express_micro": StackPreset(
        name="express_micro",
        description="Single Express.js app with SQLite (Node.js alternative, perfect for JS developers)",
        backends=["express_micro"],
        example_dsl="simple_task",
    ),
    "nextjs_onebox": StackPreset(
        name="nextjs_onebox",
        description="Next.js 14 + Prisma + PostgreSQL in single Docker container (modern full-stack)",
        backends=["nextjs_onebox"],
        example_dsl="simple_task",
    ),
    "django_next": StackPreset(
        name="django_next",
        description="Django REST API + Next.js frontend + Docker",
        backends=["django_api", "nextjs_frontend", "docker"],
        example_dsl="support_tickets",
    ),
    "django_next_cloud": StackPreset(
        name="django_next_cloud",
        description="Django + Next.js + Docker + Terraform (AWS)",
        backends=["django_api", "nextjs_frontend", "docker", "terraform"],
        example_dsl="support_tickets",
    ),
    "api_only": StackPreset(
        name="api_only",
        description="Django REST API + OpenAPI spec + Docker",
        backends=["django_api", "openapi", "docker"],
        example_dsl="simple_task",
    ),
    "openapi_only": StackPreset(
        name="openapi_only",
        description="OpenAPI specification only",
        backends=["openapi"],
        example_dsl="simple_task",
    ),
}


def get_stack_preset(name: str) -> StackPreset | None:
    """
    Get a built-in stack preset by name.

    Args:
        name: Stack name

    Returns:
        StackPreset if found, None otherwise
    """
    return BUILTIN_STACKS.get(name)


def list_stack_presets() -> list[str]:
    """
    List all available built-in stack presets.

    Returns:
        List of stack names
    """
    return sorted(BUILTIN_STACKS.keys())


def resolve_stack_backends(
    stack_name: str | None,
    explicit_backends: list[str] | None = None,
) -> list[str]:
    """
    Resolve backend list from stack name or explicit list.

    Args:
        stack_name: Stack preset name (e.g., "django_next") OR comma-separated
                   list of backends (e.g., "django_api,nextjs,docker")
        explicit_backends: Explicit backend list (overrides stack)

    Returns:
        List of backend names to execute

    Raises:
        StackError: If stack not found or invalid
    """
    # Explicit backends take precedence
    if explicit_backends:
        return explicit_backends

    # Parse stack_name
    if stack_name:
        # Check if it's a comma-separated list first
        if "," in stack_name:
            # Custom stack: comma-separated backend list
            return [b.strip() for b in stack_name.split(",")]

        # Try to look up as preset
        preset = get_stack_preset(stack_name)
        if preset:
            return preset.backends

        # Not a preset, treat as single backend name
        # (allows users to specify single backends like "openapi")
        return [stack_name]

    # No stack or backends specified
    return []


def validate_stack_backends(backends: list[str]) -> None:
    """
    Validate that all backends in the list exist.

    Args:
        backends: List of backend names

    Raises:
        StackError: If any backend is not registered
    """
    from ..stacks import list_backends

    available_backends = set(list_backends())

    for backend in backends:
        if backend not in available_backends:
            raise StackError(
                f"Backend '{backend}' not found. "
                f"Available backends: {', '.join(sorted(available_backends))}"
            )


def get_stack_description(stack_name: str) -> str:
    """
    Get human-readable description of a stack.

    Args:
        stack_name: Stack name

    Returns:
        Stack description with backend list
    """
    preset = get_stack_preset(stack_name)
    if not preset:
        return f"Unknown stack: {stack_name}"

    backend_list = ", ".join(preset.backends)
    return f"{preset.description}\nBackends: {backend_list}"


__all__ = [
    "StackError",
    "StackPreset",
    "BUILTIN_STACKS",
    "DEFAULT_DEMO_STACK",
    "get_stack_preset",
    "list_stack_presets",
    "resolve_stack_backends",
    "validate_stack_backends",
    "get_stack_description",
]
