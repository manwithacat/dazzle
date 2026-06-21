"""Pure helpers for the in-app connection-creation form (#1342 — org-admin create surface).

The route layer (``connection_admin_routes``) stays thin: it does the RBAC gate, the org-fence,
and the store write. All the per-type field-shaping, validation, and config assembly lives here so
it is unit-testable without a request. NO network I/O and NO secret persistence happen here — the
SAML metadata fetch (SSRF-guarded) and the AES-GCM secret encryption are done by the caller via the
existing ``saml_metadata`` / ``store.create_connection`` seams.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def parse_group_map(text: str) -> dict[str, str]:
    """Parse a web ``"eng=engineer, ops=operator"`` text field → ``{"eng": "engineer", ...}``.

    Lenient by design (this is a free-text convenience field, not a structured input): blank and
    malformed pairs are skipped rather than rejecting the whole submission. Comma- or
    newline-separated. Mirrors the CLI ``_parse_group_map`` intent without raising on a stray comma.
    """
    mapping: dict[str, str] = {}
    for pair in text.replace("\n", ",").split(","):
        if "=" not in pair:
            continue
        group, role = pair.split("=", 1)
        group, role = group.strip(), role.strip()
        if group and role:
            mapping[group] = role
    return mapping


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
