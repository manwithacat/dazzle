"""Backward-compatible import aggregator for MCP handler utilities.

Functions have been moved to domain-specific modules:
- ``text_utils``: slugify, extract_issue_key
- ``process/_helpers``: get_process_adapter
- ``discovery/_helpers``: load_report_data, deserialize_observations

This module re-exports everything so existing imports continue to work.
"""

from __future__ import annotations

from .discovery._helpers import deserialize_observations, load_report_data
from .process._helpers import get_process_adapter
from .text_utils import extract_issue_key, slugify

__all__ = [
    "slugify",
    "extract_issue_key",
    "get_process_adapter",
    "load_report_data",
    "deserialize_observations",
]
