"""Member-admin authorization + orphan-guard helpers (auth Plan 3b).

Pure functions over a roster (a list of ``(membership_id, roles, status)``
tuples) so the last-admin guard is unit-testable without a DB. An org must never
be left with zero active members holding an ``org_admin_role`` — otherwise nobody
could manage it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dazzle.core.ir.identity import spec_display_id
from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_catalog_id,
    leftover_honest_catalog_option_values,
)


def _role_tokens(raw: Any) -> tuple[str, ...]:
    """Split a comma-separated or sequence role payload into tokens."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts: list[Any] = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        parts = [raw]
    out: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def declared_persona_ids(appspec: Any) -> tuple[str, ...]:
    """Declared persona ids from AppSpec (empty when no catalog)."""
    out: list[str] = []
    for persona in getattr(appspec, "personas", None) or ():
        pid = spec_display_id(persona, None, prefer="id") or ""
        if pid and pid not in out:
            out.append(pid)
    return tuple(out)


def leftover_honest_persona_roles(raw: Any, declared: Any) -> tuple[str, ...]:
    """Valid declared persona names ride. Leftover junk is omitted.

    Leftover ``roles=zzz`` used to persist invented personas on
    ``POST /auth/members/roles`` and invite. Valid declared names
    ride; leftover omitted. All leftover restores () so the
    caller stays put (no write). No declared catalog (test
    rigs) is pass-through. Live domain_join_co ``admin`` /
    ``member``. Cycle 2209.
    """
    tokens = _role_tokens(raw)
    known = leftover_honest_catalog_option_values(declared)
    if not known:
        return tokens
    out: list[str] = []
    for tok in tokens:
        honest = leftover_honest_catalog_id(tok, known, "", allow_empty_rest=True)
        if honest and honest not in out:
            out.append(honest)
    return tuple(out)


def leftover_persona_roles_stay_put(raw: Any, declared: Any) -> bool:
    """True when leftover junk would invent an empty grant (stay put)."""
    tokens = _role_tokens(raw)
    known = leftover_honest_catalog_option_values(declared)
    if not tokens or not known:
        return False
    return leftover_honest_persona_roles(raw, declared) == ()


def active_admins(
    roster: list[tuple[str, list[str], str]], admin_roles: Iterable[str]
) -> list[str]:
    """Membership ids that are ACTIVE and hold at least one persona in ``admin_roles`` (the
    resolved ``manage_members`` capability set)."""
    admin_set = set(admin_roles)
    return [mid for (mid, roles, status) in roster if status == "active" and admin_set & set(roles)]


def would_orphan_org(
    roster: list[tuple[str, list[str], str]],
    target_id: str,
    *,
    new_roles: list[str] | None,
    admin_roles: Iterable[str],
) -> bool:
    """True iff applying the change to ``target_id`` leaves the org with no member holding the
    ``manage_members`` capability.

    ``new_roles=None`` models removal or suspension (the target stops being an
    active admin). ``new_roles=[...]`` models a role change. Only blocks when the
    org currently HAS at least one admin and the change drops it to zero — an
    already-admin-less org can't be orphaned further.

    Concurrency caveat: this is a **point-in-time** check over a roster snapshot.
    The route reads the roster, calls this, then mutates in a separate
    transaction — so two near-simultaneous admin-on-admin mutations can each pass
    here and both apply, dropping the org to zero admins (a rare TOCTOU race). It
    guards the common single-actor case; a concurrently-orphaned org is recoverable
    out-of-band (platform superuser / DB-level role reassignment). A fully atomic
    guard (re-checking inside the mutation's advisory-locked transaction) is a
    deferred hardening — see the 3b plan / CHANGELOG.
    """
    before = active_admins(roster, admin_roles)
    if not before:
        return False  # nothing to orphan
    admin_set = set(admin_roles)
    after: list[str] = []
    for mid, roles, status in roster:
        if mid == target_id:
            if new_roles is None:
                continue  # removed / suspended → no longer an active admin
            if status == "active" and admin_set & set(new_roles):
                after.append(mid)
        elif status == "active" and admin_set & set(roles):
            after.append(mid)
    return len(after) == 0
