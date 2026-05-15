"""Framework renderer-name registry — usable before the runtime exists.

The set of default renderer names lives in `core` because link-time
validation (`build_appspec(..., known_renderers=...)`) happens during DSL
parsing, before any `RuntimeServices` container is constructed. The
runtime registration helper (`register_default_renderers` in
`dazzle.back.runtime.renderers.init`) imports `_DEFAULT_RENDERERS` from
here so the link-time validator and runtime registry stay in sync.
"""

_DEFAULT_RENDERERS: tuple[str, ...] = ("fragment",)


def default_renderer_names() -> set[str]:
    """Framework default renderer names — no runtime dependencies."""
    return set(_DEFAULT_RENDERERS)
