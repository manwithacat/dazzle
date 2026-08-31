"""Leftover-honest SSO provider slugs (cycle 2242, oral #112).

Reuses leftover_honest_auth_error — declared catalog is google /
microsoft / apple (sso_config.SSO_PROVIDER_TOKENS). Initiate + callback
stay-put is inlined (clone ratchet vs leftover_auth_email_or_400).
"""

from typing import Any

from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_error
from dazzle.http.runtime.auth.sso_config import SSO_PROVIDER_TOKENS


def leftover_honest_sso_provider(raw: Any) -> str | None:
    """Valid declared SSO provider slugs ride. Leftover stays put (None).

    Leftover ``/auth/sso/zzz`` / ``ghost`` / ``unknown-provider`` on
    GET initiate used to invent ``303 /login?error=sso_provider_unknown``
    theater (catalog miss). The same leftover on GET callback invented
    the same error. Valid ``google`` / ``microsoft`` / ``apple`` ride. Absent /
    blank is first-visit (``""``). Well-formed slugs that are not
    configured still bounce ``sso_provider_unknown``. Distinct from
    leftover ``?connection=`` (oral #110), leftover ``?new=`` (oral
    #97), and leftover catalog picker (oral #69). Live login
    ``/auth/sso/{provider}`` (sso_views Continue-with buttons).
    Cycle 2242.
    """
    return leftover_honest_auth_error(raw, SSO_PROVIDER_TOKENS)
