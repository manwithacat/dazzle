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

# #1438: register the pack-ops provider into core's validation registry (below) so
# core never imports this tooling layer (core ↛ api_kb/mcp). Imported at top to keep
# the module import-order clean; the registration call runs at module end.
from dazzle.core.validation.surfaces import register_pack_ops_provider as _register

from .loader import (
    ApiPack,
    DockerSpec,
    EnvVarSpec,
    InfrastructureSpec,
    OperationSpec,
    SandboxSpec,
    list_packs,
    load_pack,
    search_packs,
)

__all__ = [
    "ApiPack",
    "DockerSpec",
    "EnvVarSpec",
    "InfrastructureSpec",
    "OperationSpec",
    "SandboxSpec",
    "load_pack",
    "list_packs",
    "search_packs",
]


def _pack_ops_provider() -> dict[str, set[str]]:
    """The ``{pack_name: {operation_names}}`` map for core's #996 source= typo check."""
    return {p.name: {getattr(op, "name", str(op)) for op in p.operations} for p in list_packs()}


# Activate the registration (the import-time inversion: api_kb → core, never the
# reverse). Mirrors how dazzle.mcp registers into core.docs_gen.
_register(_pack_ops_provider)
