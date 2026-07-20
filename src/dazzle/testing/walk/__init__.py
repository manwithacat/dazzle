"""Story-driven scene walks (#1638).

Deterministic persona job paths for CI — between ``dsl-run`` / surface smoke
and LLM journeys. Package home: ``dazzle.testing.walk`` (not ``agent``).

PR1: models, JSON Schema, loader, ``dazzle test walk list|validate``.
PR2+: runner, claim registry check, pack dry-run, agent seed residuals.
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
from dazzle.testing.walk.validate import WalkValidationIssue, validate_walk, validate_walks

__all__ = [
    "CORE_ACTION_TYPES",
    "ActionSpec",
    "SceneSpec",
    "SceneWalkSpec",
    "WalkActionType",
    "WalkLoadError",
    "WalkValidationIssue",
    "default_walks_dir",
    "discover_walk_paths",
    "load_walk",
    "load_walks",
    "validate_walk",
    "validate_walks",
]
