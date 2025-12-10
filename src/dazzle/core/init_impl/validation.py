"""
Project name validation and sanitization.

Handles validation of project names against reserved keywords and
conversion to valid Python module names.
"""

from __future__ import annotations

import re

from ..errors import DazzleError


class InitError(DazzleError):
    """Raised when project initialization fails."""

    pass


# Reserved keywords that can't be used as project/module names
RESERVED_KEYWORDS = {
    # DSL keywords
    "app",
    "module",
    "entity",
    "surface",
    "experience",
    "service",
    "foreign_model",
    "integration",
    "test",
    "use",
    "section",
    "field",
    "action",
    "step",
    "transition",
    # Python keywords
    "import",
    "from",
    "def",
    "class",
    "if",
    "else",
    "elif",
    "for",
    "while",
    "break",
    "continue",
    "return",
    "yield",
    "try",
    "except",
    "finally",
    "with",
    "as",
    "raise",
    "assert",
    "del",
    "pass",
    "lambda",
    "global",
    "nonlocal",
    "and",
    "or",
    "not",
    "in",
    "is",
    # Common problematic names
    "true",
    "false",
    "null",
    "none",
    "type",
    "list",
    "dict",
    "set",
    "str",
    "int",
    "float",
    "bool",
    "tuple",
    "range",
    "object",
    # Django/Python stdlib conflicts
    "admin",
    "auth",
    "models",
    "views",
    "urls",
    "settings",
    "forms",
    "serializers",
    "tests",
    "migrations",
    "static",
    "templates",
}


def validate_project_name(name: str) -> tuple[bool, str | None]:
    """
    Validate a project name.

    Args:
        name: Project name to validate

    Returns:
        (is_valid, error_message)

    Examples:
        validate_project_name("test")  # -> (False, "...")
        validate_project_name("my_app")  # -> (True, None)
    """
    if not name:
        return (False, "Project name cannot be empty")

    # Check if it starts with a digit
    if name[0].isdigit():
        return (
            False,
            f"Project name '{name}' cannot start with a digit. Try 'project_{name}' or '{name}_app'",
        )

    # Check reserved keywords
    if name.lower() in RESERVED_KEYWORDS:
        return (
            False,
            f"Project name '{name}' is a reserved keyword. Try '{name}_app', 'my_{name}', or '{name}_project' instead",
        )

    # Check if it's a valid Python identifier pattern
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        return (
            False,
            f"Project name '{name}' must contain only letters, numbers, and underscores, and cannot start with a number",
        )

    return (True, None)


def sanitize_name(name: str, validate: bool = True) -> str:
    """
    Convert a project name to a valid Python module name.

    Args:
        name: Project name (can include spaces, hyphens)
        validate: If True, raises InitError for reserved keywords

    Returns:
        Valid Python identifier (lowercase, underscores)

    Raises:
        InitError: If validate=True and name is reserved keyword

    Examples:
        "My Project" -> "my_project"
        "my-app" -> "my_app"
        "MyApp" -> "myapp"
    """
    # Convert to lowercase
    name = name.lower()
    # Replace non-alphanumeric with underscores
    name = re.sub(r"[^a-z0-9_]", "_", name)
    # Remove leading/trailing underscores
    name = name.strip("_")
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)

    # Ensure doesn't start with digit
    if name and name[0].isdigit():
        name = f"project_{name}"

    final_name = name or "my_project"

    # Validate if requested
    if validate:
        is_valid, error_msg = validate_project_name(final_name)
        if not is_valid:
            raise InitError(error_msg or "Invalid project name")

    return final_name
