"""
LLM Integration for DAZZLE.

This package provides LLM-assisted specification *analysis* — extracting
entities, personas, business rules and lifecycles from a SPEC.md and
returning them as structured data. Dazzle DSL synthesis is deliberately
**not** performed via external API call (#1222): the in-session agent
holds the framework-specific knowledge required to author DSL, and is
the right place to do that synthesis once analysis context is available.
"""

from .api_client import LLMAPIClient, LLMProvider
from .models import (
    BusinessRule,
    CRUDAnalysis,
    Question,
    SpecAnalysis,
    StateMachine,
    StateTransition,
)

__all__ = [
    "LLMAPIClient",
    "LLMProvider",
    "SpecAnalysis",
    "StateMachine",
    "StateTransition",
    "CRUDAnalysis",
    "BusinessRule",
    "Question",
]
