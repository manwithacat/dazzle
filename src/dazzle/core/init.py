"""
Project initialization utilities for DAZZLE.

This module re-exports from init_impl/ package for backwards compatibility.
For implementation details, see the init_impl/ package.
"""

# Re-export everything from the init_impl package
from .init_impl import (
    GENERATED_DIRECTORIES,
    RESERVED_KEYWORDS,
    InitError,
    copy_template,
    create_mcp_config,
    create_spec_template,
    generate_dnr_ui,
    init_project,
    list_examples,
    reset_project,
    sanitize_name,
    substitute_template_vars,
    validate_project_name,
    verify_project,
)

__all__ = [
    "InitError",
    "RESERVED_KEYWORDS",
    "list_examples",
    "sanitize_name",
    "validate_project_name",
    "substitute_template_vars",
    "GENERATED_DIRECTORIES",
    "copy_template",
    "create_spec_template",
    "generate_dnr_ui",
    "create_mcp_config",
    "init_project",
    "verify_project",
    "reset_project",
]
