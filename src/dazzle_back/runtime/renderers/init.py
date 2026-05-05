"""Default renderer registration — called once at app startup.

`register_default_renderers(services)` populates the renderer registry with
the framework defaults: Jinja (legacy path, stub adapter) and Fragment
(typed substrate from Plan 1). Apps may register additional renderers
after this call.
"""

from dazzle_back.runtime.renderers.fragment import FragmentRenderer
from dazzle_back.runtime.renderers.jinja import JinjaRenderer
from dazzle_back.runtime.services import RuntimeServices


def register_default_renderers(services: RuntimeServices) -> None:
    """Register the framework default renderers on `services`.

    Calling twice on the same services raises `PrimitiveRegistrationError`
    because the registry rejects duplicate names. Tests should construct
    fresh `RuntimeServices` instances rather than reuse and re-register.
    """
    services.renderer_registry.register(name="jinja", handler=JinjaRenderer())
    services.renderer_registry.register(name="fragment", handler=FragmentRenderer())
