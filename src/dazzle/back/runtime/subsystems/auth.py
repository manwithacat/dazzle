"""Auth routes subsystem.

Registers authentication routes (login/register/logout), social auth (OAuth2),
2FA routes, and JWT routes. Auth deps (AuthStore, AuthMiddleware, auth_dep,
optional_auth_dep) are set on SubsystemContext by DazzleBackendApp._setup_auth().
"""

import logging
from typing import Any

from dazzle.back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class AuthSubsystem:
    name = "auth_routes"

    def __init__(self) -> None:
        self._jwt_service: Any | None = None
        self._token_store: Any | None = None
        self._social_auth_service: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        if not ctx.enable_auth or not ctx.auth_store:
            return
        self._register_auth_routes(ctx)
        self._init_social_auth(ctx)
        # JWT bearer-token routes — mounted after social auth so we can
        # reuse the JWTService/TokenStore it built when OAuth is enabled.
        # Standalone JWT (no OAuth) also works — this method constructs
        # the service if social auth didn't (#1105).
        self._register_jwt_routes(ctx)

    def _register_auth_routes(self, ctx: SubsystemContext) -> None:
        """Register login/register/logout, 2FA, and JWT auth routes."""
        from dazzle.back.runtime.auth import create_2fa_routes, create_auth_routes

        # Build persona -> default_route mapping for post-login redirect
        _persona_routes: dict[str, str] = {}
        for p in ctx.config.personas:
            route = p.get("default_route")
            if route:
                _persona_routes[p["id"]] = route
        # Default signup role: first persona ID (public-facing persona by convention)
        _default_signup_roles = [ctx.config.personas[0]["id"]] if ctx.config.personas else None

        assert ctx.auth_store is not None, "auth_store must be set before AuthSubsystem starts"
        auth_router = create_auth_routes(
            ctx.auth_store,
            persona_routes=_persona_routes or None,
            default_signup_roles=_default_signup_roles,
        )
        ctx.app.include_router(auth_router)

        # Stash auth_store on app.state for routes that need it
        # (magic link consumer, qa_routes, etc.)
        ctx.app.state.auth_store = ctx.auth_store

        # auth Plan 1c — single-org auto-provision + the 1b memberships gate.
        # When on, activation lazily provisions one default org + membership
        # (invisible single-org), and a genuinely org-less identity routes to
        # /auth/no-orgs rather than the legacy proceed. Default off → unchanged
        # 1b behavior for existing apps.
        _auto_provision = bool(getattr(ctx.config, "auto_provision_single_org", False))
        ctx.app.state.single_org_auto_provision = _auto_provision
        # #1393 Phase A: declaring `tenant_host:` IMPLIES membership-gated login,
        # decoupled from auto_provision_single_org (closes the "passes auth, sees
        # empty screens" footgun). See `derive_memberships_required`.
        from dazzle.back.runtime.auth.org_activation import derive_memberships_required

        ctx.app.state.memberships_required = derive_memberships_required(
            ctx.appspec, auto_provision=_auto_provision
        )
        # auth Plan 3a: personas allowed to invite / manage org members
        # (fail-closed — empty means nobody can invite). Read by the invite route.
        _auth_cfg = getattr(ctx.config, "auth_config", None)
        ctx.app.state.org_admin_roles = list(getattr(_auth_cfg, "org_admin_roles", []) or [])
        # Admin-capability policy (manage_members / manage_connections). org_admin_roles is the
        # default for any unlisted capability, so apps that set only org_admin_roles are unchanged.
        from dazzle.back.runtime.auth.admin_policy import AdminPolicy, unknown_admin_personas

        _admin_caps = dict(getattr(_auth_cfg, "admin_capabilities", {}) or {})
        ctx.app.state.admin_policy = AdminPolicy.from_config(
            org_admin_roles=ctx.app.state.org_admin_roles,
            admin_capabilities=_admin_caps,
        )
        # Warn (don't fail) on personas referenced in the map that aren't declared — a typo would
        # silently grant nobody. ctx.config.personas is the declared-persona source (id-keyed).
        _declared = {p["id"] for p in (getattr(ctx.config, "personas", None) or []) if "id" in p}
        _unknown = unknown_admin_personas(_admin_caps, _declared)
        if _unknown:
            logger.warning(
                "auth.admin_capabilities references undeclared personas %s — those entries grant "
                "nobody. Declared personas: %s",
                sorted(_unknown),
                sorted(_declared),
            )
        # auth Plan 1d: expose the AppSpec for the activation path's 1:1 org<->
        # tenant-root mirror provisioning (archetype apps).
        ctx.app.state.appspec = ctx.appspec
        # auth Plan 3c.ii: expose the entity repositories so the /me/profile route
        # can resolve the profile entity's Repository at request time.
        ctx.app.state.repositories = getattr(ctx, "repositories", {}) or {}

        # Mount the magic link consumer router (general-purpose, production-safe)
        from dazzle.back.runtime.auth.magic_link_routes import create_magic_link_routes

        magic_link_router = create_magic_link_routes()
        ctx.app.include_router(magic_link_router)

        # Mount the email-verification router (#1109). Unconditionally
        # mounted — the endpoints carry an account-enumeration guard, so
        # they're safe to expose on deployments that don't actively
        # use verification yet. Apps opt in by setting
        # ``auth.require_email_verification`` and sending users through
        # ``POST /auth/send-verification`` after signup.
        from dazzle.back.runtime.auth.email_verification_routes import (
            create_email_verification_routes,
        )

        ctx.app.include_router(create_email_verification_routes())

        # Onboarding routes (v0.71.2) — completion + dismissal hooks
        # for guide-step overlays. Mounted only when the AppSpec
        # actually declares guides AND a DATABASE_URL is configured;
        # the route handlers reach for a repository on
        # `app.state.onboarding_state` which we populate in the same
        # block.
        # Defensive getattr — older AppSpec snapshots (and test fixtures
        # using SimpleNamespace stand-ins) may not carry the field yet.
        #
        # Tagged startup logs (#1118) — operators can grep
        # `onboarding.startup:` at deploy time to confirm whether the
        # repo got wired. Pairs with the `onboarding.inject:` tag
        # family in `_inject_onboarding_step`.
        guides_present = bool(getattr(ctx.appspec, "guides", None))
        db_url_present = bool(ctx.database_url)
        if guides_present and db_url_present:
            from dazzle.back.runtime.onboarding import (
                OnboardingStateRepository,
                create_onboarding_routes,
            )

            ctx.app.state.onboarding_state = OnboardingStateRepository(
                database_url=ctx.database_url,
            )
            ctx.app.include_router(create_onboarding_routes())
            logger.info(
                "onboarding.startup:repo-wired guides=%d database_url=set",
                len(getattr(ctx.appspec, "guides", []) or []),
            )
        else:
            # Don't wire repo or mount routes. If the deploy expected
            # guides to work, this log will say why they don't.
            logger.info(
                "onboarding.startup:repo-not-wired guides_present=%s "
                "database_url_present=%s (both must be true for the "
                "guide overlay to render at request time)",
                guides_present,
                db_url_present,
            )

        # Form-encoded password-reset routes (Phase 1.B.2, v0.67.31) —
        # typed-Fragment views in `auth_views.py` post to these endpoints
        # rather than the JSON ones in `routes.py`.
        from dazzle.back.runtime.auth.password_reset_routes import (
            create_password_reset_routes,
        )

        password_reset_router = create_password_reset_routes()
        ctx.app.include_router(password_reset_router)

        # Form-encoded password-mode login/signup routes (Phase 1.B.3,
        # v0.67.32). Mounted unconditionally — the typed-Fragment views
        # are only RENDERED when `app.state.auth_password_mode_enabled`
        # is True, but the endpoints themselves are safe to mount in
        # either mode (they just won't get traffic in magic-link-only
        # deployments).
        from dazzle.back.runtime.auth.password_login_routes import (
            create_password_login_routes,
        )

        password_login_router = create_password_login_routes()
        ctx.app.include_router(password_login_router)

        # Phase-2 org-context routes (auth Plan 1b): /auth/select-org,
        # /auth/switch-org, /auth/no-orgs. Mounted unconditionally — they
        # no-op (redirect to /login) for unauthenticated callers and only
        # matter once an identity has >1 membership.
        from dazzle.back.runtime.auth.org_context_routes import (
            create_org_context_routes,
        )

        ctx.app.include_router(create_org_context_routes())

        # auth Plan 3a: org invitations (invite / accept). Authz is fail-closed on
        # app.state.org_admin_roles; accept enforces the verified-email join rule.
        from dazzle.back.runtime.auth.invitation_routes import create_invitation_routes

        ctx.app.include_router(create_invitation_routes())

        # auth Plan 3b: member-admin surface (roster + role/suspend/remove). Each
        # mutation is admin-gated, cross-org-guarded, and last-admin-protected.
        from dazzle.back.runtime.auth.member_admin_routes import create_member_admin_routes

        ctx.app.include_router(create_member_admin_routes())

        # Org-admin connection surface: an org admin manages their org's connections in-app
        # (create OIDC/SCIM/SAML, claim + DNS-TXT verify domains), RBAC-gated + org-scoped.
        # Read surface is secret-free; creation accepts secrets (encrypted at rest) and shows a
        # minted SCIM bearer once. Gated on an active enterprise capability (#1342) — no
        # enterprise capability declared → no admin surface.
        if self._any_enterprise_active(ctx):
            from dazzle.back.runtime.auth.connection_admin_routes import (
                create_connection_admin_routes,
            )

            ctx.app.include_router(create_connection_admin_routes())

        # auth Plan 3c.ii: the member's own profile (archetype: profile) — get-or-
        # create by (active membership tenant, current_user.id), RLS-bound.
        from dazzle.back.runtime.auth.profile_routes import create_profile_routes

        ctx.app.include_router(create_profile_routes())

        # Phase E.2 — secret-gated contained QA-auth mint (#1339). Self-disabling:
        # the factory returns None unless QA_AUTH_SECRET is set, so prod is off by
        # default with no request-time flag to misconfigure. The mint enforces the
        # DB containment invariant (ADR-0035) — it can only scope a session into a
        # qa-namespaced, is_test, run-matched org.
        from dazzle.back.runtime.qa_secure_routes import create_qa_secure_routes

        _qa_secure = create_qa_secure_routes()
        if _qa_secure is not None:
            ctx.app.include_router(_qa_secure)
            logger.warning(
                "[QA-AUTH] secret-gated QA mint mounted at /qa/secure/mint "
                "(QA_AUTH_SECRET set) — ensure this deployment is a test instance"
            )

        # Form-encoded 2FA challenge submit routes (Phase 1.D.1,
        # v0.67.35) — the typed challenge view posts here instead of
        # the JSON `/auth/2fa/verify` endpoint, so the form works
        # without JS.
        from dazzle.back.runtime.auth.two_factor_form_routes import (
            create_two_factor_form_routes,
        )

        two_factor_form_router = create_two_factor_form_routes()
        ctx.app.include_router(two_factor_form_router)

        # SSO initiation + callback routes (Phase 1.C, v0.67.39).
        # Mounted unconditionally so the endpoint dispatcher can return
        # a friendly "sso_provider_unknown" redirect when SSO isn't
        # configured. The OAuth client is only constructed when a
        # registered provider is hit — `authlib` stays an optional dep.
        from dazzle.back.runtime.auth.sso_config import (
            load_sso_providers_from_env,
        )
        from dazzle.back.runtime.auth.sso_routes import create_sso_routes

        configured = load_sso_providers_from_env()
        ctx.app.state.sso_providers = configured

        # Enterprise (per-org) SSO connections (auth Plans 4b/4c/5) are gated on
        # declared opt-in capabilities (#1342): a route group mounts only when its
        # capability is *active* (declared in [capabilities] AND its extra installed).
        # A greenfield app declares nothing → no enterprise routes, even if the [sso]
        # extra happens to be installed. SCIM is included — no longer unconditional.
        any_enterprise = self._any_enterprise_active(ctx)

        # SessionMiddleware backs Authlib's `state` storage between the initiate
        # redirect and the callback (global-SSO + OIDC enterprise + SAML all need it —
        # SAML stashes the connection id + AuthnRequest id there for InResponseTo). The
        # session cookie is signed (not encrypted) via itsdangerous — fine for the
        # short-lived state token but DON'T put sensitive data in `request.session`.
        # The secret defaults to a random per-process value; production deployments
        # should set DAZZLE_SESSION_SECRET so the cookie survives restarts. Added at
        # most once, and only when something actually needs it (no blast radius for
        # non-SSO apps).
        if configured or any_enterprise:
            import os
            import secrets

            from starlette.middleware.sessions import SessionMiddleware

            session_secret = os.environ.get("DAZZLE_SESSION_SECRET") or secrets.token_urlsafe(64)
            ctx.app.add_middleware(
                SessionMiddleware,
                secret_key=session_secret,
                same_site="lax",
                https_only=False,  # cookie_secure() controls per-cookie
            )

        if configured:
            ctx.app.include_router(create_sso_routes())

        self._mount_enterprise_capabilities(ctx)
        self._register_capability_boot_guard(ctx)

        # 2FA routes — thread the AppSpec-level TwoFactorConfig through so
        # DSL authors can tune recovery-code count etc. at app-configuration
        # time (#838). When no SecurityConfig is present on the AppSpec, the
        # routes fall back to framework defaults via TwoFactorConfig().
        twofa_config = None
        if ctx.appspec.security is not None:
            twofa_config = ctx.appspec.security.two_factor
        twofa_router = create_2fa_routes(
            ctx.auth_store,
            database_url=ctx.database_url,
            two_factor_config=twofa_config,
        )
        ctx.app.include_router(twofa_router)

        # SES webhook (if SES is configured)
        try:
            from dazzle.back.channels.ses_webhooks import register_ses_webhook

            register_ses_webhook(ctx.app)
        except Exception:
            logger.info("SES webhooks not available, skipping registration")

    # Enterprise auth capability ids gated by the opt-in model (#1342).
    _ENTERPRISE_CAPABILITY_IDS = (
        "auth.enterprise.oidc",
        "auth.enterprise.saml",
        "auth.enterprise.scim",
    )

    def _any_enterprise_active(self, ctx: SubsystemContext) -> bool:
        """True iff any enterprise auth capability is active for this app (#1342)."""
        caps = getattr(ctx, "capabilities", None)
        return caps is not None and any(
            caps.is_active(cid) for cid in self._ENTERPRISE_CAPABILITY_IDS
        )

    def _register_capability_boot_guard(self, ctx: SubsystemContext) -> None:
        """Loud-log at startup if connection rows exist for a protocol whose enterprise
        capability isn't active (#1344) — their routes silently don't mount (SSO/SCIM 404).

        A startup hook (not build-time) because the DB pool only opens at lifespan startup;
        loud-log only (the lifespan registry swallows hook exceptions, and the mismatch is
        SAFE — aborting would crash-loop a safe deploy). Registered unconditionally: the whole
        point is to fire when a capability is *absent*."""
        from dazzle.back.runtime.auth.capability_guard import capability_boot_warnings
        from dazzle.back.runtime.lifespan_hooks import register_lifespan_hook

        store = getattr(ctx, "auth_store", None)
        if store is None:
            return
        caps = getattr(ctx, "capabilities", None)

        def _startup() -> None:
            is_active = caps.is_active if caps is not None else (lambda _cid: False)
            for msg in capability_boot_warnings(store.connection_type_counts(), is_active):
                logger.error("Capability boot guard: %s", msg)

        register_lifespan_hook(ctx.app, startup=_startup)

    def _mount_enterprise_capabilities(self, ctx: SubsystemContext) -> None:
        """Mount each enterprise auth route group gated on its capability (#1342)."""
        caps = getattr(ctx, "capabilities", None)
        if caps is None:
            return
        if caps.is_active("auth.enterprise.oidc"):
            self._mount_enterprise_sso(ctx)
        if caps.is_active("auth.enterprise.saml"):
            self._mount_saml(ctx)
        if caps.is_active("auth.enterprise.scim"):
            self._mount_scim(ctx)

    def _mount_enterprise_sso(self, ctx: SubsystemContext) -> None:
        """Register the native OIDC provider + mount the per-org enterprise routes.

        Registration is idempotent across app boots: the process-wide registry is
        keyed by (type, provider); per-connection authlib clients live inside the
        provider instance (keyed by connection id+revision), so no cross-app collision.
        """
        from dazzle.back.runtime.auth.enterprise_routes import (
            create_enterprise_sso_routes,
        )
        from dazzle.back.runtime.auth.oidc_provider import register_native_oidc

        register_native_oidc()
        ctx.app.include_router(create_enterprise_sso_routes())

    def _mount_saml(self, ctx: SubsystemContext) -> None:
        """Register the native SAML provider + mount the SAML routes.

        The ACS POST lives under the /auth/ CSRF-exempt prefix — correct, as its
        integrity is the signed assertion + InResponseTo, not a CSRF token.
        """
        from dazzle.back.runtime.auth.saml_provider import register_native_saml
        from dazzle.back.runtime.auth.saml_routes import create_saml_routes

        register_native_saml()
        ctx.app.include_router(create_saml_routes())

    def _mount_scim(self, ctx: SubsystemContext) -> None:
        """Mount the SCIM 2.0 provisioning endpoints (stateless bearer auth)."""
        from dazzle.back.runtime.auth.scim_routes import create_scim_routes

        ctx.app.include_router(create_scim_routes())

    def _ensure_jwt_service(self, ctx: SubsystemContext) -> bool:
        """Build (or reuse) JWTService + TokenStore, idempotently.

        Sets ``self._jwt_service`` and ``self._token_store`` on success.
        Returns ``True`` if both are now populated, ``False`` if a hard
        prerequisite is missing (e.g. no DATABASE_URL — TokenStore is
        Postgres-only). Safe to call multiple times.

        Used by both ``_init_social_auth`` and ``_register_jwt_routes``
        so the two paths share a single JWTService instance — refresh
        tokens issued via password login + ``/auth/token`` and via
        OAuth callback validate against the same key material (#1105).
        """
        if self._jwt_service is not None and self._token_store is not None:
            return True
        if not ctx.auth_config or not ctx.auth_store:
            return False
        if not ctx.database_url:
            return False

        import os

        try:
            # #1362: jwt_auth.py defers `import jwt` into method bodies, so
            # importing the module succeeds without PyJWT and the mounted
            # routes 500 at request time on a public endpoint. Probe the
            # real dependency here so a packaging regression fails loud at
            # boot (routes not mounted + warning) instead.
            import jwt  # noqa: F401

            from dazzle.back.runtime.jwt_auth import JWTConfig, JWTService
            from dazzle.back.runtime.token_store import TokenStore
        except ImportError as e:
            logger.warning(
                "JWT auth routes NOT mounted — dependency missing: %s. "
                "PyJWT is a core dependency as of v0.82.21 (#1362); this "
                "indicates a broken install.",
                e,
            )
            return False

        jwt_cfg = getattr(ctx.auth_config, "jwt", None)
        access_minutes = getattr(jwt_cfg, "access_token_minutes", 15) if jwt_cfg else 15
        refresh_days = getattr(jwt_cfg, "refresh_token_days", 7) if jwt_cfg else 7

        jwt_secret = os.getenv("JWT_SECRET")
        jwt_config_kwargs: dict[str, Any] = {
            "access_token_expire_minutes": access_minutes,
            "refresh_token_expire_days": refresh_days,
        }
        if jwt_secret:
            jwt_config_kwargs["secret_key"] = jwt_secret
        else:
            logger.warning(
                "JWT_SECRET not set — using auto-generated secret. "
                "Sessions will be invalidated on server restart. "
                "Set JWT_SECRET in your environment for production use."
            )

        if self._jwt_service is None:
            self._jwt_service = JWTService(JWTConfig(**jwt_config_kwargs))
        if self._token_store is None:
            self._token_store = TokenStore(
                database_url=ctx.database_url,
                token_lifetime_days=refresh_days,
            )
        return True

    def _register_jwt_routes(self, ctx: SubsystemContext) -> None:
        """Mount bearer-token auth routes (#1105).

        ``create_jwt_auth_routes`` was implemented and tested but never
        wired through the auth subsystem after #536 extracted it from
        the monolithic ``auth.py``. This method closes that gap: it
        ensures a ``JWTService`` + ``TokenStore`` exist (reusing the
        ones built by social auth when available) and registers the
        6 OAuth2-compatible endpoints (``/auth/token``,
        ``/auth/token/refresh``, ``/auth/token/revoke``,
        ``/auth/me/jwt``, ``/auth/sessions`` GET+DELETE).

        Gated on DATABASE_URL because TokenStore is Postgres-only.
        Routes 401 when ``JWT_SECRET`` is unset (auto-generated secret
        is fine for dev but the warning is logged on startup).
        """
        if not ctx.auth_config or not ctx.auth_store:
            return
        if not self._ensure_jwt_service(ctx):
            logger.info("JWT auth routes not mounted — DATABASE_URL or auth_store is missing")
            return

        try:
            from dazzle.back.runtime.auth import create_jwt_auth_routes
        except ImportError as e:
            logger.warning("JWT auth dependencies not available: %s", e)
            return

        assert self._jwt_service is not None  # narrowed by _ensure_jwt_service
        assert self._token_store is not None
        ctx.app.include_router(
            create_jwt_auth_routes(ctx.auth_store, self._jwt_service, self._token_store)
        )
        logger.info(
            "JWT auth routes mounted: /auth/token, /auth/token/refresh, "
            "/auth/token/revoke, /auth/me/jwt, /auth/sessions"
        )

    def _init_social_auth(self, ctx: SubsystemContext) -> None:
        """Initialize social auth (OAuth2) if providers are configured."""
        if not ctx.auth_config or not ctx.auth_store:
            return

        # Check if OAuth providers are configured
        oauth_providers = getattr(ctx.auth_config, "oauth_providers", None)
        if not oauth_providers:
            return

        try:
            from dazzle.back.runtime.social_auth import (
                SocialAuthService,
                create_social_auth_routes,
            )
        except ImportError as e:
            logger.warning("Social auth dependencies not available: %s", e)
            return

        # JWT + TokenStore are shared with _register_jwt_routes via _ensure_jwt_service.
        if not self._ensure_jwt_service(ctx):
            logger.warning("Social auth requires DATABASE_URL for token storage")
            return

        # Build social auth config from manifest + environment
        social_config = self._build_social_auth_config(oauth_providers)
        if not social_config:
            logger.info("No OAuth providers configured with valid credentials")
            return

        # Create social auth service
        assert self._jwt_service is not None  # narrowed by _ensure_jwt_service
        assert self._token_store is not None
        self._social_auth_service = SocialAuthService(
            auth_store=ctx.auth_store,
            jwt_service=self._jwt_service,
            token_store=self._token_store,
            config=social_config,
        )

        # Register social auth routes
        social_router = create_social_auth_routes(self._social_auth_service)
        ctx.app.include_router(social_router)

        # Log enabled providers
        enabled = []
        if social_config.google_client_id:
            enabled.append("google")
        if social_config.github_client_id:
            enabled.append("github")
        if social_config.apple_team_id:
            enabled.append("apple")

        if enabled:
            logger.info("Social auth enabled: %s", ", ".join(enabled))

    def _build_social_auth_config(self, oauth_providers: list[Any]) -> Any | None:
        """Build SocialAuthConfig from manifest oauth_providers.

        Reads credentials from environment variables specified in manifest.
        """
        import os

        from dazzle.back.runtime.social_auth import SocialAuthConfig

        config = SocialAuthConfig()
        any_configured = False

        for provider_cfg in oauth_providers:
            provider = provider_cfg.provider.lower()

            if provider == "google":
                client_id = os.getenv(provider_cfg.client_id_env)
                if client_id:
                    config.google_client_id = client_id
                    any_configured = True
                else:
                    logger.warning("Google OAuth: %s not set", provider_cfg.client_id_env)

            elif provider == "github":
                client_id = os.getenv(provider_cfg.client_id_env)
                client_secret = os.getenv(provider_cfg.client_secret_env)
                if client_id and client_secret:
                    config.github_client_id = client_id
                    config.github_client_secret = client_secret
                    any_configured = True
                else:
                    # Log which env vars are missing (names only, never values)
                    missing_names: list[str] = []
                    if not client_id:
                        missing_names.append("client_id")
                    if not client_secret:
                        missing_names.append("client_secret")
                    logger.warning(
                        "GitHub OAuth: missing env vars for %s",
                        ", ".join(missing_names),
                    )

            elif provider == "apple":
                # Apple requires team_id, key_id, private_key, bundle_id
                # These would need extended manifest schema
                logger.warning(
                    "Apple OAuth: requires extended configuration "
                    "(team_id, key_id, private_key, bundle_id)"
                )

            else:
                logger.warning("Unknown OAuth provider: %s", provider)

        return config if any_configured else None

    def shutdown(self) -> None:
        pass
