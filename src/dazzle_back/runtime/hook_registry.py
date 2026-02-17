"""Service hook registry for project-level lifecycle extensions (v0.29.0).

Discovers Python hook files in the project ``hooks/`` directory,
validates declaration headers, and registers them with entity services
for pre/post lifecycle interception.

Hook files use declaration headers::

    # dazzle:service-hook entity.pre_create
    # dazzle:entity Task

    async def hook(entity_name: str, data: dict) -> dict:
        '''Enrich task data before creation.'''
        data["created_source"] = "api"
        return data

Supported hook points:

- ``entity.pre_create``  — called before create, receives ``(entity_name, data)``
                           returns modified data dict (or original)
- ``entity.post_create`` — called after create, receives ``(entity_name, entity_id, data)``
- ``entity.pre_update``  — called before update, receives ``(entity_name, entity_id, data, old_data)``
                           returns modified data dict (or original)
- ``entity.post_update`` — called after update, receives ``(entity_name, entity_id, data, old_data)``
- ``entity.pre_delete``  — called before delete, receives ``(entity_name, entity_id, data)``
                           returns True to proceed, False to cancel
- ``entity.post_delete`` — called after delete, receives ``(entity_name, entity_id, data)``
- ``transition.pre_transition``  — called before state change, receives
                                   ``(entity_name, entity_id, from_state, to_state)``
                                   returns True to proceed, False to cancel
- ``transition.post_transition`` — called after state change, receives
                                   ``(entity_name, entity_id, from_state, to_state)``
"""

from __future__ import annotations

import importlib.util
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Declaration header patterns
_HOOK_RE = re.compile(r"#\s*dazzle:service-hook\s+(\S+)")
_ENTITY_RE = re.compile(r"#\s*dazzle:entity\s+(\S+)")

VALID_HOOK_POINTS = frozenset(
    {
        "entity.pre_create",
        "entity.post_create",
        "entity.pre_update",
        "entity.post_update",
        "entity.pre_delete",
        "entity.post_delete",
        "transition.pre_transition",
        "transition.post_transition",
    }
)


@dataclass
class HookDescriptor:
    """Metadata about a discovered hook."""

    hook_point: str
    entity_filter: str  # Empty string means all entities
    source_path: Path
    function: Callable[..., Any]


@dataclass
class HookRegistry:
    """Registry of project-level service hooks.

    Hooks are grouped by hook point and optionally filtered by entity name.
    """

    _hooks: dict[str, list[HookDescriptor]] = field(default_factory=dict)

    def register(self, descriptor: HookDescriptor) -> None:
        """Register a hook descriptor."""
        self._hooks.setdefault(descriptor.hook_point, []).append(descriptor)
        entity_info = f" (entity: {descriptor.entity_filter})" if descriptor.entity_filter else ""
        logger.info(
            "Registered hook %s%s from %s",
            descriptor.hook_point,
            entity_info,
            descriptor.source_path,
        )

    def get_hooks(self, hook_point: str, entity_name: str = "") -> list[HookDescriptor]:
        """Get all hooks for a given hook point, optionally filtered by entity."""
        hooks = self._hooks.get(hook_point, [])
        if not entity_name:
            return hooks
        return [h for h in hooks if not h.entity_filter or h.entity_filter == entity_name]

    @property
    def count(self) -> int:
        """Total number of registered hooks."""
        return sum(len(v) for v in self._hooks.values())

    def summary(self) -> dict[str, int]:
        """Return a summary of hooks per hook point."""
        return {k: len(v) for k, v in self._hooks.items() if v}


def discover_hooks(hooks_dir: Path) -> list[HookDescriptor]:
    """Scan a project hooks directory for hook files with declaration headers.

    Args:
        hooks_dir: Path to the project's ``hooks/`` directory.

    Returns:
        List of discovered hook descriptors.
    """
    descriptors: list[HookDescriptor] = []

    if not hooks_dir.is_dir():
        return descriptors

    for py_file in sorted(hooks_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        hook_match = _HOOK_RE.search(content)
        if not hook_match:
            continue

        hook_point = hook_match.group(1).strip()
        if hook_point not in VALID_HOOK_POINTS:
            logger.warning(
                "Unknown hook point '%s' in %s (valid: %s)",
                hook_point,
                py_file,
                ", ".join(sorted(VALID_HOOK_POINTS)),
            )
            continue

        entity_match = _ENTITY_RE.search(content)
        entity_filter = entity_match.group(1).strip() if entity_match else ""

        # Load the module and find the hook function
        func = _load_hook_function(py_file)
        if func is None:
            logger.warning("No callable 'hook' function found in %s", py_file)
            continue

        descriptors.append(
            HookDescriptor(
                hook_point=hook_point,
                entity_filter=entity_filter,
                source_path=py_file,
                function=func,
            )
        )

    return descriptors


def _load_hook_function(py_file: Path) -> Callable[..., Any] | None:
    """Load a Python file and extract the ``hook`` function."""
    module_name = f"dazzle_hooks.{py_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("Failed to load hook module %s", py_file, exc_info=True)
        del sys.modules[module_name]
        return None

    func: Callable[..., Any] | None = getattr(module, "hook", None)
    if func is None or not callable(func):
        del sys.modules[module_name]
        return None

    return func


def build_registry(hooks_dir: Path) -> HookRegistry:
    """Discover hooks and build a registry.

    Args:
        hooks_dir: Path to the project's ``hooks/`` directory.

    Returns:
        Populated HookRegistry.
    """
    registry = HookRegistry()
    for descriptor in discover_hooks(hooks_dir):
        registry.register(descriptor)
    return registry
