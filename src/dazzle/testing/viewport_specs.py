"""Custom viewport specification persistence.

Users define custom viewport assertions in JSON, which get merged with
auto-derived patterns from the AppSpec.

Storage locations:
- Primary: dsl/tests/viewport_specs.json (version-controlled)
- Runtime: .dazzle/viewport_specs/specs.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from dazzle.testing.viewport import ComponentPattern, ViewportAssertion

# Storage paths
DSL_SPECS_DIR = "dsl/tests"
RUNTIME_SPECS_DIR = ".dazzle/viewport_specs"
SPECS_FILE = "viewport_specs.json"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ViewportAssertionEntry(BaseModel):
    """A single viewport assertion entry in a custom spec."""

    selector: str
    property: str
    expected: str | list[str]
    viewport: str
    description: str = ""


class ViewportSpecEntry(BaseModel):
    """A named collection of viewport assertions for a page."""

    name: str
    page_path: str
    assertions: list[ViewportAssertionEntry]


class ViewportSpecsContainer(BaseModel):
    """Top-level container for persisting custom viewport specs."""

    version: str = "1.0"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    specs: list[ViewportSpecEntry] = Field(default_factory=list)


def _get_dsl_specs_path(project_root: Path) -> Path:
    return project_root / DSL_SPECS_DIR / SPECS_FILE


def _get_runtime_specs_path(project_root: Path) -> Path:
    return project_root / RUNTIME_SPECS_DIR / SPECS_FILE


def load_custom_viewport_specs(project_root: Path) -> list[ViewportSpecEntry]:
    """Load custom viewport specs from disk.

    Checks the DSL location first, then falls back to runtime location.

    Parameters
    ----------
    project_root:
        Root directory of the project.

    Returns
    -------
    list[ViewportSpecEntry]
        Loaded specs, or empty list if none found.
    """
    for path_fn in (_get_dsl_specs_path, _get_runtime_specs_path):
        path = path_fn(project_root)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                container = ViewportSpecsContainer(**data)
                return container.specs
            except (json.JSONDecodeError, Exception):
                continue
    return []


def save_custom_viewport_specs(
    project_root: Path,
    specs: list[ViewportSpecEntry],
    *,
    to_dsl: bool = True,
) -> Path:
    """Save custom viewport specs to disk.

    Parameters
    ----------
    project_root:
        Root directory of the project.
    specs:
        The specs to save.
    to_dsl:
        If True, save to dsl/tests/ (version-controlled).
        If False, save to .dazzle/viewport_specs/ (runtime).

    Returns
    -------
    Path
        The path the file was written to.
    """
    path = _get_dsl_specs_path(project_root) if to_dsl else _get_runtime_specs_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    container = ViewportSpecsContainer(
        specs=specs,
        updated_at=_utcnow(),
    )
    path.write_text(container.model_dump_json(indent=2))
    return path


def convert_to_patterns(
    specs: list[ViewportSpecEntry],
) -> dict[str, list[ComponentPattern]]:
    """Convert custom spec entries to ComponentPattern dicts keyed by page path.

    Parameters
    ----------
    specs:
        Custom viewport spec entries.

    Returns
    -------
    dict[str, list[ComponentPattern]]
        ``{page_path: [ComponentPattern, ...]}``
    """
    result: dict[str, list[ComponentPattern]] = {}
    for spec in specs:
        assertions = [
            ViewportAssertion(
                selector=a.selector,
                property=a.property,
                expected=a.expected,
                viewport=a.viewport,
                description=a.description or f"{spec.name}: {a.property} at {a.viewport}",
            )
            for a in spec.assertions
        ]
        pattern = ComponentPattern(name=spec.name, assertions=assertions)
        result.setdefault(spec.page_path, []).append(pattern)
    return result


def merge_patterns(
    derived: dict[str, list[ComponentPattern]],
    custom: dict[str, list[ComponentPattern]],
) -> dict[str, list[ComponentPattern]]:
    """Merge auto-derived patterns with custom patterns.

    Custom patterns are appended to the list for each page path.
    Duplicate pattern names on the same page are skipped.

    Parameters
    ----------
    derived:
        Patterns from ``derive_patterns_from_appspec()``.
    custom:
        Patterns from ``convert_to_patterns()``.

    Returns
    -------
    dict[str, list[ComponentPattern]]
        Merged result.
    """
    merged = {k: list(v) for k, v in derived.items()}
    for page_path, patterns in custom.items():
        existing = merged.setdefault(page_path, [])
        existing_names = {p.name for p in existing}
        for pat in patterns:
            if pat.name not in existing_names:
                existing.append(pat)
                existing_names.add(pat.name)
    return merged
