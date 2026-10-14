"""
LLM client for DAZZLE.

The provider client and cost table behind the runtime's ``llm_intent``
executor, and the driver resolution the agent and ``dazzle qa`` use. Dazzle
DSL synthesis is deliberately **not**
performed via external API call (#1222): the in-session agent holds the
framework-specific knowledge required to author DSL.
"""

from .api_client import LLMAPIClient, LLMProvider

__all__ = [
    "LLMAPIClient",
    "LLMProvider",
]
