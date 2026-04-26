"""App-shell theme registry — discovers + loads themes shipped under
``src/dazzle_ui/runtime/static/css/themes/`` plus optional project-local
themes under ``<project>/themes/``.

Each theme is a CSS file (``<name>.css``) with an optional sibling
manifest TOML (``<name>.toml``) declaring metadata. Themes without a
manifest are still discoverable — they get a synthesised
``AppThemeManifest`` with sensible defaults so legacy / project-local
CSS-only themes keep working.

Phase B Patch 1 of the design-system formalisation work
(see ``dev_docs/2026-04-26-design-system-phase-b.md``).
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ColorScheme = Literal["light", "dark", "auto"]
_VALID_SCHEMES: frozenset[str] = frozenset({"light", "dark", "auto"})

# Framework-shipped themes live here. Resolved relative to this file's
# location so the path is independent of cwd / sys.path quirks.
_FRAMEWORK_THEMES_DIR = (
    Path(__file__).resolve().parent.parent / "runtime" / "static" / "css" / "themes"
)


@dataclass(frozen=True)
class AppThemeManifest:
    """Parsed theme manifest — one per theme directory.

    Attributes:
        name: Theme identifier (matches the CSS filename stem).
        description: One-line human-readable summary.
        inspired_by: Free-form attribution (e.g. "Linear (linear.app)").
        default_color_scheme: ``light`` | ``dark`` | ``auto``. Hints to
            ``ThemeVariantMiddleware`` what to default a first-visit user
            to when no `prefers-color-scheme` is set.
        font_preconnect: Google Fonts URLs to add as ``<link rel="preconnect">``
            in ``base.html``. Empty list = use system-fallback fonts only.
        tags: Free-form tags for ``dazzle theme list --tag``.
        css_path: Resolved absolute path to the theme's CSS file.
        source: ``framework`` (shipped) or ``project`` (local override).
    """

    name: str
    description: str
    inspired_by: str
    default_color_scheme: ColorScheme
    font_preconnect: tuple[str, ...]
    tags: tuple[str, ...]
    css_path: Path
    source: Literal["framework", "project"]


def _parse_manifest(
    css_path: Path,
    toml_path: Path | None,
    source: Literal["framework", "project"],
) -> AppThemeManifest:
    """Parse a theme manifest TOML, or synthesise defaults when absent."""
    name = css_path.stem
    if toml_path and toml_path.is_file():
        data = tomllib.loads(toml_path.read_text())
        scheme = data.get("default_color_scheme", "auto")
        if scheme not in _VALID_SCHEMES:
            raise ValueError(
                f"Theme {name!r}: default_color_scheme must be one of "
                f"{sorted(_VALID_SCHEMES)}; got {scheme!r}"
            )
        # Manifest's `name` should match the file stem — surface mismatches
        # as load-time errors so renames don't drift silently.
        manifest_name = data.get("name", name)
        if manifest_name != name:
            raise ValueError(
                f"Theme manifest name {manifest_name!r} doesn't match "
                f"CSS filename {name!r} ({css_path})"
            )
        return AppThemeManifest(
            name=name,
            description=str(data.get("description", "")),
            inspired_by=str(data.get("inspired_by", "")),
            default_color_scheme=scheme,
            font_preconnect=tuple(data.get("font_preconnect", []) or []),
            tags=tuple(data.get("tags", []) or []),
            css_path=css_path,
            source=source,
        )
    # No manifest — synthesise defaults so CSS-only themes still load.
    return AppThemeManifest(
        name=name,
        description="",
        inspired_by="",
        default_color_scheme="auto",
        font_preconnect=(),
        tags=(),
        css_path=css_path,
        source=source,
    )


def _discover_in(
    themes_dir: Path,
    source: Literal["framework", "project"],
) -> Iterable[AppThemeManifest]:
    """Walk a themes directory, yielding one manifest per ``*.css`` file."""
    if not themes_dir.is_dir():
        return
    for css_path in sorted(themes_dir.glob("*.css")):
        toml_path = css_path.with_suffix(".toml")
        yield _parse_manifest(css_path, toml_path, source)


def discover_themes(project_root: Path | None = None) -> dict[str, AppThemeManifest]:
    """Build the full theme registry.

    Resolution: framework themes first, then project-local themes (which
    OVERRIDE shipped themes of the same name — projects can ship their
    own ``linear-dark`` to tweak the framework default without forking).

    Args:
        project_root: Project root containing optional ``themes/`` dir.
            Pass the cwd / `Path.cwd()` for normal use; `None` skips
            project-local discovery.

    Returns:
        Dict keyed by theme name → manifest.
    """
    registry: dict[str, AppThemeManifest] = {}
    for theme in _discover_in(_FRAMEWORK_THEMES_DIR, source="framework"):
        registry[theme.name] = theme
    if project_root is not None:
        project_themes_dir = project_root / "themes"
        for theme in _discover_in(project_themes_dir, source="project"):
            registry[theme.name] = theme  # project overrides framework
    return registry


def get_theme(name: str, project_root: Path | None = None) -> AppThemeManifest | None:
    """Look up a single theme by name. Returns ``None`` if not found."""
    return discover_themes(project_root).get(name)


def list_theme_names(project_root: Path | None = None) -> list[str]:
    """Return shipped + project theme names in deterministic order."""
    return sorted(discover_themes(project_root).keys())
