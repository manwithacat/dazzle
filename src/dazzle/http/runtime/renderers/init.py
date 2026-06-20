"""Default renderer registration — called once at app startup.

`register_default_renderers(services)` populates the renderer registry with
the framework defaults. Post-#1051 (v0.67.85+) only the typed Fragment
renderer is registered — the legacy Jinja adapter was retired entirely
along with `render_fragment` / `render_surface`. Apps may register
additional renderers after this call.

The framework default renderer-name set lives in
`dazzle.core.renderer_registry` (link-time validation needs it before
`RuntimeServices` exists). The runtime registry below installs the same
names.
"""

from dazzle.core.renderer_registry import _DEFAULT_RENDERERS
from dazzle.http.runtime.renderers.fragment import FragmentSurfaceRenderer
from dazzle.http.runtime.services import RuntimeServices


def register_default_renderers(services: RuntimeServices) -> None:
    """Register the framework default renderers on `services`.

    Calling twice on the same services raises `PrimitiveRegistrationError`
    because the registry rejects duplicate names. Tests should construct
    fresh `RuntimeServices` instances rather than reuse and re-register.
    """
    # Internal invariant: when a maintainer adds a framework-shipped
    # renderer, this function and `_DEFAULT_RENDERERS` must move together.
    # The assert protects framework devs from forgetting the second step.
    #
    # If you hit this as a project author trying to add your OWN renderer,
    # DO NOT mutate `_DEFAULT_RENDERERS` — that's a framework constant.
    # The project-side extension path is:
    #   1. `[renderers] extra = ["my_name"]` in dazzle.toml
    #   2. `services.renderer_registry.register(name="my_name", handler=…)`
    #      in your app factory or startup hook.
    # See fixtures/custom_renderer/ for a worked example, and #1116/#1117
    # for the design history.
    assert _DEFAULT_RENDERERS == ("fragment",), (
        "register_default_renderers is out of sync with _DEFAULT_RENDERERS. "
        "A framework default renderer was added to the tuple without a "
        "matching `services.renderer_registry.register(...)` call below. "
        "Project authors should NOT mutate _DEFAULT_RENDERERS — use "
        "`[renderers] extra` in dazzle.toml + a runtime register() call; "
        "see fixtures/custom_renderer/."
    )
    services.renderer_registry.register(name="fragment", handler=FragmentSurfaceRenderer())
