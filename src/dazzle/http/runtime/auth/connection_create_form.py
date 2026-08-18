"""Pure helpers for the in-app connection-creation form (#1342 — org-admin create surface).

The route layer (``connection_admin_routes``) stays thin: it does the RBAC gate, the org-fence,
and the store write. All the per-type field-shaping, validation, and config assembly lives here so
it is unit-testable without a request. NO network I/O and NO secret persistence happen here — the
SAML metadata fetch (SSRF-guarded) and the AES-GCM secret encryption are done by the caller via the
existing ``saml_metadata`` / ``store.create_connection`` seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CONNECTION_TYPES = ("oidc", "scim", "saml", "domain")


@dataclass(frozen=True)
class CreatePlan:
    """A validated, ready-to-persist connection-creation request.

    ``config`` + ``secrets`` are exactly what ``store.create_connection`` expects. ``secrets`` is
    empty for SAML (the IdP cert is public) and for the *pre-mint* SCIM/OIDC plans — the route mints
    the SCIM bearer / injects the OIDC client_secret. ``show_bearer_once`` flags the SCIM case so the
    route renders the minted token exactly once."""

    type: str
    config: dict[str, str]
    group_mapping: dict[str, str]
    show_bearer_once: bool = False


class CreateFormError(ValueError):
    """A user-correctable problem with the submitted form (→ HTTP 400, never a 500)."""


def _declared_personas(declared: Any) -> set[str] | None:
    """Persona catalog, or None when leftover-shaped."""
    if declared is None:
        return set()
    if isinstance(declared, (str, bytes)):
        return None
    return {str(item).strip() for item in declared if str(item or "").strip()}


def _group_map_pair(piece: str) -> tuple[str, str] | None:
    """One ``group=persona`` pair, or None when leftover-shaped."""
    if "=" not in piece:
        return None
    group, role = piece.split("=", 1)
    group, role = group.strip(), role.strip()
    if not group or not role:
        return None
    return group, role


def leftover_honest_group_map(raw: Any, declared: Any = None) -> dict[str, str] | None:
    """Valid ``group=persona`` pairs ride. Leftover stays put (None).

    Leftover ``group_map=zzz`` / ``garbage`` / ``eng=zzz`` on
    ``POST /auth/connections/create`` used to skip malformed pairs
    (or persist leftover personas) and invent a connection. Valid
    pairs ride. Absent / blank is first-visit (``{}``). Rest is
    stay-put (None → 400, no write). Distinct from leftover
    ``?new=`` form-opener (oral #97) and leftover membership
    roles (oral #89). Live simple_task ``/auth/connections``.
    Cycle 2249.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}
    if not isinstance(raw, str):
        return None
    known = _declared_personas(declared)
    if known is None:
        return None
    mapping: dict[str, str] = {}
    for pair in raw.replace("\n", ",").split(","):
        piece = pair.strip()
        if not piece:
            continue
        parsed = _group_map_pair(piece)
        if parsed is None:
            return None
        group, role = parsed
        if known and role not in known:
            return None
        mapping[group] = role
    return mapping


def leftover_group_map_stay_put(raw: Any, declared: Any = None) -> bool:
    """True when leftover group_map would invent a persist (stay put)."""
    return leftover_honest_group_map(raw, declared) is None


def parse_group_map(text: str, declared: Any = None) -> dict[str, str]:
    """Parse a web ``"eng=engineer, ops=operator"`` text field → ``{"eng": "engineer", ...}``.

    Valid pairs ride. Leftover junk (malformed tokens, leftover
    personas when ``declared`` is set) stays put — raises
    ``CreateFormError`` so the create route does not invent a
    connection. Blank / absent is first-visit empty. Comma- or
    newline-separated. Cycle 2249 (oral #119).
    """
    honest = leftover_honest_group_map(text, declared)
    if honest is None:
        raise CreateFormError("Unknown group map")
    return honest


def _require(value: str, field_label: str) -> str:
    v = (value or "").strip()
    if not v:
        raise CreateFormError(f"{field_label} is required")
    return v


def plan_oidc(*, issuer: str, client_id: str, group_map: str) -> CreatePlan:
    issuer = _require(issuer, "Issuer URL")
    if not issuer.lower().startswith("https://"):
        raise CreateFormError("Issuer URL must be https://")
    client_id = _require(client_id, "Client id")
    return CreatePlan(
        type="oidc",
        config={"issuer": issuer, "client_id": client_id},
        group_mapping=parse_group_map(group_map),
    )


def plan_scim(*, group_map: str) -> CreatePlan:
    return CreatePlan(
        type="scim",
        config={},
        group_mapping=parse_group_map(group_map),
        show_bearer_once=True,
    )


def assemble_saml_config(
    *,
    metadata: dict[str, str] | None,
    idp_entity_id: str,
    idp_sso_url: str,
    idp_x509_cert: str,
    email_attribute: str = "",
    groups_attribute: str = "",
) -> dict[str, str]:
    """Build the SAML connection config from explicit fields and/or parsed metadata.

    Explicit fields override metadata (same precedence as the CLI ``create-saml``). Requires entity
    id + SSO URL + signing cert from one source or the other; raises ``CreateFormError`` listing what
    is still missing. ``metadata`` is the dict from ``parse_idp_metadata_xml`` (fetched by the route,
    SSRF-guarded), or ``None`` when only explicit fields were given.
    """
    md = metadata or {}
    entity_id = (idp_entity_id or md.get("idp_entity_id", "")).strip()
    sso_url = (idp_sso_url or md.get("idp_sso_url", "")).strip()
    cert = (idp_x509_cert or md.get("idp_x509_cert", "")).strip()

    missing = [
        name
        for name, val in (("entity id", entity_id), ("SSO URL", sso_url), ("signing cert", cert))
        if not val
    ]
    if missing:
        raise CreateFormError(
            f"Missing IdP {', '.join(missing)}. Provide a metadata URL, or the entity id, SSO URL, "
            "and signing cert explicitly."
        )

    config: dict[str, str] = {
        "idp_entity_id": entity_id,
        "idp_sso_url": sso_url,
        "idp_x509_cert": cert,
    }
    if md.get("idp_slo_url"):
        config["idp_slo_url"] = md["idp_slo_url"]
    if email_attribute.strip():
        config["email_attribute"] = email_attribute.strip()
    if groups_attribute.strip():
        config["groups_attribute"] = groups_attribute.strip()
    return config


def plan_saml(
    *,
    config: dict[str, str],
    group_map: str,
) -> CreatePlan:
    """Wrap an already-assembled SAML ``config`` (from ``assemble_saml_config``) into a plan."""
    return CreatePlan(type="saml", config=config, group_mapping=parse_group_map(group_map))


def plan_domain() -> CreatePlan:
    """A provider-less domain connection — no IdP config, no secrets, no group mapping.

    The resulting connection acts as a domain-ownership anchor: once a domain is claimed and
    verified against it, the org's join-policy (auto_join / admin_approval) governs member
    access without any SSO IdP in the loop.  The existing add-domain / verify-domain actions
    apply unchanged after creation.
    """
    return CreatePlan(type="domain", config={}, group_mapping={})
