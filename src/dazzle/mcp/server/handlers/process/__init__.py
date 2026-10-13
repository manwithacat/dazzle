"""
Process and coverage handlers.

Story coverage and scope fidelity back the MCP ``story`` tool.
"""

from ._helpers import load_app_spec
from .coverage import (
    CRUD_OUTCOME_PATTERNS,
    UI_FEEDBACK_PATTERNS,
    CoverageReport,
    StoryCoverage,
    _collect_process_match_pool,
    _find_missing_aspects,
    _infer_structural_satisfaction,
    _outcome_matches_pool,
    stories_coverage_handler,
)
from .scope_fidelity import (
    ScopeGap,
    StoryScopeFidelity,
    scope_fidelity_handler,
    scope_fidelity_impl,
)

__all__ = [
    "load_app_spec",
    # Coverage
    "StoryCoverage",
    "CoverageReport",
    "stories_coverage_handler",
    "CRUD_OUTCOME_PATTERNS",
    "UI_FEEDBACK_PATTERNS",
    "_collect_process_match_pool",
    "_find_missing_aspects",
    "_infer_structural_satisfaction",
    "_outcome_matches_pool",
    # Proposals
    # Scope Fidelity
    "ScopeGap",
    "StoryScopeFidelity",
    "scope_fidelity_handler",
    "scope_fidelity_impl",
]
