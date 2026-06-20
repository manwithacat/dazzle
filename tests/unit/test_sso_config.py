"""Unit tests for the SSO provider config loader (Phase 1.C)."""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from dazzle.http.runtime.auth.sso_config import (
    SsoProviderConfig,
    get_provider,
    load_sso_providers_from_env,
)


def test_config_rejects_empty_client_id() -> None:
    with pytest.raises(ValueError, match="client_id"):
        SsoProviderConfig(
            name="google",
            display_name="Google",
            client_id="",
            client_secret="x",
            discovery_url="https://example.com/.well-known/openid-configuration",
            scopes="openid",
        )


def test_config_rejects_empty_client_secret() -> None:
    with pytest.raises(ValueError, match="client_secret"):
        SsoProviderConfig(
            name="google",
            display_name="Google",
            client_id="abc",
            client_secret="",
            discovery_url="https://example.com/.well-known/openid-configuration",
            scopes="openid",
        )


# ───────────────── load_sso_providers_from_env ─────────────────


def test_no_env_means_no_providers() -> None:
    assert load_sso_providers_from_env(env={}) == ()


def test_google_env_pair_enables_google() -> None:
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_GOOGLE_CLIENT_ID": "google-id",
            "DAZZLE_SSO_GOOGLE_CLIENT_SECRET": "google-secret",
        }
    )
    assert len(providers) == 1
    p = providers[0]
    assert p.name == "google"
    assert p.client_id == "google-id"
    assert p.client_secret == "google-secret"
    assert "openid" in p.scopes
    assert urlparse(p.discovery_url).netloc.endswith("google.com")


def test_microsoft_env_pair_enables_microsoft() -> None:
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_MICROSOFT_CLIENT_ID": "ms-id",
            "DAZZLE_SSO_MICROSOFT_CLIENT_SECRET": "ms-secret",
        }
    )
    assert len(providers) == 1
    assert providers[0].name == "microsoft"
    assert providers[0].display_name == "Microsoft"
    assert urlparse(providers[0].discovery_url).netloc.endswith("microsoftonline.com")


def test_both_providers_enabled() -> None:
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_GOOGLE_CLIENT_ID": "g-id",
            "DAZZLE_SSO_GOOGLE_CLIENT_SECRET": "g-secret",
            "DAZZLE_SSO_MICROSOFT_CLIENT_ID": "m-id",
            "DAZZLE_SSO_MICROSOFT_CLIENT_SECRET": "m-secret",
        }
    )
    names = {p.name for p in providers}
    assert names == {"google", "microsoft"}


def test_partial_env_silently_omits_provider() -> None:
    """Missing client_secret → provider is silently skipped, not raised."""
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_GOOGLE_CLIENT_ID": "g-id",
            # no DAZZLE_SSO_GOOGLE_CLIENT_SECRET
        }
    )
    assert providers == ()


def test_blank_env_var_treated_as_unset() -> None:
    """A literal empty string is the same as a missing value."""
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_GOOGLE_CLIENT_ID": "  ",
            "DAZZLE_SSO_GOOGLE_CLIENT_SECRET": "secret",
        }
    )
    assert providers == ()


def test_scopes_env_overrides_default() -> None:
    providers = load_sso_providers_from_env(
        env={
            "DAZZLE_SSO_GOOGLE_CLIENT_ID": "id",
            "DAZZLE_SSO_GOOGLE_CLIENT_SECRET": "secret",
            "DAZZLE_SSO_GOOGLE_SCOPES": "openid email",  # narrower than default
        }
    )
    assert providers[0].scopes == "openid email"


# ───────────────── get_provider ─────────────────


def test_get_provider_returns_matching_config() -> None:
    class _State:
        sso_providers = (
            SsoProviderConfig(
                name="google",
                display_name="Google",
                client_id="x",
                client_secret="y",
                discovery_url="https://example/.well-known/openid-configuration",
                scopes="openid",
            ),
        )

    p = get_provider(_State(), "google")
    assert p is not None
    assert p.name == "google"


def test_get_provider_returns_none_for_unknown() -> None:
    class _State:
        sso_providers = ()

    assert get_provider(_State(), "google") is None


def test_get_provider_returns_none_when_state_lacks_attr() -> None:
    """Defensive: when the deployment hasn't wired up SSO yet, the
    lookup must not raise."""

    class _State:
        pass

    assert get_provider(_State(), "google") is None
