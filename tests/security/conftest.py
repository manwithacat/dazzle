"""Shared fixtures for OWASP ASVS security tests."""

import pytest


@pytest.fixture
def security_profiles():
    """Return all supported security profile names."""
    return ["basic", "standard", "strict"]
