"""
Tests for repository module.

Tests database creation, CRUD operations, and persistence.
Requires DATABASE_URL (PostgreSQL) to run.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping PostgreSQL repository tests",
)
