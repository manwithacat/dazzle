"""Leftover-honest OAuth authorization codes / state (cycle 2243, oral #113).

Leaf helper — no fragment / route imports so SSO + enterprise
callbacks can hoist it without pulling the typed-view substrate.
Charset is broader than leftover_honest_auth_token: IdP codes
often carry ``/`` ``+`` ``=`` ``.`` (Google ``4/0A…``).
"""

import re
from typing import Any

# RFC 6749 VSCHAR subset used by IdP authorization codes + state.
# Min 16 so leftover ``zzz`` / ``ghost`` / ``fake-code`` stay put.
_OAUTH_CODE = re.compile(r"\A[A-Za-z0-9_./+=-]{16,512}\Z")


def leftover_honest_oauth_code(raw: Any) -> str | None:
    """Valid IdP authorization codes / state ride. Leftover stays put (None).

    Leftover ``?code=zzz`` / ``ghost`` on GET
    ``/auth/sso/{provider}/callback`` used to invent
    ``303 /login?error=sso_failed`` theater (authlib exchange
    miss). The same leftover on GET ``/auth/enterprise/callback``
    invented the same theater. Leftover ``?state=zzz`` did too.
    Valid opaque IdP codes (urlsafe + ``/+=.``, length 16–512)
    ride. Absent / blank is first-visit (``""`` — stray callback
    / cancel still bounces ``sso_failed``). Well-formed codes
    that fail exchange still bounce ``sso_failed``. Distinct from
    leftover consume token (oral #109), leftover 2FA code (oral
    #108), leftover SSO provider (oral #112), and leftover
    ``?connection=`` (oral #110). Live simple_task
    ``/auth/sso/{provider}/callback``. Cycle 2243.
    """
    if raw is None:
        return ""
    if type(raw) is not str:
        return None
    text = raw.strip()
    if not text:
        return ""
    if _OAUTH_CODE.fullmatch(text):
        return text
    return None
