"""Primitive registration — the extensibility seam.

Framework primitives are registered in `primitives/__init__.py` at module
load. App-local primitives use `@primitive(name="...")` in `app/ui/primitives/`,
registering against `RuntimeServices.primitive_registry` (Plan 2 wires this
up). The DSL `render: <name>` clause resolves through the registry.
"""

import dataclasses
import functools
import hashlib
import pathlib
from collections.abc import Callable
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from dazzle.render.fragment.errors import PrimitiveRegistrationError

T = TypeVar("T", bound=type)


@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for registered renderers.

    Plan 5 unified the dispatch shape: every renderer adapter takes
    `(surface, ctx)` and returns an HTML string. Post-#1051 (v0.67.85+)
    only the typed FragmentSurfaceRenderer ships by default; custom
    renderers (e.g. cytoscape_3d, future PDF/native targets) just need
    to satisfy this protocol.

    The first parameter is intentionally `Any` rather than `SurfaceSpec`
    to avoid a circular import (this module is in `dazzle.render.fragment`,
    SurfaceSpec is in `dazzle.core.ir.surfaces`, and the latter imports
    nothing from this module — but the dependency direction across the
    package boundary is one we don't want to invert). The dispatcher's
    call site uses the typed SurfaceSpec; the protocol just structurally
    requires the right arity.

    The ``ctx`` argument is the dispatched render context:

    - For ``mode: list / view / create / edit`` the dispatcher passes
      ``dict[str, Any]`` with the existing ``table`` / ``detail`` /
      ``form`` sub-dicts (built by ``_build_dispatch_ctx``).
    - For ``mode: custom`` the dispatcher passes a typed
      ``CustomRenderCtx`` (#1129) — frozen dataclass exposing
      ``request`` / ``params`` / ``services`` / ``auth_ctx`` /
      ``surface_name`` / ``workspace_name``. Custom renderers can
      ``isinstance(ctx, CustomRenderCtx)`` to opt into the typed
      shape; the bare ``dict`` form remains accepted for back-compat
      with existing renderers that haven't migrated.
    """

    def render(self, surface: Any, ctx: Any) -> str: ...

    # ``assets`` is intentionally NOT declared on the Protocol — it's
    # an OPTIONAL method (#1132). ``RendererRegistry.collect_assets``
    # uses ``getattr(handler, "assets", None)`` to discover it; the
    # bare structural Protocol stays minimal so existing renderers
    # remain compliant without an empty no-op method.


class PrimitiveRegistry:
    """Mutable registry mapping primitive names to dataclass types.

    Not thread-safe; registration happens at module import time before
    serving begins. Resolution is read-only at request time.
    """

    def __init__(self) -> None:
        self._types: dict[str, type] = {}

    def register(self, name: str, cls: type) -> None:
        if not dataclasses.is_dataclass(cls):
            raise PrimitiveRegistrationError(f"primitive {name!r} must be a dataclass; got {cls!r}")
        if name in self._types:
            existing = self._types[name]
            raise PrimitiveRegistrationError(
                f"primitive {name!r} already registered to {existing!r}; "
                f"cannot re-register to {cls!r}"
            )
        self._types[name] = cls

    def resolve(self, name: str) -> type | None:
        return self._types.get(name)

    def registered_names(self) -> list[str]:
        return list(self._types.keys())


# Module-level default registry for framework primitives. App-local primitives
# pass their own registry via the decorator's `registry=` argument or wire up
# through RuntimeServices in Plan 2.
DEFAULT_REGISTRY = PrimitiveRegistry()


def primitive(
    *,
    name: str,
    registry: PrimitiveRegistry | None = None,
) -> Callable[[T], T]:
    """Decorator: register a dataclass as a Fragment primitive under `name`.

    Usage:

        @primitive(name="aegismark_kanban_board")
        @dataclass(frozen=True, slots=True)
        class AegismarkKanbanBoard:
            columns: tuple[KanbanColumn, ...]
    """
    target = registry if registry is not None else DEFAULT_REGISTRY

    def decorator(cls: T) -> T:
        target.register(name, cls)
        return cls

    return decorator


@dataclasses.dataclass(frozen=True, slots=True)
class RendererAsset:
    """#1132: declarative dependency from a renderer to a static file.

    Custom renderers that need to ship client-side JS/CSS used to
    inline it via ``RawHTML("<script>…</script>")`` (or, since
    #1130, via ``Script(body=…)``). Both shapes re-emit the same
    bytes on every page render — no browser caching, no CSP
    fingerprinting, no dedup across renderers that share a
    dependency.

    A ``Renderer`` implementation can declare ``assets() -> list[RendererAsset]``
    to register file-backed dependencies with the framework. The
    registry collects them at app boot via ``collect_assets``;
    server-side mount + URL generation is the project's
    responsibility for now (a future iteration can auto-mount under
    ``/static/dazzle-renderers/<renderer>/<filename>`` and inject
    the URLs into the page chrome).

    Attributes:
        path: Absolute or package-relative ``Path`` to the asset
            file on disk. The bundler reads from this path.
        kind: Asset kind — drives where the URL is emitted in the
            page chrome (``js`` → ``<script>`` deferred; ``css`` →
            ``<link rel="stylesheet">`` in head; ``wasm`` / ``json``
            are renderer-fetched, no head injection).
        cache: Caching strategy. ``fingerprint`` adds a content-hash
            query string for cache-busting; ``immutable`` adds a
            ``Cache-Control: immutable`` header at serve time;
            ``no-store`` opts out of caching entirely (dev mode).
        where: Whether the script/stylesheet URL lands in ``<head>``
            or just before ``</body>`` when auto-injected by the
            page chrome.
    """

    path: pathlib.Path
    kind: Literal["js", "css", "wasm", "json"]
    cache: Literal["fingerprint", "immutable", "no-store"] = "fingerprint"
    where: Literal["head", "body-end"] = "head"

    def __post_init__(self) -> None:
        if not isinstance(self.path, pathlib.Path):
            raise TypeError(
                f"RendererAsset.path expects pathlib.Path, got {type(self.path).__name__}"
            )
        if self.kind not in ("js", "css", "wasm", "json"):
            raise ValueError(f"RendererAsset.kind invalid: {self.kind!r}")


class RendererRegistry:
    """Mutable registry mapping renderer names to handler instances.

    Registration happens at startup; resolution at request-time. The
    resolved handler is the object whose `render(fragment, ctx)` method
    the dispatcher calls when an IR node carries `render: <name>`.

    Sibling to `PrimitiveRegistry` (in this module). Reuses
    `PrimitiveRegistrationError` for duplicate-name rejection so callers
    can catch one exception type for both registries.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Renderer] = {}

    def register(self, *, name: str, handler: Renderer) -> None:
        if name in self._handlers:
            existing = self._handlers[name]
            raise PrimitiveRegistrationError(
                f"renderer {name!r} already registered to {existing!r}; "
                f"cannot re-register to {handler!r}"
            )
        self._handlers[name] = handler

    def resolve(self, name: str) -> Renderer | None:
        return self._handlers.get(name)

    def registered_names(self) -> list[str]:
        return list(self._handlers.keys())

    def asset_url(
        self,
        renderer_name: str,
        filename: str,
        *,
        cache: Literal["fingerprint", "immutable", "no-store"] = "fingerprint",
    ) -> str:
        """#1137: registry-aware asset URL with cache-strategy resolution.

        When ``cache="fingerprint"`` (the default), looks up the
        registered ``RendererAsset`` by ``(renderer_name, filename)``,
        reads the file, hashes the contents to 8 hex chars, and
        appends ``?v=<hash>``. The hash is memoised module-level
        keyed by ``(renderer_name, filename)`` so request-time cost
        is O(1) after first access.

        When ``cache="immutable"`` or ``"no-store"``, returns the
        bare URL. ``immutable``'s ``Cache-Control: immutable`` header
        is the auto-mount's responsibility (future iteration).

        Falls back to the bare URL when the asset isn't registered
        (the caller may be referencing a manually-mounted file) or
        when the file is missing — neither should hard-fail page
        rendering. Missing files do trigger a stderr warning so the
        operator sees it in dev.
        """
        base = asset_url(renderer_name, filename)
        if cache != "fingerprint":
            return base
        path = self._asset_path(renderer_name, filename)
        if path is None or not path.exists():
            # Unknown asset or missing file — return bare URL. A
            # registered asset whose file vanishes is an operator
            # error, but it shouldn't crash render.
            return base
        # `_content_hash` is `functools.cache`d (keyed by path) — first request
        # hashes the file once; subsequent requests return the memoised digest.
        return f"{base}?v={_content_hash(path)}"

    def _asset_path(self, renderer_name: str, filename: str) -> pathlib.Path | None:
        """Look up the on-disk path for a (renderer, filename) pair."""
        handler = self._handlers.get(renderer_name)
        if handler is None:
            return None
        assets_fn = getattr(handler, "assets", None)
        if assets_fn is None:
            return None
        try:
            declared = assets_fn()
        except TypeError:
            return None
        for asset in declared:
            if isinstance(asset, RendererAsset) and asset.path.name == filename:
                return asset.path
        return None

    def collect_assets(self) -> list[tuple[str, RendererAsset]]:
        """#1132: walk every registered renderer, call ``assets()`` if
        defined, and return ``(renderer_name, asset)`` pairs.

        Renderers that don't implement ``assets()`` are skipped — the
        method is optional on the Protocol. Order is deterministic:
        registration order × declared-asset order. Deduplication is
        the caller's responsibility (the bundler dedups by content
        hash, not by ``Path`` identity — two renderers might declare
        different copies of the same library).
        """
        collected: list[tuple[str, RendererAsset]] = []
        for name, handler in self._handlers.items():
            assets_fn = getattr(handler, "assets", None)
            if assets_fn is None:
                continue
            try:
                declared = assets_fn()
            except TypeError:
                # ``assets`` exists on the instance but isn't callable
                # the way we expect — log and skip. A renderer with
                # a malformed assets attribute shouldn't crash the
                # whole app boot.
                continue
            for asset in declared:
                if not isinstance(asset, RendererAsset):
                    raise TypeError(
                        f"renderer {name!r}.assets() returned a non-RendererAsset "
                        f"entry: {asset!r}. Use the RendererAsset dataclass "
                        f"from dazzle.render.fragment."
                    )
                collected.append((name, asset))
        return collected


def asset_url(renderer_name: str, filename: str) -> str:
    """#1132: well-known URL for a renderer-declared asset.

    Renderers reference their declared assets in the rendered output
    via this helper, then either (a) project code mounts them under
    ``/static/dazzle-renderers/`` matching this convention, or (b) a
    future framework iteration auto-mounts them at boot.

    The path is deliberately lowercase / underscore-free / single-
    segment-per-name so it composes cleanly with FastAPI's
    ``StaticFiles`` mount points. Filename is interpolated raw —
    callers must not pass user-controllable input here.

    This is the registry-free shape (bare URL, no fingerprinting).
    Renderers that want content-hash cache-busting per the asset's
    declared ``cache="fingerprint"`` strategy should call
    ``RendererRegistry.asset_url(...)`` instead (#1137) — it has the
    registry context needed to look up the asset's on-disk path.
    """
    return f"/static/dazzle-renderers/{renderer_name}/{filename}"


# #1137/#1445: per-path memoisation via functools.cache (no module-level mutable
# dict + reset helper). First request for a path hashes the file once; subsequent
# requests return the memoised digest. Cache is process-lifetime — assets don't
# change without a restart. A test that mutates a fixture file calls
# `_content_hash.cache_clear()` to force a re-hash.
@functools.cache
def _content_hash(path: pathlib.Path) -> str:
    """SHA-256 of file contents, truncated to 8 hex chars.

    8 chars (32 bits) is enough collision resistance for cache-
    busting query strings — the goal is "different file → different
    URL", not cryptographic identity. Matches the
    ``asset_fingerprint`` helper's truncation length used elsewhere
    in the UI runtime.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8]
