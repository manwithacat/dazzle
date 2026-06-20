"""Native SAML 2.0 SP ConnectionProvider (auth Plan 5.i).

Implements the 4a ``ConnectionProvider`` seam for per-org SAML SSO with Dazzle as the
Service Provider (SP). ``initiate`` builds an SP-initiated AuthnRequest redirect;
``callback`` validates the IdP's SAML Response and returns an ``AssertedIdentity``.

**All XML parsing + signature validation is delegated to python3-saml** (``onelogin.saml2``)
with secure defaults — ``strict=True`` and ``wantAssertionsSigned=True`` — so an assertion
is trusted only when its XML signature verifies against the connection's configured IdP
certificate. We never parse, canonicalize, or verify XML ourselves: XXE, signature-wrapping,
and comment-truncation are the library's concern, not hand-rolled here.

python3-saml needs the native ``libxmlsec1`` and lives in the ``[saml]`` extra; it is
imported lazily inside ``_build_auth`` so the rest of the framework is unaffected until a
SAML connection is actually exercised. Replay protection: SP-initiated flows stash the
AuthnRequest id in the session and ``callback`` passes it to ``process_response``, which
enforces the InResponseTo↔request-id match (one-time, since the id is popped). The opt-in
IdP-initiated path (``allow_idp_initiated``) has no such binding, so it enforces one-time
assertion consumption instead (the ``saml_consumed_assertions`` cache). There is NO library
"reject unsolicited" setting — python3-saml only checks InResponseTo when given a request id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    register_provider,
)

_logger = logging.getLogger(__name__)

# One stable ACS (Assertion Consumer Service) URL per app — registered with the IdP.
_ACS_PATH = "/auth/saml/acs"
# One stable SLS (Single Logout Service) URL per app — for IdP-initiated SLO (#1342 A).
_SLS_PATH = "/auth/saml/sls"
# Session key carrying the AuthnRequest id across the IdP round-trip (InResponseTo).
_SESSION_REQUEST_ID = "saml_request_id"


@dataclass(frozen=True)
class SamlLogout:
    """Outcome of processing an IdP ``LogoutRequest`` at the SLS (#1342 A)."""

    name_id: str | None  # subject NameID (email, lowercased) — trustworthy only post-validation
    redirect_url: str | None  # LogoutResponse redirect back to the IdP, or None


_NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
_BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
_BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"

_DEFAULT_GROUPS_ATTR = "groups"


def _first(value: Any) -> str:
    """SAML attributes are lists; take the first string value (or ``""``)."""
    if isinstance(value, (list, tuple)):
        return str(value[0]).strip() if value else ""
    return str(value).strip() if value is not None else ""


class NativeSAMLProvider:
    """Native SAML SP via python3-saml. Stateless — settings are rebuilt per request
    from the connection's (DB-stored) config, so a rotated IdP cert takes effect at once."""

    ACS_PATH = _ACS_PATH

    def _acs_url(self, request: Any) -> str:
        return f"{str(request.base_url).rstrip('/')}{self.ACS_PATH}"

    def _sp_entity_id(self, connection: ConnectionRecord, request: Any) -> str:
        # Default the SP entityId to the ACS URL (a stable, unique SP identifier) unless
        # the connection pins one (some IdPs require a specific audience value).
        return (connection.config or {}).get("sp_entity_id") or self._acs_url(request)

    def _settings(self, connection: ConnectionRecord, request: Any) -> dict[str, Any]:
        cfg = connection.config or {}
        idp_entity_id = cfg.get("idp_entity_id")
        idp_sso_url = cfg.get("idp_sso_url")
        idp_cert = cfg.get("idp_x509_cert")
        missing = [
            name
            for name, val in (
                ("idp_entity_id", idp_entity_id),
                ("idp_sso_url", idp_sso_url),
                ("idp_x509_cert", idp_cert),
            )
            if not val
        ]
        if missing:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: missing required config {missing}"
            )
        settings: dict[str, Any] = {
            # strict=True is load-bearing: python3-saml only enforces signature +
            # condition validation in strict mode.
            "strict": True,
            "sp": {
                "entityId": self._sp_entity_id(connection, request),
                "assertionConsumerService": {
                    "url": self._acs_url(request),
                    "binding": _BINDING_POST,
                },
                "NameIDFormat": cfg.get("nameid_format") or _NAMEID_EMAIL,
            },
            "idp": {
                "entityId": idp_entity_id,
                "singleSignOnService": {"url": idp_sso_url, "binding": _BINDING_REDIRECT},
                "x509cert": idp_cert,
            },
            "security": {
                # Require the assertion to be signed — the anti-forgery control.
                "wantAssertionsSigned": True,
                "wantNameId": True,
                "requestedAuthnContext": False,
            },
        }
        # Replay protection is NOT a python3-saml setting (the library only enforces the
        # InResponseTo↔request_id match when we pass a non-None request_id — response.py).
        # So the SP side owns it: SP-initiated flows pin InResponseTo to the one-time
        # session-stashed AuthnRequest id (callback), and the opt-in IdP-initiated path
        # enforces one-time assertion consumption (the saml_consumed_assertions cache).
        # SP-signed AuthnRequests (#1342, feature C): when this connection has a stored SP
        # keypair + the sign_requests flag, give python3-saml the key/cert and ask it to
        # sign the AuthnRequest. This is ADDITIVE — the assertion-signature requirement
        # (wantAssertionsSigned) is unchanged, so the Response signature remains the trust anchor.
        sp_cert = cfg.get("sp_cert")
        sp_key = (connection.secrets or {}).get("sp_private_key")
        if cfg.get("sign_requests") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["authnRequestsSigned"] = True
            settings["security"]["signatureAlgorithm"] = (
                "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
            )
            settings["security"]["digestAlgorithm"] = "http://www.w3.org/2001/04/xmlenc#sha256"
        # Encrypted assertions (#1342, feature B): when enabled + keypair present, require
        # the assertion to be encrypted and give python3-saml the key to decrypt it. Shares
        # the keypair the sign_requests block may already have installed (set idempotently).
        # A plaintext assertion is then rejected — strict by design (operator enables the
        # IdP-side encryption first; the CLI warns).
        if cfg.get("encrypt_assertions") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["wantAssertionsEncrypted"] = True
        return settings

    def _request_data(
        self, request: Any, *, post_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = request.url
        return {
            "https": "on" if url.scheme == "https" else "off",
            "http_host": url.hostname or "",
            "script_name": url.path,
            "get_data": dict(request.query_params),
            "post_data": post_data or {},
        }

    def _build_auth(self, request_data: dict[str, Any], settings: dict[str, Any]) -> Any:
        """Construct the python3-saml auth object (lazy import — [saml] extra).

        Isolated so tests can substitute a fake without installing libxmlsec1."""
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        return OneLogin_Saml2_Auth(request_data, old_settings=settings)

    def _sp_only_settings(
        self, request: Any, connection: ConnectionRecord | None = None
    ) -> dict[str, Any]:
        """SP-only settings for metadata generation (#1342).

        No IdP section needed — the SP identity (ACS URL, entityId, NameID) is app-level,
        the same one registered with every IdP. entityId defaults to the ACS URL. When a
        ``connection`` with request-signing enabled is given, the metadata advertises its
        signing cert (public only) via a KeyDescriptor so the IdP can verify SP-signed
        AuthnRequests.
        """
        acs = self._acs_url(request)
        entity = self._sp_entity_id(connection, request) if connection is not None else acs
        settings: dict[str, Any] = {
            "strict": True,
            "sp": {
                "entityId": entity,
                "assertionConsumerService": {"url": acs, "binding": _BINDING_POST},
                # Advertise the SLS so an importing IdP knows where to send LogoutRequests
                # (IdP-initiated SLO, #1342 A). App-level + single-stable-URL, like the ACS.
                "singleLogoutService": {
                    "url": self._sls_url(request),
                    "binding": _BINDING_REDIRECT,
                },
                "NameIDFormat": _NAMEID_EMAIL,
            },
        }
        if connection is not None:
            cfg = connection.config or {}
            sp_key = (connection.secrets or {}).get("sp_private_key")
            wants_key = cfg.get("sign_requests") or cfg.get("encrypt_assertions")
            if wants_key and cfg.get("sp_cert") and sp_key:
                # python3-saml requires BOTH cert + key in the settings; the generated
                # metadata XML carries only the public cert (never the private key).
                settings["sp"]["x509cert"] = cfg["sp_cert"]
                settings["sp"]["privateKey"] = sp_key
                security: dict[str, Any] = {}
                # authnRequestsSigned drives the AuthnRequestsSigned metadata attr + signing
                # KeyDescriptor; only when signing is actually on.
                if cfg.get("sign_requests"):
                    security["authnRequestsSigned"] = True
                # get_sp_metadata adds the use="encryption" KeyDescriptor ONLY when
                # wantAssertionsEncrypted (or wantNameIdEncrypted) is set — the cert alone
                # is not enough — so set it to advertise the SP encryption cert to the IdP.
                if cfg.get("encrypt_assertions"):
                    security["wantAssertionsEncrypted"] = True
                if security:
                    settings["security"] = security
        return settings

    def _build_sp_settings(self, settings: dict[str, Any]) -> Any:
        """Construct the python3-saml Settings object in SP-validation-only mode
        (lazy import — [saml] extra). Isolated so tests can fake it without
        installing libxmlsec1, mirroring ``_build_auth``."""
        from onelogin.saml2.settings import OneLogin_Saml2_Settings

        return OneLogin_Saml2_Settings(settings, sp_validation_only=True)

    def sp_metadata(self, request: Any, connection: ConnectionRecord | None = None) -> str:
        """Generate this SP's SAML metadata XML for IdP import (#1342).

        When ``connection`` has request-signing enabled, the metadata advertises its
        signing KeyDescriptor (public cert only — never the private key).

        The IdP imports this instead of an operator hand-configuring the ACS URL /
        entityId / NameID. SP-only generation (no IdP config), validated before
        return so we never serve malformed metadata. Contains nothing secret —
        only the public SP identity (entityId, ACS URL, NameID).

        Two deliberate limitations:
        - Serves the **default, app-level** SP identity (entityId = ACS URL). A
          connection that pins a custom ``sp_entity_id`` is not reflected here; its
          IdP must be configured with that pinned value directly.
        - entityId/ACS derive from ``request.base_url`` (Host header), exactly like
          the live login/ACS path. Front SAML deployments with a trusted-host /
          canonical base URL so the advertised ACS can't be Host-spoofed.
        """
        settings = self._build_sp_settings(self._sp_only_settings(request, connection))
        metadata = settings.get_sp_metadata()
        errors = settings.validate_metadata(metadata)
        if errors:
            raise RuntimeError(f"generated SP metadata failed validation: {errors}")
        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata

    async def initiate(self, connection: ConnectionRecord, request: Any) -> str:
        """Begin SP-initiated SSO — return the IdP redirect URL (carrying the
        AuthnRequest). Stashes the request id in the session for InResponseTo checking."""
        settings = self._settings(connection, request)
        auth = self._build_auth(self._request_data(request), settings)
        url: str = auth.login()
        request_id = auth.get_last_request_id()
        if request_id is not None and hasattr(request, "session"):
            request.session[_SESSION_REQUEST_ID] = request_id
        return url

    async def callback(self, connection: ConnectionRecord, request: Any) -> AssertedIdentity:
        """Validate the POSTed SAML Response and assert the verified identity.

        Signature + condition validation is python3-saml's job; we only proceed when it
        reports no errors AND an authenticated subject, then enforce identity invariants.
        """
        form = await request.form()
        post_data = {
            "SAMLResponse": form.get("SAMLResponse"),
            "RelayState": form.get("RelayState"),
        }
        settings = self._settings(connection, request)
        auth = self._build_auth(self._request_data(request, post_data=post_data), settings)

        request_id = (
            request.session.pop(_SESSION_REQUEST_ID, None) if hasattr(request, "session") else None
        )
        allow_idp_initiated = (
            str((connection.config or {}).get("allow_idp_initiated", "")).lower() == "true"
        )
        if not request_id and not allow_idp_initiated:
            # No stashed AuthnRequest id and this connection has NOT opted into IdP-initiated →
            # unsolicited / replayed / lost-session response. Passing request_id=None would make
            # python3-saml SKIP the InResponseTo check, so we refuse: only a flow we started
            # (its id in the session) is accepted.
            raise ConnectionError(
                f"SAML connection {connection.id!r}: no AuthnRequest id in session — "
                "only SP-initiated flows are accepted (unsolicited/replayed responses refused)"
            )
        idp_initiated = not request_id  # implies allow_idp_initiated (guarded above)

        # request_id pins InResponseTo (None on the opted-in IdP-initiated path). python3-saml
        # only enforces the InResponseTo↔request_id match when request_id is non-None, so on the
        # IdP-initiated path that binding is intentionally absent — signature/audience/recipient/
        # conditions are STILL enforced, and replay is closed by one-time assertion consumption
        # below (NOT by any library "reject unsolicited" setting — that isn't a real python3-saml
        # option). Library validation failures are recorded in get_errors(); malformed input (bad
        # base64/XML) can RAISE — normalize either to a clean refusal so a bad response never
        # yields an identity or a 500 stack trace.
        try:
            auth.process_response(request_id=request_id)
            errors = auth.get_errors()
            authenticated = auth.is_authenticated()
        except ConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 — any library failure ⇒ refuse, never assert
            raise ConnectionError(
                f"SAML connection {connection.id!r}: response validation failed ({exc})"
            ) from exc
        if errors or not authenticated:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: response validation failed ({errors})"
            )

        if idp_initiated:
            # The IdP-initiated path lacks the one-time session request-id replay defense, so
            # enforce one-time assertion consumption instead. The assertion's other guarantees
            # (signature/audience/conditions) were validated by process_response above.
            self._enforce_idp_initiated_replay(connection, request, auth)

        attributes = auth.get_attributes() or {}
        email = self._extract_email(connection, auth, attributes)
        if not email:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: assertion carried no email/NameID"
            )
        groups = self._extract_groups(connection, attributes)
        return AssertedIdentity(
            email=email, attributes=attributes, groups=groups, claims_source="saml_assertion"
        )

    def _enforce_idp_initiated_replay(
        self, connection: ConnectionRecord, request: Any, auth: Any
    ) -> None:
        """One-time-use guard for an IdP-initiated assertion: reject if its id was already consumed
        within its validity window (replay). Refuses if the assertion carries no id (can't protect)."""
        assertion_id = auth.get_last_assertion_id()
        if not assertion_id:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: IdP-initiated assertion had no id — "
                "cannot replay-protect, refusing"
            )
        # The assertion's NotOnOrAfter bounds the replay window; fall back to a short window if the
        # IdP omitted it (process_response already validated conditions, so this is belt-and-braces).
        expires_at = (
            auth.get_last_assertion_not_on_or_after()
            or (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        )
        store = request.app.state.auth_store
        if not store.record_consumed_assertion(
            str(assertion_id),
            connection_id=connection.id,
            tenant_id=connection.tenant_id,
            expires_at=str(expires_at),
        ):
            raise ConnectionError(
                f"SAML connection {connection.id!r}: SAML assertion already consumed "
                "(IdP-initiated replay refused)"
            )

    def _extract_email(
        self, connection: ConnectionRecord, auth: Any, attributes: dict[str, Any]
    ) -> str:
        cfg = connection.config or {}
        attr = cfg.get("email_attribute")
        if attr and attr in attributes:
            return _first(attributes[attr]).lower()
        # Fall back to the NameID (emailAddress format is the SP default).
        return str(auth.get_nameid() or "").strip().lower()

    def _extract_groups(
        self, connection: ConnectionRecord, attributes: dict[str, Any]
    ) -> list[str]:
        # Group overage (#1342 schools-gap): when a user is in too many groups (Entra caps the
        # SAML groups claim at 150) the IdP OMITS the groups and emits a `…groups.link` overage
        # indicator pointing at Graph instead. The member then arrives with no groups → no
        # group-derived roles, silently. Log loudly rather than under-grant without a signal.
        if any(str(k).lower().endswith("groups.link") for k in attributes):
            _logger.warning(  # nosemgrep
                "SAML connection %s: group overage — the IdP truncated the groups claim "
                "(too many groups); this member's group-derived roles may be incomplete. Use "
                "IdP app-role assignment or reduce the group count for this app.",
                connection.id,
            )
        attr = (connection.config or {}).get("groups_attribute") or _DEFAULT_GROUPS_ATTR
        raw = attributes.get(attr) or []
        if isinstance(raw, (list, tuple)):
            return [str(g).strip() for g in raw if g is not None and str(g).strip()]
        return [str(raw).strip()] if str(raw).strip() else []

    # ---- Single Logout (IdP-initiated, #1342 feature A) ----

    def _sls_url(self, request: Any) -> str:
        return f"{str(request.base_url).rstrip('/')}{_SLS_PATH}"

    def _slo_settings(self, connection: ConnectionRecord, request: Any) -> dict[str, Any]:
        """Settings for processing an IdP ``LogoutRequest``: the standard SP/IdP blocks plus
        the SLS endpoints and ``wantMessagesSigned`` (reject an unsigned/forged
        LogoutRequest — the load-bearing anti-forgery control; python3-saml validates the
        signature against ``idp.x509cert``). Signs the LogoutResponse when this connection
        has request-signing enabled (reuses feature C's SP keypair)."""
        settings = self._settings(connection, request)
        cfg = connection.config or {}
        settings["sp"]["singleLogoutService"] = {
            "url": self._sls_url(request),
            "binding": _BINDING_REDIRECT,
        }
        if cfg.get("idp_slo_url"):
            settings["idp"]["singleLogoutService"] = {
                "url": cfg["idp_slo_url"],
                "binding": _BINDING_REDIRECT,
            }
        settings["security"]["wantMessagesSigned"] = True
        sp_cert = cfg.get("sp_cert")
        sp_key = (connection.secrets or {}).get("sp_private_key")
        if cfg.get("sign_requests") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["logoutRequestSigned"] = True
            settings["security"]["logoutResponseSigned"] = True
        return settings

    def _logout_request_nameid(self, saml_request: str) -> str | None:
        """Extract the subject NameID from a Redirect-binding ``LogoutRequest``. Isolated as
        a seam (like ``_build_auth``) so tests can fake it without real signed XML. ONLY the
        caller's post-validation use makes this trustworthy — never act on it before
        ``process_slo`` reports no errors."""
        if not saml_request:
            return None
        from onelogin.saml2.logout_request import OneLogin_Saml2_Logout_Request
        from onelogin.saml2.utils import OneLogin_Saml2_Utils

        xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(saml_request)
        nameid: str | None = OneLogin_Saml2_Logout_Request.get_nameid(xml)
        return nameid

    def process_logout(self, connection: ConnectionRecord, request: Any) -> SamlLogout:
        """Validate an IdP ``LogoutRequest`` (signature, via ``process_slo``) and return the
        subject NameID + the LogoutResponse redirect. Raises ``ConnectionError`` on ANY
        validation error — fail-closed; the caller must not touch a session in that case."""
        settings = self._slo_settings(connection, request)
        request_data = self._request_data(request)
        auth = self._build_auth(request_data, settings)
        try:
            redirect_url = auth.process_slo(keep_local_session=True)
            errors = auth.get_errors()
        except ConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 — any library failure ⇒ refuse, never act
            raise ConnectionError(
                f"SAML connection {connection.id!r}: logout validation failed ({exc})"
            ) from exc
        if errors:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: logout validation failed ({errors})"
            )
        # The NameID is trustworthy ONLY now — after process_slo verified the signature.
        saml_request = (request_data.get("get_data") or {}).get("SAMLRequest", "")
        name_id = self._logout_request_nameid(saml_request)
        return SamlLogout(
            name_id=(name_id or "").strip().lower() or None, redirect_url=redirect_url
        )

    def _post_logout_url(self, request: Any) -> str:
        return f"{str(request.base_url).rstrip('/')}/"

    def initiate_logout(self, connection: ConnectionRecord, request: Any, *, name_id: str) -> str:
        """Build an SP-initiated ``LogoutRequest`` and return the redirect to the IdP SLO
        (#1342 SP-SLO). Signs the request when request-signing is on (reuses ``_slo_settings``
        / feature C's keypair). Raises ``ConnectionError`` when the connection has no
        ``idp_slo_url`` — the caller falls back to plain local logout."""
        if not (connection.config or {}).get("idp_slo_url"):
            raise ConnectionError(
                f"SAML connection {connection.id!r}: no idp_slo_url — cannot SP-initiate logout"
            )
        settings = self._slo_settings(connection, request)
        auth = self._build_auth(self._request_data(request), settings)
        return str(auth.logout(name_id=name_id, return_to=self._post_logout_url(request)))


def register_native_saml() -> None:
    """Register the native SAML provider for ``(saml, native)`` (called at startup)."""
    register_provider("saml", "native", NativeSAMLProvider())
