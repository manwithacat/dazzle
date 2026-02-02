"""
Stack Adapters for Dazzle E2E Testing.

Adapters provide stack-specific implementations for test operations
like seeding data, resetting state, and making API calls.
"""

from dazzle_e2e.adapters.base import BaseAdapter
from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter

__all__ = ["BaseAdapter", "DazzleAdapter"]
