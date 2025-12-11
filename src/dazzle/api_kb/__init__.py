"""
DAZZLE API Knowledgebase (api_kb) - v0.10.0

Curated, pre-validated API configurations for common external services.

The API Knowledgebase provides:
- Pre-tested service configurations (no LLM hallucination)
- Environment variable requirements
- Foreign model schemas
- DSL generation templates

Usage:
    from dazzle.api_kb import load_pack, list_packs, search_packs

    # Load a specific pack
    pack = load_pack("stripe_payments")

    # List all available packs
    packs = list_packs()

    # Search by category or provider
    payment_packs = search_packs(category="payments")
    stripe_packs = search_packs(provider="Stripe")
"""

from .loader import (
    ApiPack,
    EnvVarSpec,
    OperationSpec,
    list_packs,
    load_pack,
    search_packs,
)

__all__ = [
    "ApiPack",
    "EnvVarSpec",
    "OperationSpec",
    "load_pack",
    "list_packs",
    "search_packs",
]
