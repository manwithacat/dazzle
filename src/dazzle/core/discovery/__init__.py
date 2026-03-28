"""
Capability discovery for DAZZLE AppSpecs.
"""

from dazzle.core.discovery.engine import suggest_capabilities
from dazzle.core.discovery.models import ExampleRef, Relevance

__all__ = ["ExampleRef", "Relevance", "suggest_capabilities"]
