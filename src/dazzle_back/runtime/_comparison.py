"""
Shared comparison utilities for runtime evaluators.

Provides common value normalization and operator dispatch used by
condition_evaluator, access_evaluator, and invariant_evaluator.

The canonical implementation lives in dazzle.core.comparison — this module
re-exports it so that dazzle_back callers continue to work unchanged.
"""

from __future__ import annotations

from dazzle.core.comparison import eval_comparison_op as eval_comparison_op
from dazzle.core.comparison import normalize_for_comparison as normalize_for_comparison

__all__ = ["eval_comparison_op", "normalize_for_comparison"]
