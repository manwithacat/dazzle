"""Content-hash fingerprinting for everything the page chrome links.

Rewrites ``/static/<rel>`` URLs with the content hash embedded in the
filename (never a query string):

    /static/dist/dazzle.min.js   → /static/dist/dazzle.min.a1b2c3d4.js
    /static/js/brand-chrome.js   → /static/js/brand-chrome.0f3c9e21.js
    /static/themes/aegismark.css → /static/themes/aegismark.5d1e77b0.css

The static file server (``CombinedStaticFiles``) recognises the hashed
pattern, strips the hash to find the real file on disk, and serves it with
``Cache-Control: immutable``. A deploy that changes a file changes its hash →
a new URL → returning visitors fetch the fix immediately instead of running
the cached copy until ``max-age`` expires (#1468 for the framework bundle;
#1793 for project ``[ui] app_scripts``, theme entries and the sheets they
``@import``, ``static/css/custom.css`` and renderer-declared assets).

One :class:`StaticFingerprinter` per app covers every directory the
``/static`` mounts serve — consumer ``extra_static_dirs``, ``<project>/static``,
the framework's static dir, plus ``<project>/themes`` under
``/static/themes``. A stylesheet's digest folds in the digests of every
absolute ``/static/...`` ``@import`` it carries (recursively), so editing an
imported sheet changes the entry's URL too; the server rewrites those
``@import`` URLs to their hashed form when it serves the sheet. Relative
``@import``s and ``url()`` sub-resources are not followed.

Gated on environment (``should_fingerprint``): on in production/staging,
off in dev/test (plain URLs, fast iteration) and when a project sets
``[ui] active_development = true`` (a deployed site that wants no-cache
iteration instead of immutable fingerprints).

No build step required — digests are computed lazily and cached for the
process lifetime (a deploy is a new process, so the cache always reflects the
bytes being served; fingerprinting is off under ``serve --watch``).
"""

import hashlib
import os
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from dazzle.render.fragment.registry import RendererAsset, asset_url

# Matches a fingerprinted filename: name.HEXHASH.ext
# The hash is 8 hex chars (truncated SHA-256).
FINGERPRINT_RE = re.compile(r"^(.+)\.([0-9a-f]{8})(\.\w+)$")

# An absolute `/static/...` @import, quoted or url()-wrapped, with an optional
# layer()/supports()/media clause before the terminating semicolon.
_CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*)?["']?(/static/[^"')\s;]+)["']?\s*\)?([^;]*);"""
)

_STATIC_PREFIX = "/static/"
_THEMES_PREFIX = "themes/"


def strip_fingerprint(path: str) -> str | None:
    """Strip the content hash from a fingerprinted filename.

    Returns the original filename if the path matches the fingerprint
    pattern, or None if it doesn't match.

    Example::

        strip_fingerprint("css/dazzle-bundle.a1b2c3d4.css")
        # → "css/dazzle-bundle.css"
    """
    match = FINGERPRINT_RE.match(path)
    if match:
        return f"{match.group(1)}{match.group(3)}"
    return None


def should_fingerprint(*, active_development: bool = False, env: str | None = None) -> bool:
    """Whether static asset URLs should carry content-hash fingerprints.

    On in production/staging — returning visitors must receive a JS/CSS fix
    the instant it deploys, not after the asset's ``max-age`` expires (#1468).
    Off in dev/test (plain ``/static/...`` URLs — fast iteration, stable
    test assertions) and whenever a project opts into ``[ui]
    active_development = true`` (a deployed site that prefers ``no-cache``
    iteration over immutable fingerprints).

    Mirrors :func:`dazzle.page.runtime.asset_bundle.should_bundle_assets`'s
    environment gate so bundling and fingerprinting turn on together.
    """
    if active_development:
        return False
    resolved = env if env is not None else os.environ.get("DAZZLE_ENV", "")
    return resolved in ("production", "staging")


def framework_static_dir() -> Path:
    """The framework's served static dir (``page/runtime/static``)."""
    return Path(__file__).parent / "static"


def static_root_dirs(
    project_root: Path | str | None, extra_static_dirs: Iterable[Path | str] | None = None
) -> list[Path]:
    """The directories the catch-all ``/static`` mount serves, in precedence order.

    Consumer-supplied ``extra_static_dirs`` win (#793), then
    ``<project>/static``, then the framework's static dir (always last — it is
    the mount's primary/fallback directory).
    """
    dirs: list[Path] = [Path(d) for d in extra_static_dirs or ()]
    if project_root:
        dirs.append(Path(project_root) / "static")
    dirs.append(framework_static_dir())
    return dirs


def _hashed_name(rel: str, digest: str) -> str:
    p = PurePosixPath(rel)
    name = f"{p.stem}.{digest}{p.suffix}"
    return name if str(p.parent) == "." else f"{p.parent}/{name}"


