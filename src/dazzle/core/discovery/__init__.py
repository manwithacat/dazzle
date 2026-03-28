"""
Capability discovery for DAZZLE AppSpecs.

Surfaces relevant capabilities (widgets, layouts, components, completeness gaps)
by scanning an AppSpec against domain rule modules and joining with example
references from working apps.
"""

from dazzle.core.discovery.models import ExampleRef, Relevance

__all__ = ["ExampleRef", "Relevance", "suggest_capabilities"]


def suggest_capabilities(
    appspec: "object",
    *,
    examples_dir: "object | None" = None,
    suppress: bool = False,
) -> "list[Relevance]":
    """Placeholder — implemented in Task 7."""
    return []
