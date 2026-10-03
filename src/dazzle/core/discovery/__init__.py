"""
Capability discovery for DAZZLE AppSpecs.
"""

from dazzle.core.discovery.engine import fold_relevance, suggest_capabilities
from dazzle.core.discovery.models import ExampleRef, Relevance, RelevanceGroup

__all__ = [
    "ExampleRef",
    "Relevance",
    "RelevanceGroup",
    "fold_relevance",
    "suggest_capabilities",
]
