"""
Process and coverage handlers.

Story coverage and scope fidelity back the MCP ``story`` tool; process
proposal, save and diagram implementations back the ``dazzle process`` CLI.
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
from .diagrams import (
    FLOW_COMPLETE_KEYWORDS,
    FLOW_FAILURE_KEYWORDS,
)
from .proposals import (
    WorkflowProposal,
    _build_review_checklist,
    _cluster_stories_into_workflows,
    _is_crud_story,
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
    # Diagrams
    "FLOW_COMPLETE_KEYWORDS",
    "FLOW_FAILURE_KEYWORDS",
    # Proposals
    "WorkflowProposal",
    "_is_crud_story",
    "_cluster_stories_into_workflows",
    "_build_review_checklist",
    # Scope Fidelity
    "ScopeGap",
    "StoryScopeFidelity",
    "scope_fidelity_handler",
    "scope_fidelity_impl",
]