class StaticFingerprinter:
    """Content-hash URLs for every file the ``/static`` mounts serve (#1793).

    Built once per app at boot (``system_routes``) and shared by the chrome
    resolver, the static file server (``@import`` rewriting) and the renderer
    registry (``RendererRegistry.asset_url``). Digests are cached per resolved
    path for the process lifetime.
    """

    def __init__(
        self,
        static_dirs: Iterable[Path],
        themes_dir: Path | None = None,
        *,
        active_development: bool = False,
        env: str | None = None,
    ) -> None:
        self.static_dirs: tuple[Path, ...] = tuple(Path(d) for d in static_dirs)
        self.themes_dir = themes_dir
        self.enabled = should_fingerprint(active_development=active_development, env=env)
        self._digests: dict[Path, str] = {}

    @classmethod
    def for_project(
        cls,
        project_root: Path | str | None,
        *,
        active_development: bool = False,
        extra_static_dirs: Iterable[Path | str] | None = None,
    ) -> "StaticFingerprinter":
        """The fingerprinter matching the mounts ``_mount_static_files`` creates."""
        themes = Path(project_root) / "themes" if project_root else None
        return cls(
            static_root_dirs(project_root, extra_static_dirs),
            themes,
            active_development=active_development,
        )

    # -- resolution -------------------------------------------------------

    def resolve(self, rel: str) -> Path | None:
        """The file a ``/static/<rel>`` request is served from, or None.

        ``themes/<name>.css`` resolves under the project themes dir (the
        ``/static/themes`` mount, #1330); everything else under the first
        static dir holding it — the same precedence as the mounts.
        """
        rel = rel.lstrip("/")
        if not rel or ".." in PurePosixPath(rel).parts:
            return None
        if rel.startswith(_THEMES_PREFIX) and self.themes_dir is not None:
            candidate = self.themes_dir / rel.removeprefix(_THEMES_PREFIX)
            return candidate if candidate.is_file() else None
        for root in self.static_dirs:
            candidate = root / rel
            if candidate.is_file():
                return candidate
        return None

    def _resolve_url(self, url: str) -> Path | None:
        if not url.startswith(_STATIC_PREFIX):
            return None
        return self.resolve(url.removeprefix(_STATIC_PREFIX))

    # -- digests ----------------------------------------------------------

    def digest(self, path: Path) -> str:
        """8-hex content digest of ``path`` folded with its ``@import`` chain."""
        return self._digest(path.resolve(), frozenset())

    def _digest(self, path: Path, visiting: frozenset[Path]) -> str:
        cached = self._digests.get(path)
        if cached is not None:
            return cached
        data = path.read_bytes()
        h = hashlib.sha256(data)
        if path.suffix == ".css":
            inner = visiting | {path}
            for url in self.css_import_urls(data.decode("utf-8", errors="replace")):
                target = self._resolve_url(url)
                if target is None:
                    continue
                target = target.resolve()
                if target in inner:
                    continue  # cyclic @import — the browser ignores it too
                h.update(self._digest(target, inner).encode())
        digest = h.hexdigest()[:8]
        self._digests[path] = digest
        return digest

    @staticmethod
    def css_import_urls(text: str) -> list[str]:
        """Absolute ``/static/...`` URLs a stylesheet ``@import``s, in order."""
        return [m.group(1) for m in _CSS_IMPORT_RE.finditer(text)]

    # -- URL rewriting ----------------------------------------------------

    def hashed(self, url: str) -> str:
        """``/static/<dir>/<stem><ext>`` → ``/static/<dir>/<stem>.<sha8><ext>``.

        Unchanged when fingerprinting is off, the URL isn't ``/static/``, it
        carries a query string or fragment, or no served file backs it.
        """
        if not self.enabled or not url.startswith(_STATIC_PREFIX) or "?" in url or "#" in url:
            return url
        path = self._resolve_url(url)
        if path is None:
            return url
        rel = url.removeprefix(_STATIC_PREFIX)
        return _STATIC_PREFIX + _hashed_name(rel, self.digest(path))

    def rewrite_css_imports(self, text: str) -> str:
        """Point a stylesheet's absolute ``/static/`` ``@import``s at their hashed
        URLs, keeping any ``layer()`` / ``supports()`` / media clause."""

        def _swap(m: re.Match[str]) -> str:
            url = m.group(1)
            return m.group(0).replace(url, self.hashed(url), 1)

        return _CSS_IMPORT_RE.sub(_swap, text)

    def path_url(self, path: Path) -> str | None:
        """The (hashed) ``/static/`` URL serving ``path``, or None when ``path``
        lies under no served directory."""
        resolved = path.resolve()
        roots: list[tuple[Path, str]] = [(d, "") for d in self.static_dirs]
        if self.themes_dir is not None:
            roots.insert(0, (self.themes_dir, _THEMES_PREFIX))
        for root, prefix in roots:
            try:
                rel = resolved.relative_to(root.resolve())
            except ValueError:
                continue
            return self.hashed(f"{_STATIC_PREFIX}{prefix}{rel.as_posix()}")
        return None

    def renderer_asset_url(self, renderer_name: str, asset: RendererAsset) -> str:
        """URL for a renderer-declared asset (#1132/#1793).

        ``cache="no-store"``, fingerprinting off or a missing file → the plain
        ``/static/dazzle-renderers/<renderer>/<filename>`` URL. A file under a
        served static dir → its hashed ``/static/`` URL there. Otherwise the
        hashed ``/static/dazzle-renderers/<renderer>/<stem>.<sha8><ext>``.
        """
        plain = asset_url(renderer_name, asset.path.name)
        if asset.cache == "no-store" or not self.enabled or not asset.path.is_file():
            return plain
        under_static = self.path_url(asset.path)
        if under_static is not None:
            return under_static
        return asset_url(renderer_name, _hashed_name(asset.path.name, self.digest(asset.path)))
