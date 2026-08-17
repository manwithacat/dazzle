"""Single source of truth for same-origin redirect validation.

Consolidates the `_is_safe_redirect_path` helper that was previously duplicated
across five auth route modules (password_login, magic_link, sso, email_verification,
two_factor_form). One implementation removes the risk of a single copy drifting
into a real open redirect — exactly the bug class CodeQL's ``py/url-redirection``
warns about. Each route module imports this and keeps its local
``_is_safe_redirect_path`` name as a thin alias, so call sites are unchanged.
"""

from typing import Any
from urllib.parse import urlparse


def leftover_honest_auth_next(raw: Any) -> str | None:
    """Valid same-origin ``?next=`` rides. Leftover junk restores None.

    Leftover ``?next=zzz`` / ``https://evil.com`` used to invent the
    default landing (``/`` on GET login, ``/app`` on select-org) via
    omit-as-absent / fail-closed rewrite. Valid same-origin paths
    ride. Absent / blank / ``/`` is the honest first-visit default
    (``""``). Rest is stay-put (None). Distinct from leftover auth
    error (oral #95). Live simple_task ``/login``. Cycle 2222.
    """
    text = "" if raw is None else str(raw).strip()
    if not text or text == "/":
        return ""
    if is_safe_redirect_path(text):
        return text
    return None


def is_safe_redirect_path(value: str) -> bool:
    """Return ``True`` only for safe same-origin redirect targets.

    Rejects:

    1. **Backslashes** — browsers normalize ``\\`` to ``/`` per the WHATWG URL
       spec, so ``/\\evil.com`` can become a protocol-relative URL pointing at
       ``evil.com``. Reject explicitly before parsing.
    2. **Any scheme** (``http://``, ``https://``, ``javascript:``, ``data:`` …)
       — would escape the origin entirely.
    3. **Any netloc** (authority/host) — catches ``//evil.com`` (protocol-
       relative) and any input whose authority parses out.

    A safe value must then be a ``path`` beginning with ``/`` (absolute
    within-origin path, excluding the empty string).
    """
    if "\\" in value:
        return False
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return False
    return parsed.path.startswith("/")
