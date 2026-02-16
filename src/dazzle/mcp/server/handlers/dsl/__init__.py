"""DSL analysis tool handlers.

Handles DSL validation, module listing, entity/surface inspection,
pattern analysis, and linting.

Split into submodules:
- validate: validate_dsl, lint_project, get_unified_issues, list_modules
- inspect: inspect_entity, inspect_surface
- analysis: analyze_patterns, export_frontend_spec_handler
"""

from ..text_utils import extract_issue_key as _extract_issue_key
from .analysis import analyze_patterns, export_frontend_spec_handler
from .inspect import inspect_entity, inspect_surface
from .validate import get_unified_issues, lint_project, list_modules, validate_dsl

__all__ = [
    "_extract_issue_key",
    "analyze_patterns",
    "export_frontend_spec_handler",
    "get_unified_issues",
    "inspect_entity",
    "inspect_surface",
    "lint_project",
    "list_modules",
    "validate_dsl",
]
