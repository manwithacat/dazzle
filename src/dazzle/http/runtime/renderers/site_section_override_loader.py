"""Project-local override loader for sitespec section builders (#1110 Part A).

Mirrors the pattern proven in :mod:`dazzle.pitch.generators.plugin_loader`:
scan a project-local directory (``<project_root>/site_sections/``) for
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


_README_CONTENT = """# Project-local site section builders

Drop Python files in this directory to override or extend the framework's
default sitespec section renderers (#1110).

## Builder API

Each builder function must:

1. Be named `build_<section_type>_section` (e.g. `build_pricing_section`).
2. Accept exactly **one** positional argument: the section dict from
   `sitespec.yaml` (already shaped at parse time).
3. Return a string of pre-rendered HTML.

```python
import html

def build_pricing_section(section: dict) -> str:
    headline = html.escape(str(section.get("headline", "")))
    return (
        f'<section class="dz-section dz-section-pricing my-custom-pricing">'
        f"<h2>{headline}</h2>"
        # ...
        f"</section>"
    )
```

## How dispatch works

When the runtime renders a sitespec page, it walks `sections`. For each
typed section it:

1. Looks the section type up in the project's override registry.
2. If a builder is registered, calls it with the section dict.
3. Otherwise falls back to the framework's default builder for that
   type.
4. Unknown types are skipped per the typed-substrate directive.

## File naming

The filename is decoration — the dispatch key is taken from the
**function name** (`build_pricing_section` → `pricing`). One file can
export multiple builders; multiple files can target different section
types. Files starting with `_` are skipped (treat them as helpers).

## Available section types

The framework ships defaults for: `hero`, `cta`, `generic`, `trust_bar`,
`value_highlight`, `logo_cloud`, `markdown`, `stats`, `steps`,
`comparison`, `split_content`, `card_grid`, `team`, `testimonials`,
`features`, `pricing`, `faq`, `social_proof_strip`, `integration_grid`,
`compliance_badge_row`, `before_after_comparison`, `mid_page_cta_band`.

You can also register a builder for a **new** type — the dispatch
looks at the registry before the type whitelist, so an override for an
unrecognised type still wins.

## Errors

A broken plugin file logs a warning at startup and gets skipped — it
doesn't crash the boot. Check the application log for
`Failed to load section override …` if your builder doesn't seem to
take effect.
"""


def write_section_overrides_readme(project_root: Path) -> Path | None:
    """Write the convention README into ``<project_root>/site_sections/``.

    Idempotent. Skips if the README already exists so a project author's
    custom notes survive a re-scaffold. Returns the path on creation,
    ``None`` when the file was already present.
    """
    plugin_dir = project_root / "site_sections"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    readme = plugin_dir / "README.md"
    if readme.exists():
        return None
    readme.write_text(_README_CONTENT, encoding="utf-8")
    return readme
