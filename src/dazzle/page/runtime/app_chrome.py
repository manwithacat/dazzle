"""App chrome resolver — surfaces theme, asset, branding config (#1042 follow-up).

Pre-#1042 these were Jinja env globals (``_use_cdn``, ``_app_theme``,
``_app_theme_url``, ``_app_theme_url_chain``, ``_app_theme_font_preconnect``,
``_app_theme_map``, ``_favicon``, ``_feedback_widget_enabled``) consumed
by ``base.html`` and ``layouts/app_shell.html``. Both templates are
gone; the typed-Page primitive substrate now consumes the same data
through the typed ``AppChrome`` dataclass that lives on
``app.state.fragment_chrome``.

The single ``resolve_app_chrome`` entry point computes the chrome
config from the AppSpec + dazzle.toml manifest + project root + env
overrides. Called once at app boot in ``system_routes.py`` and stashed
on ``app.state``; every page-render call site reads from there.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.core import ir
from dazzle.core.manifest import TopbarTitleMode
from dazzle.page.runtime.asset_fingerprint import StaticFingerprinter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AppChrome:
    """Resolved app-wide chrome configuration.

    Stashed on ``app.state.fragment_chrome`` at boot and passed into
    the typed Page primitive at every render.

    Attributes:
        css_links: Stylesheet URLs in cascade order (parent theme →
            leaf theme; leaf wins via CSS @layer overrides). Always
            includes the framework bundle as the first entry.
        js_scripts: Script URLs (deferred). Default is just the
            framework bundle; themes may extend.
        theme: Leaf theme name for the ``data-theme`` attribute on
            ``<html>``. None when no theme is configured (uses the
            framework default).
        theme_map: Mapping of theme-name → full css-chain. Used by a
            future live-switcher island; emitted as JSON.
        font_preconnect: External font origins to emit as
            ``<link rel="preconnect" href="...">`` in ``<head>``.
        favicon: Favicon URL (defaults to the framework asset).
        use_cdn: ``True`` when the project opted into CDN-hosted
            assets via ``[ui] cdn = true`` in dazzle.toml. Currently
            informational — the typed substrate always serves local
            ``dist/dazzle.min.{css,js}``; CDN routing is a follow-up.
        topbar_title: ``[ui] topbar_title`` (#1794) — ``"app"`` (app name,
            default), ``"page"`` (the page title, app name as fallback) or
            ``"none"`` (empty topbar title).
        page_purpose: ``[ui] page_purpose`` (#1811) — ``False`` stops the shell
            rendering ``ux: purpose:`` as ``.dz-page-purpose`` (default ``True``).
    """

    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",)
    # #1276: lucide UMD must precede the framework bundle so `window.lucide`
    # exists when dazzle.min.js calls `lucide.createIcons()`. Pre-#1042 the
    # Jinja head included this script via a CDN link; the typed substrate
    # had silently dropped it, leaving every data-lucide icon invisible on
    # marketing/site pages.
    # #1336: vendored widget JS formerly loaded here (TomSelect) — retired in
    # HMC-018 slice 3. combobox/tags are now HM-native progressive-enhancement
    # controllers bundled inside dazzle.min.js, so there is no separate vendor
    # widget runtime to preload before the bundle's DOMContentLoaded
    # mountWidgets() pass.
    js_scripts: tuple[str, ...] = (
        "/static/dist/dazzle-icons.min.js",
        "/static/dist/dazzle.min.js",
    )
    theme: str | None = None
    theme_map: dict[str, list[str]] = field(default_factory=dict)
    font_preconnect: tuple[str, ...] = ()
    favicon: str = "/static/assets/dazzle-favicon.svg"
    use_cdn: bool = False
    topbar_title: TopbarTitleMode = "app"
    page_purpose: bool = True


_FRAMEWORK_BUNDLE_CSS = "/static/dist/dazzle.min.css"
PROJECT_CUSTOM_CSS = "/static/css/custom.css"
_FRAMEWORK_BUNDLE_JS = "/static/dist/dazzle.min.js"
# #1276: lucide UMD bundle ships in the wheel at the same dist path.
# Must load before the framework bundle so `window.lucide.createIcons()`
# resolves on first page render.
_LUCIDE_UMD_JS = "/static/dist/dazzle-icons.min.js"
# #1336: a vendored widget runtime (TomSelect) was preloaded here until
# HMC-018 slice 3. combobox/tags are now HM-native controllers inside the
# framework bundle, so no separate vendor widget JS is needed.
_DEFAULT_FAVICON = "/static/assets/dazzle-favicon.svg"
# `feedback_widget: enabled` mounts the in-app feedback widget (button +
# panel posting to /feedbackreports). Its CSS ships inside dazzle.min.css.
FEEDBACK_WIDGET_JS = "/static/js/feedback-widget.js"


def _theme_css_url(theme: Any) -> str:
    """Mirror the legacy registry's URL convention.

    Framework themes live under ``/static/css/themes/<name>.css``;
    project themes under ``/static/themes/<name>.css``.
    """
    if getattr(theme, "source", None) == "framework":
        return f"/static/css/themes/{theme.name}.css"
    return f"/static/themes/{theme.name}.css"


def _dedup_preserving_order(items: list[str]) -> tuple[str, ...]:
    """Drop duplicates while keeping first-seen order — used to merge
    font preconnects across an inheritance chain."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _hashed_urls(fingerprinter: StaticFingerprinter, urls: list[str]) -> list[str]:
    """Content-hash each URL (#1793); warn on a hand-bumped ``?v=`` that blocks it."""
    if fingerprinter.enabled:
        for url in urls:
            if url.startswith("/static/") and "?" in url:
                logger.warning(
                    "Chrome asset %r carries a hand-bumped query string — fingerprinting "
                    "skipped; drop the ?v= and the URL is content-hashed (#1793)",
                    url,
                )
    return [fingerprinter.hashed(u) for u in urls]


def resolve_app_chrome(
    appspec: ir.AppSpec,
    *,
    project_root: Path | None = None,
    manifest: Any = None,
    fingerprinter: StaticFingerprinter | None = None,
) -> AppChrome:
    """Compute the full ``AppChrome`` for an app.

    Resolution order for theme name:
        1. ``DAZZLE_OVERRIDE_THEME`` env var (operator-level A/B).
        2. ``appspec.app_config.theme`` (DSL ``app foo: theme: ...``).
        3. ``manifest.app_theme`` (``[ui] theme = "..."`` in
           dazzle.toml).
        4. None — use the framework default bundled in
           ``dazzle.min.css``.

    Args:
        appspec: The compiled AppSpec.
        project_root: Project root (used for theme discovery). When
            None, only framework themes are considered.
        manifest: Loaded dazzle.toml manifest. Optional — when None,
            CDN / favicon / theme fall back to defaults.
        fingerprinter: The app's ``StaticFingerprinter`` (#1793). When None,
            one is built for ``project_root`` (no ``extra_static_dirs``).

    Returns:
        Fully populated ``AppChrome``. Always emits the framework
        bundle as the first CSS/JS entry; themes append.
    """
    # Manifest-level config (favicon, cdn toggle).
    favicon = _DEFAULT_FAVICON
    use_cdn = False
    active_development = False
    manifest_theme: str | None = None
    topbar_title: TopbarTitleMode = "app"
    page_purpose = True
    if manifest is not None:
        topbar_title = getattr(manifest, "topbar_title", "app")
        page_purpose = bool(getattr(manifest, "page_purpose", True))
        if getattr(manifest, "favicon", None):
            favicon = str(manifest.favicon)
        use_cdn = bool(getattr(manifest, "cdn", False))
        active_development = bool(getattr(manifest, "active_development", False))
        manifest_theme = getattr(manifest, "app_theme", None) or None

    # Theme name: env > DSL > manifest > None.
    env_theme = os.environ.get("DAZZLE_OVERRIDE_THEME") or None
    dsl_theme: str | None = None
    app_config = getattr(appspec, "app_config", None) if appspec is not None else None
    if app_config is not None and getattr(app_config, "theme", None):
        dsl_theme = str(app_config.theme)
    leaf_theme = env_theme or dsl_theme or manifest_theme

    # Default CSS / JS chain — framework bundle always first.
    # #1276: lucide UMD precedes the framework bundle so window.lucide is
    # defined before dazzle.min.js calls lucide.createIcons().
    css_links: list[str] = [_FRAMEWORK_BUNDLE_CSS]
    js_scripts: list[str] = [
        _LUCIDE_UMD_JS,
        _FRAMEWORK_BUNDLE_JS,
    ]
    font_preconnect: list[str] = []
    theme_map: dict[str, list[str]] = {}

    if leaf_theme is not None:
        try:
            from dazzle.page.themes.app_theme_registry import (
                discover_themes,
                resolve_inheritance_chain,
            )

            chain = resolve_inheritance_chain(leaf_theme, project_root=project_root)
            for theme in chain:
                css_links.append(_theme_css_url(theme))
                font_preconnect.extend(getattr(theme, "font_preconnect", ()) or ())

            # Build full theme_map for the live switcher. Each entry
            # is the full inheritance-chain CSS URL list.
            for tname in sorted(discover_themes(project_root=project_root)):
                try:
                    sub_chain = resolve_inheritance_chain(tname, project_root=project_root)
                except ValueError:
                    # Broken inheritance — skip; other themes stay switchable.
                    continue
                theme_map[tname] = [_theme_css_url(t) for t in sub_chain]
        except ValueError as exc:
            logger.warning(
                "Theme %r inheritance resolution failed — falling back to default chrome: %s",
                leaf_theme,
                exc,
            )
            leaf_theme = None
        except Exception:
            logger.warning(
                "Theme registry lookup failed for %r — falling back to default chrome",
                leaf_theme,
                exc_info=True,
            )
            leaf_theme = None

    # #1796: a project's `static/css/custom.css` was linked by the site and auth
    # pages only; the app shell never saw it. Link it after the theme chain so it
    # can override, the same auto-detection the site routes use.
    if project_root is not None and (project_root / "static" / "css" / "custom.css").is_file():
        css_links.append(PROJECT_CUSTOM_CSS)

    # Feedback widget (`feedback_widget: enabled`) — the FeedbackReport entity
    # and /feedbackreports API are linker-generated; this mounts the client.
    feedback_widget = getattr(appspec, "feedback_widget", None) if appspec is not None else None
    if feedback_widget is not None and getattr(feedback_widget, "enabled", False):
        js_scripts.append(FEEDBACK_WIDGET_JS)

    # Onboarding overlay JS (v0.71.6) — auto-mount when the project
    # declares any `guide` block. Apps without guides don't pay the
    # ~2 KB script cost.
    if appspec is not None and getattr(appspec, "guides", None):
        js_scripts.append("/static/js/dz-onboarding.js")

    # #1515 — downstream app custom client JS. Appended after the framework +
    # onboarding scripts so a project's islands/controllers load last (and can
    # depend on the framework bundle). Order-preserving; goes through the same
    # fingerprint pass below. Static serving of static/js/*.js already works
    # (#793) — this only threads the URLs into the chrome <head>.
    for _app_script in getattr(manifest, "app_scripts", None) or []:
        js_scripts.append(str(_app_script))

    # #1468/#1793: content-hash every linked /static/ URL — framework bundle,
    # theme chain (entry + its @imports), custom.css, app_scripts — in
    # prod/staging so a deploy's fixes reach returning visitors immediately.
    # No-op in dev/test/active-development.
    if fingerprinter is None:
        fingerprinter = StaticFingerprinter.for_project(
            project_root, active_development=active_development
        )
    css_links = _hashed_urls(fingerprinter, css_links)
    js_scripts = _hashed_urls(fingerprinter, js_scripts)
    theme_map = {name: _hashed_urls(fingerprinter, urls) for name, urls in theme_map.items()}
    favicon = fingerprinter.hashed(favicon)

    return AppChrome(
        css_links=tuple(css_links),
        js_scripts=tuple(js_scripts),
        theme=leaf_theme,
        theme_map=theme_map,
        font_preconnect=_dedup_preserving_order(font_preconnect),
        favicon=favicon,
        use_cdn=use_cdn,
        topbar_title=topbar_title,
        page_purpose=page_purpose,
    )
