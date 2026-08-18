"""Leftover-honest 2FA codes (cycle 2238, oral #108).

Leaf helper — no fragment / route imports so JSON 2FA routes can
hoist it without pulling the typed-view substrate.
"""

from typing import Any

# TOTP / email-OTP are 6 digits (RFC 6238); some OTP lengths are 8.
# Recovery codes are 8 chars from generate_recovery_codes (XXXX-XXXX).
_2FA_RECOVERY_ALPHABET = frozenset("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def leftover_honest_2fa_code(raw: Any) -> str | None:
    """Valid TOTP / OTP / recovery codes ride. Leftover stays put (None).

    Leftover ``code=zzz`` / ``ghost`` / ``12abc`` on POST
    ``/auth/2fa/verify/submit`` used to invent
    ``303 /2fa/challenge?error=invalid_code`` theater (store miss /
    verify fail). The same leftover on JSON ``/auth/2fa/verify``
    invented ``401 Invalid 2FA code``. Digit codes (6–8) and
    recovery ``XXXX-XXXX`` ride. Absent / blank is first-visit
    (``""``). Well-formed codes that fail verify still bounce
    ``invalid_code``. Distinct from leftover 2FA mode (oral #92)
    and leftover 2FA sent (oral #94). Live simple_task
    ``/2fa/challenge``. Cycle 2238.
    """
    if raw is None:
        return ""
    if type(raw) is not str:
        return None
    text = raw.strip()
    if not text:
        return ""
    compact = "".join(ch for ch in text if ch not in " -")
    if not compact:
        return ""
    if compact.isdigit() and 6 <= len(compact) <= 8:
        return compact
    rec = compact.upper()
    if len(rec) == 8 and all(ch in _2FA_RECOVERY_ALPHABET for ch in rec):
        return f"{rec[:4]}-{rec[4:]}"
    return None
