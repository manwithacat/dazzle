"""
LLM Integration for DAZZLE.

This package provides LLM-assisted specification analysis and DSL generation.
Supports both API mode (Anthropic, OpenAI) and CLI handoff mode.
"""

from .api_client import LLMAPIClient, LLMProvider
from .spec_analyzer import SpecAnalyzer, SpecAnalysis
from .dsl_generator import DSLGenerator, generate_dsl_from_analysis
from .models import (
    StateMachine,
    StateTransition,
    CRUDAnalysis,
    BusinessRule,
    Question,
)

__all__ = [
    'LLMAPIClient',
    'LLMProvider',
    'SpecAnalyzer',
    'SpecAnalysis',
    'DSLGenerator',
    'generate_dsl_from_analysis',
    'StateMachine',
    'StateTransition',
    'CRUDAnalysis',
    'BusinessRule',
    'Question',
]
