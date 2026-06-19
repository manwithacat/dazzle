"""#1420 Slice 1 — fail-closed guard for auth-disabled production deploys.

``enable_auth=False`` makes ``_setup_auth`` return no auth dependency, so generated
CRUD routes mount with no permit/scope enforcement — world-writable. That is an
ergonomic default for local dev but a critical misconfiguration in production
(a downstream hit it when an auth toggle was accidentally on in prod). This guard
refuses to boot in that case unless the operator explicitly acknowledges it.
"""

import logging
import os

logger = logging.getLogger("dazzle.server")

INSECURE_ACK_VAR = "DAZZLE_ALLOW_INSECURE_NO_AUTH"


class InsecureAuthConfigError(RuntimeError):
    """Raised at build when auth is disabled in production without acknowledgement."""


def assert_secure_auth_config(enable_auth: bool, *, production: bool, allow_insecure: bool) -> None:
    """Fail closed when production runs with auth disabled and unacknowledged."""
    if enable_auth or not production:
        return
    if allow_insecure:
        logger.warning(
            "Dazzle is running in PRODUCTION with auth DISABLED (acknowledged via %s=1). "
            "Generated CRUD routes carry NO permit/scope enforcement and are "
            "unauthenticated. This is intended only for a fully public deployment.",
            INSECURE_ACK_VAR,
        )
        return
    raise InsecureAuthConfigError(
        "Refusing to start: auth is disabled (enable_auth=False) but DAZZLE_ENV=production. "
        "Generated CRUD routes would be world-writable (no permit/scope enforcement). "
        "Enable auth ([auth] enabled=true in dazzle.toml), or set "
        f"{INSECURE_ACK_VAR}=1 to explicitly acknowledge an unauthenticated production deploy."
    )


def insecure_ack_from_env() -> bool:
    """True when DAZZLE_ALLOW_INSECURE_NO_AUTH is set truthy (1/true/yes)."""
    return os.environ.get(INSECURE_ACK_VAR, "").strip().lower() in ("1", "true", "yes")
