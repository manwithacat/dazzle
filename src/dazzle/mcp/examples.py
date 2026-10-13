"""
Example project metadata for DAZZLE MCP server.

Provides searchable information about example projects and what DSL features they demonstrate.
"""

from typing import Any


def get_example_metadata() -> dict[str, Any]:
    """
    Get metadata about all DAZZLE example projects.

    Returns a dictionary mapping example names to their metadata,
    including what features they demonstrate.
    """
    return {
        "simple_task": {
            "name": "simple_task",
            "path": "examples/simple_task",
            "title": "Simple Task Manager",
            "description": "Basic task management system demonstrating core DAZZLE concepts",
            "demonstrates": [
                "entities",
                "surfaces",
                "basic_crud",
                "enum_fields",
                "datetime_fields",
                "ux_block",
                "workspace",
                "persona",
                "attention_signals",
            ],
            "v0_2_features": ["ux_block", "workspace", "persona", "purpose_statements"],
            "complexity": "beginner",
            "entities": ["Task"],
            "surfaces": ["task_list", "task_create", "task_edit", "task_detail"],
            "workspaces": ["task_dashboard", "my_workspace"],
            "ci_status": "P0",
        },
        "support_tickets": {
            "name": "support_tickets",
            "path": "examples/support_tickets",
            "title": "Support Ticket System",
            "description": "Customer support system with multiple personas and attention signals",
            "demonstrates": [
                "entities",
                "relationships",
                "surfaces",
                "complete_crud",
                "ux_block",
                "workspace",
                "persona",
                "attention_signals",
                "information_needs",
                "scope_filtering",
                "aggregates",
            ],
            "v0_2_features": [
                "ux_block",
                "workspace",
                "persona",
                "attention_signals",
                "purpose_statements",
                "scope_filtering",
                "persona_specific_workspaces",
                "aggregates",
            ],
            "complexity": "intermediate",
            "entities": ["Ticket", "Customer", "Agent", "Comment"],
            "surfaces": ["ticket_list", "ticket_create", "ticket_edit", "ticket_detail"],
            "workspaces": ["agent_dashboard", "manager_dashboard", "customer_portal"],
            "personas": ["agent", "manager", "customer"],
            "use_cases": [
                "Role-based dashboards",
                "Multi-persona workflows",
                "Attention signal usage",
                "Workspace composition",
            ],
            "ci_status": "P1",
        },
    }


def search_examples(
    features: list[str] | None = None, complexity: str | None = None
) -> list[dict[str, Any]]:
    """
    Search for example projects by features or complexity.

    Args:
        features: List of features to search for (e.g., ['persona', 'workspace'])
        complexity: Complexity level ('beginner', 'intermediate', 'advanced')

    Returns:
        List of matching examples with metadata
    """
    examples = get_example_metadata()
    results = []

    for _example_name, metadata in examples.items():
        # Filter by complexity if specified
        if complexity and metadata.get("complexity") != complexity:
            continue

        # Filter by features if specified
        if features:
            # Normalize feature names
            normalized_features = [f.lower().replace("-", "_") for f in features]
            demonstrates = metadata.get("demonstrates", [])
            v0_2_features = metadata.get("v0_2_features", [])
            all_features = demonstrates + v0_2_features

            # Check if example demonstrates any of the requested features
            if not any(feature in all_features for feature in normalized_features):
                continue

        results.append(
            {
                "name": metadata["name"],
                "title": metadata["title"],
                "path": metadata["path"],
                "description": metadata["description"],
                "demonstrates": metadata.get("demonstrates", []),
                "v0_2_features": metadata.get("v0_2_features", []),
                "complexity": metadata.get("complexity"),
                "uri": f"dazzle://examples/{metadata['name']}",
            }
        )

    return results
