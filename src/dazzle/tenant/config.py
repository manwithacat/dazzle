"""Tenant configuration helpers — slug validation and schema naming."""

import re

# Max slug length: 63 (PG identifier limit) - 7 ("tenant_" prefix) = 56
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,55}$")
SCHEMA_PREFIX = "tenant_"


def validate_slug(slug: str) -> None:
    """Validate a tenant slug.

    Raises ValueError if the slug is invalid.
    """
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"Slug must match {SLUG_PATTERN.pattern}. Got: '{slug}'")


def slug_to_schema_name(slug: str) -> str:
    """Convert a tenant slug to a PostgreSQL schema name."""
    return f"{SCHEMA_PREFIX}{slug}"
