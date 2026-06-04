"""Tenant configuration helpers — slug validation and schema naming."""

import re

# Max slug length: 63 (PG identifier limit) - 7 ("tenant_" prefix) = 56
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,55}$")
SCHEMA_PREFIX = "tenant_"

# Slugs in the `qa` namespace are reserved for ephemeral test tenants
# (#1339). Both separators are reserved: `qa-` is the spec's human-visible
# marker (already grammar-invalid since hyphens are forbidden, but checked
# first for a clearer error), and `qa_` is the grammar-valid form a normal
# create could otherwise claim. The load-bearing test-tenant marker is the
# queryable `is_test` column on the tenant record, not this prefix
# (belt-and-suspenders — see docs/superpowers/specs/2026-06-04-tenant-lifecycle-design.md §5).
RESERVED_SLUG_PREFIXES = ("qa-", "qa_")


def validate_slug(slug: str, *, allow_reserved: bool = False) -> None:
    """Validate a tenant slug.

    Raises ValueError if the slug is invalid or claims the reserved `qa`
    namespace. Pass ``allow_reserved=True`` only from the test-tenant
    provisioner, which is permitted to mint `qa`-namespaced slugs.
    """
    if not allow_reserved and slug.startswith(RESERVED_SLUG_PREFIXES):
        raise ValueError(
            f"Slug prefix is reserved for test tenants ({', '.join(RESERVED_SLUG_PREFIXES)}). "
            f"Got: '{slug}'"
        )
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"Slug must match {SLUG_PATTERN.pattern}. Got: '{slug}'")


def slug_to_schema_name(slug: str) -> str:
    """Convert a tenant slug to a PostgreSQL schema name."""
    return f"{SCHEMA_PREFIX}{slug}"
