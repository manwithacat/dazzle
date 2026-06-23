"""
Environment configuration for Dazzle runtime.

This module provides a standard way to determine the runtime environment
and configure dev-only features like test endpoints.

The DAZZLE_ENV environment variable follows the pattern established by:
- Rails: RAILS_ENV (development, test, production)
- Django: DEBUG + DJANGO_SETTINGS_MODULE
- Flask: FLASK_ENV (development, testing, production)
- Node.js: NODE_ENV (development, test, production)

Environment values:
    - development (default): All dev features enabled
    - test: Test endpoints enabled
    - production: All dev features disabled for security

Usage:
    from dazzle.core.environment import get_dazzle_env

    env = get_dazzle_env()  # Returns "development", "test", or "production"
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DazzleEnv(StrEnum):
    """Runtime environment values."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


# Default environment
_DEFAULT_ENV = DazzleEnv.DEVELOPMENT

# Environment variable name (follows Rails/Django/Flask patterns)
DAZZLE_ENV_VAR = "DAZZLE_ENV"


def get_dazzle_env() -> DazzleEnv:
    """Get the current Dazzle environment from DAZZLE_ENV.

    Returns:
        DazzleEnv: The current environment (development, test, or production).
        Defaults to development if DAZZLE_ENV is not set or invalid.

    Examples:
        >>> import os
        >>> os.environ["DAZZLE_ENV"] = "production"
        >>> get_dazzle_env()
        <DazzleEnv.PRODUCTION: 'production'>
    """
    env_value = os.environ.get(DAZZLE_ENV_VAR, "").lower().strip()

    if env_value == "production" or env_value == "prod":
        return DazzleEnv.PRODUCTION
    elif env_value == "test" or env_value == "testing":
        return DazzleEnv.TEST
    elif env_value == "development" or env_value == "dev" or env_value == "":
        return DazzleEnv.DEVELOPMENT
    else:
        # Unknown value - default to development with warning
        import logging

        logging.getLogger(__name__).warning(
            "Unknown DAZZLE_ENV value '%s'. "
            "Valid values: development, test, production. Defaulting to development.",
            env_value,
        )
        return DazzleEnv.DEVELOPMENT


def is_production() -> bool:
    """Check if running in production environment."""
    return get_dazzle_env() == DazzleEnv.PRODUCTION


def is_development() -> bool:
    """Check if running in development environment."""
    return get_dazzle_env() == DazzleEnv.DEVELOPMENT


def is_test() -> bool:
    """Check if running in test environment."""
    return get_dazzle_env() == DazzleEnv.TEST


def skip_boot_schema_ddl() -> bool:
    """True when framework stores must NOT run schema DDL at boot (#1462).

    In production the app-DB schema is owned by Alembic migrations (ADR-0044's
    ``ensure_framework_schema`` baseline creates every framework table + index),
    and the runtime may connect as a NON-OWNER role — under ``shared_schema`` RLS
    the serving role is ``dazzle_app`` (``NOSUPERUSER NOBYPASSRLS``) so RLS is
    actually enforced. That role cannot run ``CREATE``/``ALTER TABLE``/``CREATE
    INDEX``, so a store that runs DDL in its ``_init_db`` at boot halts startup.

    This mirrors the DSL ``create_all`` gate (server's
    ``_should_create_schema_on_startup`` = ``not is_production()``): framework
    stores skip boot DDL in production and rely on the migration-managed schema.
    """
    return is_production()


def pin_production_env() -> None:
    """#1420: pin ``DAZZLE_ENV=production`` when it is unset.

    Production entry points that establish production by some *other* signal —
    ``create_app_factory`` (uvicorn ``--factory``) which defaults an unset
    ``DAZZLE_ENV`` to production, and ``dazzle serve --production`` — must make
    that intent visible to every downstream ``is_production()`` read. Otherwise
    the fail-closed auth guard (which reads ``DAZZLE_ENV`` directly) misses them
    and an auth-disabled prod boot proceeds world-writable. ``setdefault`` never
    overrides an explicitly-set value, so dev/test are unaffected.
    """
    os.environ.setdefault(DAZZLE_ENV_VAR, DazzleEnv.PRODUCTION.value)


def should_enable_test_endpoints(manifest_override: bool | None = None) -> bool:
    """Determine if test endpoints (/__test__/*) should be enabled.

    Resolution order:
    1. If manifest_override is explicitly set (True/False), use it
    2. Otherwise, use environment defaults:
       - development: True
       - test: True (needed for E2E test setup)
       - production: False (security)

    Args:
        manifest_override: Explicit setting from dazzle.toml [dev] section.
            None means "use environment default".

    Returns:
        bool: Whether to enable test endpoints.

    Examples:
        # In development
        >>> should_enable_test_endpoints(None)
        True

        # In production
        >>> import os; os.environ["DAZZLE_ENV"] = "production"
        >>> should_enable_test_endpoints(None)
        False
    """
    # Explicit manifest setting takes precedence
    if manifest_override is not None:
        return manifest_override

    # Environment defaults
    env = get_dazzle_env()
    if env == DazzleEnv.PRODUCTION:
        return False
    else:  # DEVELOPMENT or TEST
        return True


def get_environment_info() -> dict[str, str | bool]:
    """Get a summary of the current environment configuration.

    Useful for debugging and startup logging.

    Returns:
        dict: Environment information including:
            - env: Current DAZZLE_ENV value
            - test_endpoints_default: Default test endpoints setting
    """
    env = get_dazzle_env()
    return {
        "env": env.value,
        "test_endpoints_default": should_enable_test_endpoints(None),
    }
