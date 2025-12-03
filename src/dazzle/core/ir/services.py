"""
Service types for DAZZLE IR.

This module contains external service specifications including
authentication profiles and API configurations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuthKind(str, Enum):
    """Authentication profile types."""

    OAUTH2_LEGACY = "oauth2_legacy"
    OAUTH2_PKCE = "oauth2_pkce"
    JWT_STATIC = "jwt_static"
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY = "api_key_query"
    NONE = "none"


class AuthProfile(BaseModel):
    """
    Authentication profile for a service.

    Attributes:
        kind: Type of authentication
        options: Additional auth options (scopes, etc.)
    """

    kind: AuthKind
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class APISpec(BaseModel):
    """
    Specification for an external API service.

    APIs represent third-party systems that the app integrates with.

    Attributes:
        name: API identifier
        title: Human-readable title
        spec_url: URL to API spec (often OpenAPI)
        spec_inline: Inline spec identifier
        auth_profile: Authentication configuration
        owner: API owner/provider
    """

    name: str
    title: str | None = None
    spec_url: str | None = None
    spec_inline: str | None = None
    auth_profile: AuthProfile
    owner: str | None = None

    model_config = ConfigDict(frozen=True)
