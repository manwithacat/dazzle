"""
Process and coverage tool handlers for MCP server.

Handles process inspection, story coverage analysis, process proposal generation,
and process run monitoring.
"""

from ._helpers import _get_process_adapter, _load_app_spec
from .coverage import (
    CRUD_OUTCOME_PATTERNS,
    UI_FEEDBACK_PATTERNS,
    CoverageReport,
    StoryCoverage,
    _collect_process_match_pool,
    _find_missing_aspects,
    _find_missing_aspects_from_index,
    _infer_structural_satisfaction,
    _outcome_matches_pool,
    stories_coverage_handler,
)
from .diagrams import (
    FLOW_COMPLETE_KEYWORDS,
    FLOW_FAILURE_KEYWORDS,
    get_process_diagram_handler,
)
from .inspection import (
    inspect_process_handler,
    list_processes_handler,
)
from .proposals import (
    WorkflowProposal,
    _build_review_checklist,
    _cluster_stories_into_workflows,
    _is_crud_story,
    _slugify,
    propose_processes_handler,
)
from .storage import (
    ProcessRunSummary,
    _get_run_async,
    _list_runs_async,
    get_process_run_handler,
    list_process_runs_handler,
    save_processes_handler,
)

__all__ = [
    # Coverage
    "StoryCoverage",
    "CoverageReport",
    "stories_coverage_handler",
    "CRUD_OUTCOME_PATTERNS",
    "UI_FEEDBACK_PATTERNS",
    "_collect_process_match_pool",
    "_find_missing_aspects",
    "_find_missing_aspects_from_index",
    "_infer_structural_satisfaction",
    "_outcome_matches_pool",
    # Diagrams
    "FLOW_COMPLETE_KEYWORDS",
    "FLOW_FAILURE_KEYWORDS",
    "get_process_diagram_handler",
    # Inspection
    "inspect_process_handler",
    "list_processes_handler",
    # Proposals
    "WorkflowProposal",
    "propose_processes_handler",
    "_is_crud_story",
    "_slugify",
    "_cluster_stories_into_workflows",
    "_build_review_checklist",
    # Storage / Runs
    "ProcessRunSummary",
    "save_processes_handler",
    "list_process_runs_handler",
    "get_process_run_handler",
    "_list_runs_async",
    "_get_run_async",
]
