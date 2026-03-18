"""Schema-per-tenant isolation for Dazzle apps.

Opt-in via dazzle.toml:
    [tenant]
    isolation = "schema"
    resolver = "subdomain"
"""

from .config import SLUG_PATTERN, slug_to_schema_name, validate_slug
from .provisioner import TenantProvisioner
from .registry import TenantRecord, TenantRegistry

__all__ = [
    "SLUG_PATTERN",
    "TenantProvisioner",
    "TenantRecord",
    "TenantRegistry",
    "slug_to_schema_name",
    "validate_slug",
]
