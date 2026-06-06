"""Capability gating for advisory cognition surfaces (#1342 Phase 2).

These helpers decide what proactive surfaces (bootstrap, lint relevance,
spec-analyze proposals) may push. They are deliberately *non-raising*: an
advisory read must never crash a project on a malformed/incomplete manifest.

Pull surfaces (the ``knowledge`` MCP tool) do NOT use these — direct queries
always return content regardless of declared capabilities.
"""

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

from dazzle.core.capabilities.registry import active_capability_ids, get

logger = logging.getLogger(__name__)

T = TypeVar("T")


def active_capabilities_for(project_root: Path | str) -> set[str]:
    """Active capability ids declared in ``<project_root>/dazzle.toml``.

    Empty set when there is no manifest or it can't be read — advisory only,
    never raises into a cognition read.
    """
    path = Path(project_root) / "dazzle.toml"
    if not path.is_file():
        return set()
    try:
        from dazzle.core.manifest import load_manifest

        return active_capability_ids(load_manifest(path).capabilities.enabled)
    except Exception:
        # Malformed manifest must not break an advisory cognition read — but a
        # real bug shouldn't be fully invisible, so leave a breadcrumb.
        logger.debug("active_capabilities_for(%s) failed; treating as none", path, exc_info=True)
        return set()


def partition_by_capability(
    items: Iterable[T],
    active: set[str],
    capability_of: Callable[[T], str | None],
) -> tuple[list[T], list[tuple[T, str]]]:
    """Split ``items`` into ``(surfaced, gated)``.

    ``surfaced`` = ungated (capability ``None``) or whose capability is active.
    ``gated`` = ``(item, capability_id)`` for each item gated by an inactive
    capability — the caller turns these into enable-suggestions or drops them.
    """
    surfaced: list[T] = []
    gated: list[tuple[T, str]] = []
    for item in items:
        cap = capability_of(item)
        if cap is None or cap in active:
            surfaced.append(item)
        else:
            gated.append((item, cap))
    return surfaced, gated


def enable_suggestion(capability_id: str) -> dict[str, Any]:
    """A structured 'declare this capability' hint for a requirement the spec
    stated but the app hasn't opted into."""
    cap = get(capability_id)
    return {
        "capability": capability_id,
        "label": cap.label if cap else capability_id,
        "enable": f"dazzle capability enable {capability_id}",
        "remediation": cap.remediation if cap else "",
    }
