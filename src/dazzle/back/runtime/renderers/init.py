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

from dazzle.back.runtime.renderers.fragment import FragmentSurfaceRenderer
from dazzle.back.runtime.services import RuntimeServices
from dazzle.core.renderer_registry import _DEFAULT_RENDERERS


def register_default_renderers(services: RuntimeServices) -> None:
    """Register the framework default renderers on `services`.

    Calling twice on the same services raises `PrimitiveRegistrationError`
    because the registry rejects duplicate names. Tests should construct
    fresh `RuntimeServices` instances rather than reuse and re-register.
    """
    assert _DEFAULT_RENDERERS == ("fragment",), (
        "register_default_renderers must be updated when _DEFAULT_RENDERERS changes"
    )
    services.renderer_registry.register(name="fragment", handler=FragmentSurfaceRenderer())
