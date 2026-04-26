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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
        extends: Parent theme name (Phase C Patch 1). When set, the
            parent's CSS is loaded BEFORE this theme's so the child's
            ``@layer overrides`` block wins. Inherited fields
            (default_color_scheme, font_preconnect, tags) fall through
            to the parent when this theme leaves them unset.
        templates_dir: Optional path to a ``<theme>/templates/``
            directory (Phase C Patch 2). When present, the framework's
            Jinja loader prepends it so this theme can override
            individual templates (e.g. ship a paper-stack
            ``card_wrapper.html``). ``None`` means CSS-only theme.
        site_preset: Phase C Patch 4 — name of a legacy site/marketing
            ``ThemeSpec`` preset (one of saas-default, minimal,
            corporate, startup, docs) to use for site-page rendering
            when this theme is active. ``None`` falls back to the
            project's ``[theme] preset`` in ``dazzle.toml``.
        site_overrides: Phase C Patch 4 — token overrides applied on
            top of ``site_preset``. Mirrors the structure of legacy
            ``[theme.colors]`` etc. blocks. Empty dict means no
            overrides. Keys are token categories (``colors``,
            ``shadows``, ``spacing``, ``radii``, ``custom``); values
            are the per-token mappings.
    """

    name: str
    description: str
    inspired_by: str
    default_color_scheme: ColorScheme
    font_preconnect: tuple[str, ...]
    tags: tuple[str, ...]
    css_path: Path
    source: Literal["framework", "project"]
    extends: str | None = None
    templates_dir: Path | None = None
    site_preset: str | None = None
    site_overrides: dict[str, Any] = field(default_factory=dict)


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
        extends = data.get("extends")
        if extends is not None and not isinstance(extends, str):
            raise ValueError(
                f"Theme {name!r}: `extends` must be a string (parent theme name); "
                f"got {type(extends).__name__}"
            )
        if extends == name:
            raise ValueError(f"Theme {name!r} cannot extend itself")
        site_preset, site_overrides = _parse_site_section(name, data.get("site"))
        return AppThemeManifest(
            name=name,
            description=str(data.get("description", "")),
            inspired_by=str(data.get("inspired_by", "")),
            default_color_scheme=scheme,
            font_preconnect=tuple(data.get("font_preconnect", []) or []),
            tags=tuple(data.get("tags", []) or []),
            css_path=css_path,
            source=source,
            extends=extends,
            templates_dir=_resolve_templates_dir(css_path),
            site_preset=site_preset,
            site_overrides=site_overrides,
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
        templates_dir=_resolve_templates_dir(css_path),
    )


# Phase C Patch 4: site-section keys recognised in the unified manifest.
# Mirrors the categories the legacy `ThemeConfig` accepts so the runtime
# can pass them through `resolve_theme(...)` unchanged.
_SITE_OVERRIDE_KEYS: frozenset[str] = frozenset({"colors", "shadows", "spacing", "radii", "custom"})


def _parse_site_section(theme_name: str, site_data: Any) -> tuple[str | None, dict[str, Any]]:
    """Parse the optional ``[site]`` table — Phase C Patch 4.

    Returns ``(site_preset, site_overrides)`` where ``site_preset`` is
    a legacy ``ThemeSpec`` preset name (or ``None`` when only inline
    overrides are supplied) and ``site_overrides`` is the structured
    overrides dict suitable for ``resolve_theme(manifest_overrides=...)``.

    A theme that omits ``[site]`` returns ``(None, {})`` and the runtime
    falls back to ``[theme]`` in ``dazzle.toml`` as before.
    """
    if site_data is None:
        return None, {}
    if not isinstance(site_data, dict):
        raise ValueError(
            f"Theme {theme_name!r}: `[site]` must be a table; got {type(site_data).__name__}"
        )
    preset = site_data.get("preset")
    if preset is not None and not isinstance(preset, str):
        raise ValueError(
            f"Theme {theme_name!r}: `[site] preset` must be a string; got {type(preset).__name__}"
        )
    overrides: dict[str, Any] = {}
    for key, value in site_data.items():
        if key == "preset":
            continue
        if key not in _SITE_OVERRIDE_KEYS:
            raise ValueError(
                f"Theme {theme_name!r}: unknown `[site]` key {key!r}; "
                f"expected one of {sorted(_SITE_OVERRIDE_KEYS)} or `preset`"
            )
        if not isinstance(value, dict):
            raise ValueError(
                f"Theme {theme_name!r}: `[site.{key}]` must be a table; got {type(value).__name__}"
            )
        overrides[key] = dict(value)
    return preset, overrides


def _resolve_templates_dir(css_path: Path) -> Path | None:
    """Return ``<themes_dir>/<name>/templates/`` when present, else None.

    Phase C Patch 2: themes that need template overrides ship them
    alongside the CSS. Convention: a sibling directory named for the
    theme containing a ``templates/`` subdir matching the framework's
    template path layout. Themes that just override tokens leave this
    out and the helper returns None.
    """
    candidate = css_path.parent / css_path.stem / "templates"
    return candidate if candidate.is_dir() else None


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


# Phase C Patch 1: theme inheritance — chain resolution.
# Cap depth at 4 to prevent runaway chains; deeper than 4 is a design
# smell and should fail loudly at validation time.
_MAX_INHERITANCE_DEPTH = 4


def resolve_inheritance_chain(
    name: str,
    project_root: Path | None = None,
) -> list[AppThemeManifest]:
    """Walk a theme's `extends` chain, returning manifests root → leaf.

    For a theme `cyan-tweak` that `extends = "linear-dark"`, returns
    ``[<linear-dark>, <cyan-tweak>]`` so the runtime can emit the CSS
    links in cascade order (parent loads first; child's
    ``@layer overrides`` wins).

    Phase C Patch 1 — implements the design-system Phase C inheritance
    feature. See ``dev_docs/2026-04-26-design-system-phase-c.md``.

    Raises:
        ValueError: When the chain exceeds depth 4, contains a cycle,
            or references a missing parent.
    """
    registry = discover_themes(project_root=project_root)
    if name not in registry:
        raise ValueError(f"Theme {name!r} not found in registry")

    chain: list[AppThemeManifest] = []
    visited: set[str] = set()
    current: str | None = name

    while current is not None:
        if current in visited:
            cycle = " → ".join([*[m.name for m in chain], current])
            raise ValueError(f"Theme inheritance cycle detected: {cycle}")
        visited.add(current)

        if current not in registry:
            parent_chain = " → ".join(m.name for m in chain)
            raise ValueError(
                f"Theme {current!r} (extended by {parent_chain}) not found in registry"
            )

        manifest = registry[current]
        chain.append(manifest)

        if len(chain) > _MAX_INHERITANCE_DEPTH:
            chain_repr = " → ".join(m.name for m in chain)
            raise ValueError(
                f"Theme inheritance chain exceeds max depth {_MAX_INHERITANCE_DEPTH}: {chain_repr}"
            )

        current = manifest.extends

    # chain currently leaf → root because we appended each ancestor
    # AFTER its child. Reverse so callers can iterate root → leaf and
    # emit CSS in cascade order.
    return list(reversed(chain))


# Phase C Patch 4: resolve site-page config from the active app theme.


def resolve_site_config(
    name: str | None,
    project_root: Path | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Look up the site-page config declared by the active app theme.

    When ``name`` is set and the matching manifest declares a ``[site]``
    section, returns that theme's site preset + overrides. Falls back to
    the inheritance chain — if the leaf doesn't override either field,
    walk parents (root → leaf order) so a child can inherit the parent's
    site config without restating it. Returns ``(None, {})`` when no
    chain entry declares a site config or when ``name`` is ``None`` /
    not in the registry. The caller blends those defaults with the
    legacy ``[theme]`` block from ``dazzle.toml`` (which always supplies
    a baseline preset).

    See ``dev_docs/2026-04-26-design-system-phase-c.md`` Patch 4.
    """
    if not name:
        return None, {}
    try:
        chain = resolve_inheritance_chain(name, project_root=project_root)
    except ValueError:
        return None, {}
    preset: str | None = None
    overrides: dict[str, Any] = {}
    for manifest in chain:
        if manifest.site_preset is not None:
            preset = manifest.site_preset
        for key, value in manifest.site_overrides.items():
            existing = overrides.setdefault(key, {})
            if isinstance(value, dict):
                existing.update(value)
    return preset, overrides
