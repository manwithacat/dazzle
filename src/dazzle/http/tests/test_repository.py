"""
Tests for repository module.

Tests database creation, CRUD operations, and persistence.
Requires DATABASE_URL (PostgreSQL) to run.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping PostgreSQL repository tests",
)
