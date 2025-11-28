"""
User entity auto-detection for DNR Backend.

Automatically detects User entities and configures authentication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec, EntitySpec


# =============================================================================
# User Entity Detection
# =============================================================================


USER_ENTITY_NAMES = {"user", "users", "account", "accounts", "member", "members"}
EMAIL_FIELD_NAMES = {"email", "email_address", "mail"}
PASSWORD_FIELD_NAMES = {"password", "password_hash", "hashed_password", "pwd"}
USERNAME_FIELD_NAMES = {"username", "user_name", "name", "login"}


def find_user_entity(spec: "BackendSpec") -> "EntitySpec | None":
    """
    Find a User-like entity in the BackendSpec.

    Looks for entities named 'User', 'Account', etc. that have email and password fields.

    Args:
        spec: Backend specification to search

    Returns:
        User entity if found, None otherwise
    """
    for entity in spec.entities:
        name_lower = entity.name.lower()

        # Check if entity name suggests it's a user entity
        if name_lower in USER_ENTITY_NAMES:
            # Verify it has required auth fields
            if has_auth_fields(entity):
                return entity

    return None


def has_auth_fields(entity: "EntitySpec") -> bool:
    """
    Check if an entity has fields suitable for authentication.

    Requires at least an email-like field and optionally a password field.

    Args:
        entity: Entity to check

    Returns:
        True if entity has auth-compatible fields
    """
    has_email = False
    has_password = False

    for field in entity.fields:
        field_name_lower = field.name.lower()

        if field_name_lower in EMAIL_FIELD_NAMES:
            has_email = True
        elif field_name_lower in PASSWORD_FIELD_NAMES:
            has_password = True

    # Email is required, password is optional (we might generate it)
    return has_email


def get_auth_field_mapping(entity: "EntitySpec") -> dict[str, str | None]:
    """
    Get mapping of auth fields from entity fields.

    Args:
        entity: Entity to analyze

    Returns:
        Dict mapping auth field names to entity field names
    """
    mapping: dict[str, str | None] = {
        "email": None,
        "password": None,
        "username": None,
    }

    for field in entity.fields:
        field_name_lower = field.name.lower()

        if field_name_lower in EMAIL_FIELD_NAMES and mapping["email"] is None:
            mapping["email"] = field.name
        elif field_name_lower in PASSWORD_FIELD_NAMES and mapping["password"] is None:
            mapping["password"] = field.name
        elif field_name_lower in USERNAME_FIELD_NAMES and mapping["username"] is None:
            mapping["username"] = field.name

    return mapping


# =============================================================================
# Auth Configuration
# =============================================================================


class AuthConfig:
    """Configuration for authentication based on entity detection."""

    def __init__(
        self,
        enabled: bool = False,
        user_entity: "EntitySpec | None" = None,
        field_mapping: dict[str, str | None] | None = None,
        use_builtin_user_table: bool = True,
    ):
        """
        Initialize auth configuration.

        Args:
            enabled: Whether auth is enabled
            user_entity: Detected user entity (if any)
            field_mapping: Mapping of auth fields to entity fields
            use_builtin_user_table: Use auth.py's built-in user table
        """
        self.enabled = enabled
        self.user_entity = user_entity
        self.field_mapping = field_mapping or {}
        self.use_builtin_user_table = use_builtin_user_table

    @classmethod
    def from_spec(cls, spec: "BackendSpec") -> "AuthConfig":
        """
        Create auth configuration from BackendSpec.

        Automatically detects user entity and configures authentication.

        Args:
            spec: Backend specification

        Returns:
            Auth configuration
        """
        user_entity = find_user_entity(spec)

        if user_entity:
            field_mapping = get_auth_field_mapping(user_entity)
            return cls(
                enabled=True,
                user_entity=user_entity,
                field_mapping=field_mapping,
                use_builtin_user_table=True,  # Always use builtin for now
            )

        return cls(enabled=False)

    @property
    def user_entity_name(self) -> str | None:
        """Get user entity name."""
        return self.user_entity.name if self.user_entity else None

    def __repr__(self) -> str:
        return (
            f"AuthConfig(enabled={self.enabled}, "
            f"user_entity={self.user_entity_name}, "
            f"field_mapping={self.field_mapping})"
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def detect_auth_requirements(spec: "BackendSpec") -> AuthConfig:
    """
    Detect authentication requirements from a BackendSpec.

    This is the main entry point for auth detection.

    Args:
        spec: Backend specification

    Returns:
        Auth configuration based on detected entities
    """
    return AuthConfig.from_spec(spec)


def should_enable_auth(spec: "BackendSpec") -> bool:
    """
    Check if authentication should be enabled for a spec.

    Args:
        spec: Backend specification

    Returns:
        True if auth should be enabled
    """
    return find_user_entity(spec) is not None
