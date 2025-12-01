"""
Prompt definitions for DAZZLE MCP server.

Prompts are reusable instructions that Claude Code can invoke as slash commands.
"""

from typing import Any


def create_prompts() -> list[dict[str, Any]]:
    """
    Create available prompts/slash commands for the MCP server.

    Returns:
        List of prompt definitions with name, description, and arguments
    """
    return [
        {
            "name": "validate",
            "description": "Validate the DAZZLE project DSL and report any errors",
            "arguments": [],
        },
        {
            "name": "review_dsl",
            "description": "Review DSL design and suggest improvements",
            "arguments": [
                {
                    "name": "aspect",
                    "description": "Aspect to review: design, performance, security, or all",
                    "required": False,
                }
            ],
        },
        {
            "name": "code_review",
            "description": "Review generated code artifacts for quality and best practices. NOTE: DNR is the primary runtime - use code generation only for custom deployments.",
            "arguments": [
                {
                    "name": "stack",
                    "description": "Stack to review (docker, base). Legacy stacks (django_micro_modular, etc.) are deprecated.",
                    "required": True,
                }
            ],
        },
        {
            "name": "suggest_surfaces",
            "description": "Suggest surface definitions for an entity based on CRUD patterns",
            "arguments": [
                {
                    "name": "entity_name",
                    "description": "Name of the entity to suggest surfaces for",
                    "required": True,
                }
            ],
        },
        {
            "name": "optimize_dsl",
            "description": "Suggest optimizations for DSL based on patterns and best practices",
            "arguments": [],
        },
    ]
