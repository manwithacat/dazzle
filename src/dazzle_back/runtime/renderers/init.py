"""Default renderer registration — called once at app startup.

`register_default_renderers(services)` populates the renderer registry with
the framework defaults. Post-#1051 (v0.67.85+) only the typed Fragment
renderer is registered — the legacy Jinja adapter was retired entirely
along with `render_fragment` / `render_surface`. Apps may register
additional renderers after this call.

`default_renderer_names()` returns the same set without requiring a
`RuntimeServices` instance — production `build_appspec` call sites use it
to populate `known_renderers=` for link-time validation, before the
`RuntimeServices` container itself is constructed.
"""

from dazzle_back.runtime.renderers.fragment import FragmentSurfaceRenderer
from dazzle_back.runtime.services import RuntimeServices

# Single source of truth: the framework default renderer set. Both the
# registration helper below and `default_renderer_names()` derive from this
# tuple, so the link-time validator and runtime registry can never disagree.
_DEFAULT_RENDERERS: tuple[str, ...] = ("fragment",)


def register_default_renderers(services: RuntimeServices) -> None:
    """Register the framework default renderers on `services`.

    Calling twice on the same services raises `PrimitiveRegistrationError`
    because the registry rejects duplicate names. Tests should construct
    fresh `RuntimeServices` instances rather than reuse and re-register.
    """
    services.renderer_registry.register(name="fragment", handler=FragmentSurfaceRenderer())


def default_renderer_names() -> set[str]:
    """The framework default renderer names, without instantiating services.

    Useful at `build_appspec` time — that call happens before the
    `RuntimeServices` container is built, so the runtime registry isn't yet
    populated. Production callers pass the result as `known_renderers=` to
    enable link-time validation of `render:` clauses against the same set
    that `register_default_renderers` will install moments later.
    """
    return set(_DEFAULT_RENDERERS)
