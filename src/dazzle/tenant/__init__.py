"""Schema-per-tenant isolation for Dazzle apps.

Opt-in via dazzle.toml:
    [tenant]
    isolation = "schema"
    resolver = "subdomain"
"""

from .cache_registry import _active_caches, _clear_registry, _register_cache, bust
from .config import (
    RESERVED_SLUG_PREFIXES,
    SLUG_PATTERN,
    slug_to_schema_name,
    validate_slug,
)
from .provisioner import TenantProvisioner
from .registry import TenantRecord, TenantRegistry

__all__ = [
    "RESERVED_SLUG_PREFIXES",
    "SLUG_PATTERN",
    "TenantProvisioner",
    "TenantRecord",
    "TenantRegistry",
    # #1289 slice 6: tenant_host cache invalidation
    "bust",
    "slug_to_schema_name",
    "validate_slug",
]
