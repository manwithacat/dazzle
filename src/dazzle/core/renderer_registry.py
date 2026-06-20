"""Framework renderer-name registry — usable before the runtime exists.

The set of default renderer names lives in `core` because link-time
validation (`build_appspec(..., known_renderers=...)`) happens during DSL
parsing, before any `RuntimeServices` container is constructed. The
runtime registration helper (`register_default_renderers` in
`dazzle.http.runtime.renderers.init`) imports `_DEFAULT_RENDERERS` from
here so the link-time validator and runtime registry stay in sync.

Projects extend the validator's known set via `[renderers] extra=[…]`
in `dazzle.toml` — call ``known_renderer_names(manifest)`` instead of
``default_renderer_names()`` whenever a manifest is reachable. See
#1116 and ``fixtures/custom_renderer/`` for the full extension path.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.manifest import ProjectManifest


_DEFAULT_RENDERERS: tuple[str, ...] = ("fragment",)


def default_renderer_names() -> set[str]:
    """Framework default renderer names — no runtime dependencies.

    Prefer ``known_renderer_names(manifest)`` for code paths that have a
    manifest available. This function exists for the narrow case where
    no manifest is reachable (tests, isolated parser invocations).
    """
    return set(_DEFAULT_RENDERERS)


def known_renderer_names(manifest: "ProjectManifest | None" = None) -> set[str]:
    """Framework defaults plus any project-declared extras (#1116).

    The DSL's link-time renderer-name validator should call this — not
    ``default_renderer_names()`` — so that projects can declare custom
    renderer names in ``dazzle.toml``::

        [renderers]
        extra = ["branch_compare", "cytoscape_graph"]

    The names returned here are the validation allowlist only. Runtime
    registration (handler attached to a name) is a separate step in app
    code via ``services.renderer_registry.register(name=…, handler=…)``.
    See ``fixtures/custom_renderer/`` for a worked example.
    """
    names = set(_DEFAULT_RENDERERS)
    if manifest is not None and manifest.renderers.extra:
        names.update(manifest.renderers.extra)
    return names
