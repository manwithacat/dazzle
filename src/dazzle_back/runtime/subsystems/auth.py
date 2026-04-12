"""Auth routes subsystem.

Registers authentication routes (login/register/logout), social auth (OAuth2),
2FA routes, and JWT routes. Auth deps (AuthStore, AuthMiddleware, auth_dep,
optional_auth_dep) are set on SubsystemContext by DazzleBackendApp._setup_auth().
"""

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

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

    def _register_auth_routes(self, ctx: SubsystemContext) -> None:
        """Register login/register/logout, 2FA, and JWT auth routes."""
        from dazzle_back.runtime.auth import create_2fa_routes, create_auth_routes

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

        # Mount the magic link consumer router (general-purpose, production-safe)
        from dazzle_back.runtime.auth.magic_link_routes import create_magic_link_routes

        magic_link_router = create_magic_link_routes()
        ctx.app.include_router(magic_link_router)

        # 2FA routes
        twofa_router = create_2fa_routes(
            ctx.auth_store,
            database_url=ctx.database_url,
        )
        ctx.app.include_router(twofa_router)

        # SES webhook (if SES is configured)
        try:
            from dazzle_back.channels.ses_webhooks import register_ses_webhook

            register_ses_webhook(ctx.app)
        except Exception:
            logger.info("SES webhooks not available, skipping registration")

    def _init_social_auth(self, ctx: SubsystemContext) -> None:
        """Initialize social auth (OAuth2) if providers are configured."""
        if not ctx.auth_config or not ctx.auth_store:
            return

        # Check if OAuth providers are configured
        oauth_providers = getattr(ctx.auth_config, "oauth_providers", None)
        if not oauth_providers:
            return

        import os

        try:
            from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService
            from dazzle_back.runtime.social_auth import (
                SocialAuthService,
                create_social_auth_routes,
            )
            from dazzle_back.runtime.token_store import TokenStore
        except ImportError as e:
            logger.warning("Social auth dependencies not available: %s", e)
            return

        # Get JWT config from auth_config
        jwt_cfg = getattr(ctx.auth_config, "jwt", None)
        access_minutes = getattr(jwt_cfg, "access_token_minutes", 15) if jwt_cfg else 15
        refresh_days = getattr(jwt_cfg, "refresh_token_days", 7) if jwt_cfg else 7

        # Create JWT service
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
        self._jwt_service = JWTService(JWTConfig(**jwt_config_kwargs))

        # Create token store (PostgreSQL-only)
        if not ctx.database_url:
            logger.warning("Social auth requires DATABASE_URL for token storage")
            return
        self._token_store = TokenStore(
            database_url=ctx.database_url,
            token_lifetime_days=refresh_days,
        )

        # Build social auth config from manifest + environment
        social_config = self._build_social_auth_config(oauth_providers)
        if not social_config:
            logger.info("No OAuth providers configured with valid credentials")
            return

        # Create social auth service
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

        from dazzle_back.runtime.social_auth import SocialAuthConfig

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
