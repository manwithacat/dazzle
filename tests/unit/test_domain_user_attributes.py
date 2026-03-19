"""Tests for domain user attribute resolution in scope rules (#532).

Verifies that current_user.<attr> references in scope rules resolve
domain attributes from the DSL User entity when they don't exist on
the auth UserRecord or preferences.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def _make_user_and_session() -> tuple[Any, Any]:
    """Create real UserRecord and SessionRecord for tests."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from dazzle_back.runtime.auth.models import SessionRecord, UserRecord

    user = UserRecord(
        id=uuid4(),
        email="admin@oakwood.sch.uk",
        password_hash="hashed",
        username="admin",
        roles=["school_admin"],
    )
    session = SessionRecord(
        id="session-abc",
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return user, session


class TestLoadDomainUserAttributes:
    """Test AuthStore._load_domain_user_attributes."""

    def test_returns_empty_when_no_table_configured(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(database_url="postgresql://localhost/test")
        assert store._load_domain_user_attributes("test@example.com") == {}

    def test_returns_scalar_fields_from_domain_row(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        # Mock the SQL execution
        domain_row = {
            "id": "user-123",
            "email": "admin@oakwood.sch.uk",
            "password_hash": "hashed",
            "school": "school-uuid-456",
            "department": "maths",
            "trust": "trust-uuid-789",
            "name": "Admin User",
            "nullable_field": None,
        }
        with patch.object(store, "_execute", return_value=[domain_row]):
            result = store._load_domain_user_attributes("admin@oakwood.sch.uk")

        # Should include scalar domain fields
        assert result["school"] == "school-uuid-456"
        assert result["department"] == "maths"
        assert result["trust"] == "trust-uuid-789"
        assert result["name"] == "Admin User"
        # Should skip auth-internal and null fields
        assert "id" not in result
        assert "email" not in result
        assert "password_hash" not in result
        assert "nullable_field" not in result

    def test_returns_empty_when_no_domain_row_found(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )
        with patch.object(store, "_execute", return_value=[]):
            result = store._load_domain_user_attributes("unknown@example.com")
        assert result == {}

    def test_returns_empty_on_db_error(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )
        with patch.object(store, "_execute", side_effect=Exception("table not found")):
            result = store._load_domain_user_attributes("admin@example.com")
        assert result == {}


class TestValidateSessionMergesDomainAttrs:
    """Test that validate_session merges domain user attributes into preferences."""

    def test_domain_attrs_merged_into_preferences(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        user, session = _make_user_and_session()

        with (
            patch.object(store, "get_session", return_value=session),
            patch.object(store, "get_user_by_id", return_value=user),
            patch.object(
                store,
                "_execute",
                side_effect=[
                    [],  # user_preferences query returns empty
                    [
                        {
                            "school": "school-456",
                            "department": "maths",
                            "email": "admin@oakwood.sch.uk",
                            "id": "x",
                        }
                    ],  # domain user query
                ],
            ),
        ):
            ctx = store.validate_session("session-abc")

        assert ctx.is_authenticated
        assert ctx.preferences.get("school") == "school-456"
        assert ctx.preferences.get("department") == "maths"

    def test_explicit_preferences_take_priority(self) -> None:
        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        user, session = _make_user_and_session()

        with (
            patch.object(store, "get_session", return_value=session),
            patch.object(store, "get_user_by_id", return_value=user),
            patch.object(
                store,
                "_execute",
                side_effect=[
                    [{"key": "school", "value": "override-school"}],  # explicit preference
                    [
                        {"school": "domain-school", "email": "admin@oakwood.sch.uk", "id": "x"}
                    ],  # domain user
                ],
            ),
        ):
            ctx = store.validate_session("session-abc")

        # Explicit preference wins over domain attribute
        assert ctx.preferences["school"] == "override-school"


class TestResolveUserAttributeWithPreferences:
    """Test that _resolve_user_attribute picks up domain attrs via preferences."""

    def test_resolves_school_from_preferences(self) -> None:
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.school = MagicMock(spec=[])  # not a scalar
        auth_context.user.school_id = MagicMock(spec=[])  # not a scalar
        auth_context.preferences = {"school": "school-uuid-456"}

        result = _resolve_user_attribute("school", auth_context)
        assert result == "school-uuid-456"

    def test_returns_rbac_deny_when_not_found(self) -> None:
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        # Make getattr return non-scalar
        auth_context.user.school = MagicMock(spec=[])
        auth_context.user.school_id = MagicMock(spec=[])
        auth_context.preferences = {}

        result = _resolve_user_attribute("school", auth_context)
        assert result == "__RBAC_DENY__"
