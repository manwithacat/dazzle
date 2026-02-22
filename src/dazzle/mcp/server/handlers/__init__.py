"""
MCP Server tool handlers package.

This package splits the tool handlers into domain-specific modules
for better maintainability.
"""

from .api_packs import (
    generate_service_dsl_handler,
    get_api_pack_handler,
    get_env_vars_for_packs_handler,
    list_api_packs_handler,
    search_api_packs_handler,
)
from .bootstrap import handle_bootstrap
from .dsl import (
    analyze_patterns,
    get_unified_issues,
    inspect_entity,
    inspect_surface,
    lint_project,
    list_modules,
    validate_dsl,
)
from .knowledge import (
    find_examples_handler,
    get_cli_help_handler,
    get_workflow_guide_handler,
    lookup_concept_handler,
    lookup_inference_handler,
)
from .project import (
    get_active_project_info,
    list_projects,
    load_appspec_for_project,
    select_project,
    validate_all_projects,
)
from .spec_analyze import handle_spec_analyze
from .status import (
    get_dnr_logs_handler,
    get_mcp_status_handler,
)
from .stories import (
    get_dsl_spec_handler,
    get_stories_handler,
    propose_stories_from_dsl_handler,
    save_stories_handler,
)
from .testing import (
    get_e2e_test_coverage_handler,
    get_test_tier_guidance_handler,
    list_e2e_flows_handler,
    run_agent_e2e_tests_handler,
    run_e2e_tests_handler,
)

__all__ = [
    # Project handlers
    "list_projects",
    "load_appspec_for_project",
    "select_project",
    "get_active_project_info",
    "validate_all_projects",
    # DSL handlers
    "validate_dsl",
    "list_modules",
    "inspect_entity",
    "inspect_surface",
    "analyze_patterns",
    "lint_project",
    "get_unified_issues",
    # Knowledge handlers
    "lookup_concept_handler",
    "find_examples_handler",
    "get_cli_help_handler",
    "get_workflow_guide_handler",
    "lookup_inference_handler",
    # Status handlers
    "get_mcp_status_handler",
    "get_dnr_logs_handler",
    # API pack handlers
    "list_api_packs_handler",
    "search_api_packs_handler",
    "get_api_pack_handler",
    "generate_service_dsl_handler",
    "get_env_vars_for_packs_handler",
    # Story handlers
    "get_dsl_spec_handler",
    "propose_stories_from_dsl_handler",
    "save_stories_handler",
    "get_stories_handler",
    # Testing handlers
    "run_e2e_tests_handler",
    "run_agent_e2e_tests_handler",
    "get_e2e_test_coverage_handler",
    "list_e2e_flows_handler",
    "get_test_tier_guidance_handler",
    # Spec analyze handlers
    "handle_spec_analyze",
    # Bootstrap handler
    "handle_bootstrap",
]
