"""
Environment configuration for Dazzle runtime.

This module provides a standard way to determine the runtime environment
and configure dev-only features like the Dazzle Bar and test endpoints.

The DAZZLE_ENV environment variable follows the pattern established by:
- Rails: RAILS_ENV (development, test, production)
- Django: DEBUG + DJANGO_SETTINGS_MODULE
- Flask: FLASK_ENV (development, testing, production)
- Node.js: NODE_ENV (development, test, production)

Environment values:
    - development (default): All dev features enabled
    - test: Test endpoints enabled, Dazzle Bar disabled by default
    - production: All dev features disabled for security

Usage:
    from dazzle.core.environment import get_dazzle_env, should_enable_dazzle_bar

    env = get_dazzle_env()  # Returns "development", "test", or "production"

    # Check with manifest override
    if should_enable_dazzle_bar(manifest.dev.dazzle_bar):
        # Enable Dazzle Bar
        pass
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


def should_enable_dazzle_bar(manifest_override: bool | None = None) -> bool:
    """Determine if the Dazzle Bar should be enabled.

    Resolution order:
    1. If manifest_override is explicitly set (True/False), use it
    2. Otherwise, use environment defaults:
       - development: True
       - test: False (Dazzle Bar interferes with E2E tests)
       - production: False (security)

    Args:
        manifest_override: Explicit setting from dazzle.toml [dev] section.
            None means "use environment default".

    Returns:
        bool: Whether to enable the Dazzle Bar.

    Examples:
        # In development (DAZZLE_ENV not set)
        >>> should_enable_dazzle_bar(None)
        True

        # In production with no override
        >>> import os; os.environ["DAZZLE_ENV"] = "production"
        >>> should_enable_dazzle_bar(None)
        False

        # Force enable in production (not recommended!)
        >>> should_enable_dazzle_bar(True)
        True
    """
    # Explicit manifest setting takes precedence
    if manifest_override is not None:
        return manifest_override

    # Environment defaults
    env = get_dazzle_env()
    if env == DazzleEnv.PRODUCTION:
        return False
    elif env == DazzleEnv.TEST:
        return False  # Dazzle Bar interferes with E2E tests
    else:  # DEVELOPMENT
        return True


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
            - dazzle_bar_default: Default Dazzle Bar setting
            - test_endpoints_default: Default test endpoints setting
    """
    env = get_dazzle_env()
    return {
        "env": env.value,
        "dazzle_bar_default": should_enable_dazzle_bar(None),
        "test_endpoints_default": should_enable_test_endpoints(None),
    }
