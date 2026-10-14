"""Project-local override loader for sitespec section builders (#1110 Part A).

Project-local plugin pattern: scan a project-local directory (``<project_root>/site_sections/``) for
Python files that expose builder functions, register them by name, and
hand the registry to the dispatch path.

Builders shadow the framework's default builders for matching section
types. A project that wants a custom ``pricing`` section drops a
``site_sections/pricing.py`` with::

    def build_pricing_section(section: dict) -> str:
        ...

…and the registry returns that callable when ``render_typed_section``
looks up the ``pricing`` type. Falls through to the framework default
when no override is registered.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SectionBuilder = Callable[[dict[str, Any]], str]


class SectionOverrideRegistry:
    """Per-project registry of custom section builders.

    Used by :func:`dazzle.http.runtime.renderers.site_section_builder.render_typed_section`
    to dispatch a section to a project-local builder when one is
    registered. Construction is cheap — an empty registry is the
    default behaviour (no overrides) and consumers can pass it
    through unconditionally.
    """

    def __init__(self) -> None:
        self._builders: dict[str, SectionBuilder] = {}

    def register(self, section_type: str, builder: SectionBuilder) -> None:
        """Register ``builder`` for ``section_type``.

        Re-registering replaces the previous builder. The framework
        default builder for ``section_type`` (if any) is shadowed —
        the override takes precedence at dispatch time.
        """
        self._builders[section_type] = builder
        logger.debug("Registered section override for %r", section_type)

    def get(self, section_type: str) -> SectionBuilder | None:
        return self._builders.get(section_type)

    def list_overrides(self) -> list[str]:
        return sorted(self._builders.keys())

    def __bool__(self) -> bool:
        return bool(self._builders)


def discover_section_overrides(project_root: Path) -> SectionOverrideRegistry:
    """Scan ``<project_root>/site_sections/`` for builder functions.

    Each Python file in the directory may expose one or more
    ``build_<type>_section(section: dict) -> str`` callables. Filename
    is decoration only — the dispatch key is taken from the function
    name (``build_pricing_section`` → key ``pricing``). Files
    starting with ``_`` are skipped (private helpers).

    The directory does not need to exist. Returns an empty registry
    when it's absent — keeping the call-site unconditional. Import
    errors on individual files are logged at WARNING and the file is
    skipped; one broken plugin doesn't poison the whole registry.
    """
    registry = SectionOverrideRegistry()
    plugin_dir = project_root / "site_sections"
    if not plugin_dir.is_dir():
        return registry

    for py_file in sorted(plugin_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"site_sections.{py_file.stem}", py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                if not (attr_name.startswith("build_") and attr_name.endswith("_section")):
                    continue
                fn = getattr(module, attr_name)
                if not callable(fn):
                    continue
                sig = inspect.signature(fn)
                if len(sig.parameters) != 1:
                    # Builders must take exactly one positional arg
                    # (the section dict). Anything else is probably a
                    # helper that happens to follow the naming.
                    continue
                section_type = attr_name[len("build_") : -len("_section")]
                registry.register(section_type, fn)
        except Exception:
            logger.warning(
                "Failed to load section override %s — skipping",
                py_file.name,
                exc_info=True,
            )

    return registry
