"""The signed-in principal handed to renderers (#1794).

A custom renderer (``Renderer.render(surface, ctx)``) that needs "my" rows used
to reach into ``dazzle.http.runtime.audit_context`` or the RLS contextvars for
the actor. The principal is now part of the renderer context contract:

- ``mode: custom`` surfaces get ``CustomRenderCtx.principal``;
- list / view / create / edit surfaces get ``ctx["principal"]``.

Both are ``None`` for an anonymous request. This module is a leaf (render layer,
no ``http`` import); the HTTP runtime builds the value from the request's auth
context with ``dazzle.http.runtime.auth.models.principal_of``.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request a renderer is serving.

    Attributes:
        user_id: The auth user id (the same value the framework binds as the
            audit actor for the request), as a string.
        roles: Effective roles with the ``role_`` prefix removed — the active
            membership's roles when there is one, else the user's roles.
        tenant_id: The active membership's tenant (organization) id, or
            ``None`` when the user acts outside a membership.
        email: The user's email.
        display_name: The user's human label (the auth ``username``), or
            ``None`` when unset.
    """

    user_id: str | None
    roles: tuple[str, ...] = ()
    tenant_id: str | None = None
    email: str | None = None
    display_name: str | None = None
