"""
Layout Plan Caching

Caches computed layout plans to speed up incremental builds.
Invalidates cache when DSL files or layout engine code changes.
"""

import hashlib
import json
from pathlib import Path

from ...core import ir
from .types import LayoutPlan


class LayoutPlanCache:
    """Cache for computed layout plans."""

    def __init__(self, cache_dir: Path):
        """
        Initialize layout plan cache.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, workspace: ir.WorkspaceLayout, engine_version: str = "0.3.0") -> str:
        """
        Compute hash for workspace + engine version.

        Args:
            workspace: Workspace layout to hash
            engine_version: Layout engine version

        Returns:
            SHA-256 hash string
        """
        # Serialize workspace to deterministic JSON
        workspace_dict = {
            "id": workspace.id,
            "label": workspace.label,
            "stage": workspace.stage,
            "attention_budget": workspace.attention_budget,
            "time_horizon": workspace.time_horizon,
            "signals": [
                {
                    "id": signal.id,
                    "kind": signal.kind.value,
                    "source": signal.source,
                    "label": signal.label,
                    "attention_weight": signal.attention_weight,
                }
                for signal in workspace.attention_signals
            ],
            "engine_version": engine_version,
        }

        # Compute hash
        json_str = json.dumps(workspace_dict, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """
        Get cache file path for key.

        Args:
            cache_key: Cache key (hash)

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{cache_key}.json"

    def get(self, workspace: ir.WorkspaceLayout) -> LayoutPlan | None:
        """
        Get cached layout plan for workspace.

        Args:
            workspace: Workspace layout

        Returns:
            Cached layout plan if found, None otherwise
        """
        cache_key = self._compute_hash(workspace)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            # Load cached plan
            with cache_path.open("r") as f:
                data = json.load(f)

            # Reconstruct LayoutPlan
            from dazzle.core.ir import LayoutSurface, Stage

            plan = LayoutPlan(
                workspace_id=data["workspace_id"],
                persona_id=data.get("persona_id"),
                stage=Stage(data["stage"]),
                surfaces=[
                    LayoutSurface(
                        id=s["id"],
                        stage=Stage(s["stage"]),
                        capacity=s["capacity"],
                        priority=s["priority"],
                        assigned_signals=s["assigned_signals"],
                    )
                    for s in data["surfaces"]
                ],
                over_budget_signals=data.get("over_budget_signals", []),
                warnings=data.get("warnings", []),
                metadata=data.get("metadata", {}),
            )

            return plan

        except (json.JSONDecodeError, KeyError, ValueError):
            # Cache corrupted, ignore
            return None

    def set(self, workspace: ir.WorkspaceLayout, plan: LayoutPlan) -> None:
        """
        Cache layout plan for workspace.

        Args:
            workspace: Workspace layout
            plan: Computed layout plan
        """
        cache_key = self._compute_hash(workspace)
        cache_path = self._get_cache_path(cache_key)

        # Serialize plan to JSON
        data = {
            "workspace_id": plan.workspace_id,
            "persona_id": plan.persona_id,
            "stage": plan.stage.value,
            "surfaces": [
                {
                    "id": s.id,
                    "stage": s.stage.value,
                    "capacity": s.capacity,
                    "priority": s.priority,
                    "assigned_signals": s.assigned_signals,
                }
                for s in plan.surfaces
            ],
            "over_budget_signals": plan.over_budget_signals,
            "warnings": plan.warnings,
            "metadata": plan.metadata,
        }

        # Write to cache
        with cache_path.open("w") as f:
            json.dump(data, f, indent=2)

    def clear(self) -> None:
        """Clear all cached layout plans."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

    def invalidate(self, workspace: ir.WorkspaceLayout) -> None:
        """
        Invalidate cached layout plan for specific workspace.

        Args:
            workspace: Workspace to invalidate
        """
        cache_key = self._compute_hash(workspace)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()


def get_layout_cache(project_root: Path) -> LayoutPlanCache:
    """
    Get layout plan cache for project.

    Args:
        project_root: Project root directory

    Returns:
        Layout plan cache instance
    """
    cache_dir = project_root / ".dazzle" / "cache" / "layout_plans"
    return LayoutPlanCache(cache_dir)


__all__ = ["LayoutPlanCache", "get_layout_cache"]
