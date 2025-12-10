"""
Project initialization utilities for DAZZLE.

This package contains modular implementations for project initialization:
- validation.py - Name validation and sanitization
- templates.py - Template copying and variable substitution
- spec.py - SPEC.md template generation
- dnr_ui.py - DNR UI generation from DSL
- project.py - Main init_project logic
- reset.py - Project reset and verification
"""

from __future__ import annotations

from .validation import (
    RESERVED_KEYWORDS,
    InitError,
    sanitize_name,
    validate_project_name,
)
from .templates import (
    GENERATED_DIRECTORIES,
    copy_template,
    substitute_template_vars,
)
from .spec import create_spec_template
from .dnr_ui import generate_dnr_ui
from .project import create_mcp_config, init_project, list_examples
from .reset import reset_project, verify_project

__all__ = [
    # Errors
    "InitError",
    # Validation
    "RESERVED_KEYWORDS",
    "validate_project_name",
    "sanitize_name",
    # Templates
    "GENERATED_DIRECTORIES",
    "substitute_template_vars",
    "copy_template",
    # Spec
    "create_spec_template",
    # DNR UI
    "generate_dnr_ui",
    # Project init
    "list_examples",
    "create_mcp_config",
    "init_project",
    # Reset
    "reset_project",
    "verify_project",
]
