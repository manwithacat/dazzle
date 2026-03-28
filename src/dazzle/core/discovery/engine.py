"""Suggestion engine for capability discovery.

Coordinates all rule modules, builds the example index, and joins rule output
with example references to produce enriched Relevance items.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec

from dazzle.core.discovery.completeness_rules import check_completeness_relevance
from dazzle.core.discovery.component_rules import check_component_relevance
from dazzle.core.discovery.example_index import build_example_index
from dazzle.core.discovery.layout_rules import check_layout_relevance
from dazzle.core.discovery.models import ExampleRef, Relevance
from dazzle.core.discovery.widget_rules import check_widget_relevance

_log = logging.getLogger(__name__)


def suggest_capabilities(
    appspec: AppSpec,
    *,
    examples_dir: Path | None = None,
    suppress: bool = False,
) -> list[Relevance]:
    """Return enriched Relevance items for capabilities applicable to *appspec*.

    Calls all four rule modules, builds an example index from *examples_dir*
    (auto-detected if not provided), then joins each raw Relevance with any
    matching example references.

    Args:
        appspec: The parsed and linked application specification.
        examples_dir: Directory containing example app subdirectories.
            If ``None``, the function attempts to locate the ``examples/``
            directory relative to the installed ``dazzle`` package.
        suppress: If ``True``, return an empty list immediately without
            running any rules. Useful for CI environments where discovery
            output is not desired.

    Returns:
        A list of :class:`Relevance` objects with ``examples`` populated from
        matching example apps.  Returns ``[]`` when *suppress* is ``True`` or
        no rules fire.
    """
    if suppress:
        return []

    entities = list(appspec.domain.entities)
    surfaces = list(appspec.surfaces)
    workspaces = list(appspec.workspaces)

    # Collect raw results from all rule modules.
    raw: list[Relevance] = []
    raw.extend(check_widget_relevance(entities, surfaces))
    raw.extend(check_layout_relevance(entities, surfaces, workspaces))
    raw.extend(check_component_relevance(entities, surfaces, workspaces))
    raw.extend(check_completeness_relevance(entities, surfaces))

    if not raw:
        return []

    # Resolve examples directory.
    if examples_dir is None:
        examples_dir = _find_examples_dir()

    # Build example index (returns {} when dir is missing or empty).
    if examples_dir is not None:
        index: dict[str, list[ExampleRef]] = build_example_index(examples_dir)
    else:
        index = {}

    # Join each Relevance with matching ExampleRef entries.
    enriched: list[Relevance] = []
    for item in raw:
        cap_key = _cap_key(item.kg_entity)
        refs = index.get(cap_key, [])
        enriched.append(
            Relevance(
                context=item.context,
                capability=item.capability,
                category=item.category,
                examples=refs,
                kg_entity=item.kg_entity,
            )
        )

    return enriched


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cap_key(kg_entity: str) -> str:
    """Derive capability key from a KG entity string.

    Examples::

        "capability:widget_rich_text"  → "widget_rich_text"
        "widget_rich_text"             → "widget_rich_text"
    """
    if ":" in kg_entity:
        return kg_entity.split(":", 1)[1]
    return kg_entity


def _find_examples_dir() -> Path | None:
    """Locate the ``examples/`` directory relative to the dazzle package.

    Walks up from the installed package location:
    ``src/dazzle/__init__.py`` → ``src/dazzle/`` → ``src/`` → project root

    Returns:
        Path to the examples directory if it exists, otherwise ``None``.
    """
    try:
        import dazzle

        pkg_dir = Path(dazzle.__file__).resolve().parent
        project_root = pkg_dir.parent.parent  # src/dazzle → src → root
        examples = project_root / "examples"
        return examples if examples.is_dir() else None
    except Exception:  # noqa: BLE001
        _log.debug("_find_examples_dir: could not locate examples dir")
        return None
