"""Story-driven scene walks (#1638).

Deterministic persona job paths for CI — between ``dsl-run`` / surface smoke
and LLM journeys. Package home: ``dazzle.testing.walk`` (not ``agent``).

PR1: models, JSON Schema, loader, ``list|validate``.
PR2: ``run`` (HTTP core actions + optional Playwright).
PR3+: claim registry check, pack dry-run, agent seed residuals.
"""

from __future__ import annotations

from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.loader import WalkLoadError, load_walk, load_walks
from dazzle.testing.walk.models import (
    CORE_ACTION_TYPES,
    ActionSpec,
    SceneSpec,
    SceneWalkSpec,
    WalkActionType,
)
from dazzle.testing.walk.runner import WalkRunner, WalkRunResult, run_walk, run_walk_sync
from dazzle.testing.walk.validate import WalkValidationIssue, validate_walk, validate_walks

__all__ = [
    "CORE_ACTION_TYPES",
    "ActionSpec",
    "SceneSpec",
    "SceneWalkSpec",
    "WalkActionType",
    "WalkLoadError",
    "WalkRunResult",
    "WalkRunner",
    "WalkValidationIssue",
    "default_walks_dir",
    "discover_walk_paths",
    "load_walk",
    "load_walks",
    "run_walk",
    "run_walk_sync",
    "validate_walk",
    "validate_walks",
]
