"""Connection activation diagnostics (auth Plan 4b.v).

``diagnose_connection`` reports exactly what an enterprise connection still needs to
go live — config-vs-missing plus an ordered activation runbook. This is the agent-
driven north-star: a human states the binary requirement ("this org needs Okta SSO")
and pays for infra; the agent reads this diagnosis and fills the gaps (or hands a
devops human the runbook).

Pure + deterministic: it takes the loaded connection plus three environment flags and
returns a structured report. It does **no** network I/O (no discovery fetch — no SSRF
surface) and **never** reads or echoes a secret *value* (only presence is checked).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CheckLevel = Literal["required", "recommended"]
CheckStatus = Literal["ok", "warn", "fail"]


def environment_flags() -> tuple[bool, bool, bool]:
    """(secret_key_ok, sso_extra_ok, dns_extra_ok) — the doctor's environment inputs.

    Shared by the CLI ``doctor`` and the org-admin readiness panel so the two can't
    drift. ``secret_key_ok`` = DAZZLE_CONNECTION_SECRET is a loadable 32-byte key.
    """
    from importlib.util import find_spec

    from dazzle.back.runtime.auth.connection_crypto import ConnectionSecretError, _load_key

    try:
        _load_key()
        secret_key_ok = True
    except ConnectionSecretError:
        secret_key_ok = False
    return secret_key_ok, find_spec("authlib") is not None, find_spec("dns") is not None


@dataclass(frozen=True)
class Check:
    """One diagnostic result. ``remedy`` is the concrete next action when not ``ok``."""

    name: str
    level: CheckLevel
    status: CheckStatus
    detail: str
    remedy: str = ""


@dataclass(frozen=True)
class Diagnosis:
    """The full report for a connection."""

    connection_id: str
    connection_type: str
    checks: tuple[Check, ...]

    @property
    def ready(self) -> bool:
        """True iff every *required* check passes (the connection can go live)."""
        return all(c.status == "ok" for c in self.checks if c.level == "required")

    @property
    def runbook(self) -> tuple[str, ...]:
        """Ordered remaining actions: every non-ok check's remedy (required first), then
        the two things this tool can't introspect — the IdP-side redirect URI and a
        live test."""
        failing = [c for c in self.checks if c.status != "ok" and c.remedy]
        failing.sort(key=lambda c: 0 if c.level == "required" else 1)
        steps = [c.remedy for c in failing]
        steps.append("Register this redirect URI with the IdP: <base_url>/auth/enterprise/callback")
        steps.append(
            f"Test: visit /auth/enterprise/login?connection={self.connection_id} "
            "(or ?email=<user@verified-domain>)"
        )
        return tuple(steps)


def _required(name: str, ok: bool, ok_detail: str, fail_detail: str, remedy: str) -> Check:
    return Check(
        name=name,
        level="required",
        status="ok" if ok else "fail",
        detail=ok_detail if ok else fail_detail,
        remedy="" if ok else remedy,
    )


def diagnose_connection(
    connection: Any,
    *,
    secret_key_ok: bool,
    sso_extra_ok: bool,
    dns_extra_ok: bool,
) -> Diagnosis:
    """Diagnose an OIDC connection's activation-readiness.

    ``secret_key_ok``  — ``DAZZLE_CONNECTION_SECRET`` is set to a valid 32-byte key.
    ``sso_extra_ok``   — authlib is importable (the OIDC dance + the [sso] extra).
    ``dns_extra_ok``   — dnspython is importable (needed for ``verify-domain``).

    For a non-OIDC connection type only the environment + a not-yet-supported note are
    returned (SCIM is 4c, SAML is Plan 5).
    """
    config = connection.config or {}
    secrets = connection.secrets or {}
    verified = [d for d in (connection.verified_domains or []) if d]
    claimed = [d for d in (connection.domains or []) if d]
    group_mapping = connection.group_mapping or {}

    checks: list[Check] = [
        _required(
            "secret_key",
            secret_key_ok,
            "DAZZLE_CONNECTION_SECRET is set and valid",
            "DAZZLE_CONNECTION_SECRET is missing/invalid — secrets can't be decrypted",
            'Set a 32-byte base64 key: python -c "import os,base64;'
            'print(base64.b64encode(os.urandom(32)).decode())" then export '
            "DAZZLE_CONNECTION_SECRET=<value> in the deployment env",
        ),
    ]

    if connection.type != "oidc":
        checks.append(
            Check(
                name="type",
                level="required",
                status="warn",
                detail=f"connection type {connection.type!r} is not yet diagnosable "
                "(SCIM is Plan 4c, SAML is Plan 5)",
            )
        )
        return Diagnosis(connection.id, connection.type, tuple(checks))

    checks.extend(
        [
            _required(
                "sso_extra",
                sso_extra_ok,
                "authlib is installed",
                "authlib is not installed — the OIDC flow can't run",
                "Install the SSO extra: pip install 'dazzle-dsl[sso]'",
            ),
            _required(
                "issuer_or_discovery",
                bool(config.get("issuer") or config.get("discovery_url")),
                "OIDC discovery configured",
                "no issuer or discovery_url in config",
                "Set config.issuer (e.g. https://idp.example) or config.discovery_url",
            ),
            _required(
                "client_id",
                bool(config.get("client_id")),
                "client_id is set",
                "config.client_id is missing",
                "Set config.client_id to the OAuth client id from the IdP",
            ),
            _required(
                # Presence only — the value is never read here.
                "client_secret",
                bool(secrets.get("client_secret")),
                "client_secret is present (encrypted at rest)",
                "no client_secret stored",
                "Recreate the connection with --client-secret (prefer the "
                "DAZZLE_OIDC_CLIENT_SECRET env var)",
            ),
            _required(
                "verified_domain",
                bool(verified),
                f"{len(verified)} verified domain(s): {', '.join(verified)}",
                "no verified domains — the connection routes nobody and asserts nobody",
                "Claim a domain (dazzle auth connection add-domain), publish its TXT "
                "record, then dazzle auth connection verify-domain",
            ),
            Check(
                name="dns_extra",
                level="recommended",
                status="ok" if dns_extra_ok else "warn",
                detail="dnspython is installed"
                if dns_extra_ok
                else "dnspython not installed — verify-domain can't run",
                remedy=""
                if dns_extra_ok
                else "Install the SSO extra: pip install 'dazzle-dsl[sso]'",
            ),
            Check(
                name="group_mapping",
                level="recommended",
                status="ok" if group_mapping else "warn",
                detail=f"{len(group_mapping)} group→role mapping(s)"
                if group_mapping
                else "no group→role mapping — members sign in with no app roles (default-deny)",
                remedy=""
                if group_mapping
                else "Add mappings at create time: --group-map <idp-group>=<role>",
            ),
        ]
    )

    # Claimed-but-unverified domains are a soft nudge (only matters when nothing is
    # verified yet, which the required check above already flags).
    unverified = [
        d for d in claimed if d.strip().lower() not in {v.strip().lower() for v in verified}
    ]
    if unverified:
        checks.append(
            Check(
                name="claimed_unverified",
                level="recommended",
                status="warn",
                detail=f"claimed but unverified: {', '.join(unverified)}",
                remedy="Publish each domain's TXT record then run "
                "dazzle auth connection verify-domain",
            )
        )

    return Diagnosis(connection.id, connection.type, tuple(checks))
