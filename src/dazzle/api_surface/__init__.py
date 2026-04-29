"""
API surface introspection — for the breaking-change pass tooling.

The framework's public surface is enumerated and snapshotted as a structured
text artifact. Drift between the live surface and the on-disk baseline is
caught by tests/unit/test_api_surface_drift.py, forcing every breaking change
to be a conscious decision.

Cycle 1 covers DSL constructs only. See `docs/api-surface/dsl-constructs.txt`
for the committed baseline. See issue #961 for cycle 2+ scope.
"""

from .dsl_constructs import (
    BASELINE_PATH,
    diff_against_baseline,
    snapshot_dsl_constructs,
)

__all__ = [
    "BASELINE_PATH",
    "diff_against_baseline",
    "snapshot_dsl_constructs",
]
