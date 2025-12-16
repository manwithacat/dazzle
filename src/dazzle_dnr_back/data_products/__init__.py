"""
Data Products module for DAZZLE.

Provides curated data pipelines with:
- Classification-based field filtering
- Transform application (minimise, pseudonymise, aggregate, mask)
- Separate topic namespace for curated streams
- Cross-tenant aggregation controls

Part of v0.18.0 Event-First Architecture (Issue #25, Phase G).
"""

from dazzle_dnr_back.data_products.cross_tenant import (
    CrossTenantPolicy,
    CrossTenantValidator,
)
from dazzle_dnr_back.data_products.curated_topics import (
    CuratedTopicConfig,
    CuratedTopicGenerator,
    FieldFilter,
    generate_curated_topics,
)
from dazzle_dnr_back.data_products.test_generator import (
    PolicyTestCase,
    PolicyTestGenerator,
    PolicyTestSuite,
    generate_policy_tests,
)
from dazzle_dnr_back.data_products.transformer import (
    DataProductTransformer,
    TransformResult,
)

__all__ = [
    # Curated topics
    "CuratedTopicConfig",
    "CuratedTopicGenerator",
    "FieldFilter",
    "generate_curated_topics",
    # Transformer
    "DataProductTransformer",
    "TransformResult",
    # Cross-tenant
    "CrossTenantPolicy",
    "CrossTenantValidator",
    # Test generation
    "PolicyTestCase",
    "PolicyTestGenerator",
    "PolicyTestSuite",
    "generate_policy_tests",
]
