"""Tests for domain user attribute resolution in scope rules (#532).

Verifies that current_user.<attr> references in scope rules resolve
domain attributes from the DSL User entity when they don't exist on
the auth UserRecord or preferences.
"""

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
        # Should skip auth-internal and null fields (id stored as entity_id)
        assert "id" not in result
        assert result["entity_id"] == "user-123"  # domain entity PK (#534)
        assert "email" not in result
        assert "password_hash" not in result
        assert "nullable_field" not in result

    def test_uuid_values_serialized_to_string(self) -> None:
        """UUID objects from psycopg3 must be converted to strings (#684)."""
        from uuid import UUID, uuid4

        from dazzle_back.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        school_uuid = uuid4()
        dept_uuid = uuid4()
        domain_row = {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "email": "teacher@oakwood.sch.uk",
            "password_hash": "hashed",
            "school": school_uuid,  # psycopg3 returns UUID objects
            "department": dept_uuid,
            "name": "Teacher",
        }
        with patch.object(store, "_execute", return_value=[domain_row]):
            result = store._load_domain_user_attributes("teacher@oakwood.sch.uk")

        # UUID values must be converted to strings
        assert result["school"] == str(school_uuid)
        assert result["department"] == str(dept_uuid)
        assert isinstance(result["school"], str)
        assert isinstance(result["department"], str)
        # name (str) should still work
        assert result["name"] == "Teacher"

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

    def test_resolves_entity_id_from_preferences(self) -> None:
        """current_user in via clauses should resolve to DSL entity ID (#534)."""
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.entity_id = MagicMock(spec=[])  # not a scalar on UserRecord
        auth_context.preferences = {"entity_id": "dsl-user-uuid-789"}

        result = _resolve_user_attribute("entity_id", auth_context)
        assert result == "dsl-user-uuid-789"

    def test_uuid_preference_resolves_not_deny(self) -> None:
        """UUID FK attrs stored as strings must resolve, not produce __RBAC_DENY__ (#684)."""
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.department = MagicMock(spec=[])  # not a scalar
        auth_context.preferences = {"department": "b3b49b49-02d1-50f5-9266-e20ecfd8c103"}

        result = _resolve_user_attribute("department", auth_context)
        # Must resolve to the UUID string, NOT __RBAC_DENY__
        assert result == "b3b49b49-02d1-50f5-9266-e20ecfd8c103"
        assert result != "__RBAC_DENY__"


class TestPositiveAuthResolution:
    """Verify that permitted users with FK ref attrs get data, not empty results (#684).

    Exercises the positive auth path: when a user HAS the required FK
    attributes (e.g. scope: org_id = current_user.org), the scope
    resolution produces a usable filter value — not __RBAC_DENY__.

    Uses generic DSL entity names, not domain-specific ones.
    """

    def test_uuid_fk_attrs_resolve_through_full_auth_path(self) -> None:
        """Full path: UUID FK in domain User row → session prefs → scope resolution.

        Simulates: entity with `scope: org_id = current_user.org` where
        the User entity has `org: ref Organisation` (a UUID FK column).
        """
        from uuid import UUID, uuid4

        from dazzle_back.runtime.auth.store import AuthStore
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        # Simulate a domain User row as psycopg3 returns it — UUID FK columns
        # come back as uuid.UUID objects, not strings
        org_uuid = uuid4()
        team_uuid = uuid4()
        domain_row = {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "email": "user@example.com",
            "password_hash": "hashed",
            "org": org_uuid,  # ref Organisation — psycopg3 returns UUID
            "team": team_uuid,  # ref Team — psycopg3 returns UUID
            "display_name": "Test User",
        }

        # Step 1: _load_domain_user_attributes must convert UUID→str
        with patch.object(store, "_execute", return_value=[domain_row]):
            attrs = store._load_domain_user_attributes("user@example.com")

        assert isinstance(attrs["org"], str)
        assert isinstance(attrs["team"], str)

        # Step 2: attrs go into auth_context.preferences (as validate_session does)
        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.org = MagicMock(spec=[])  # not a scalar on UserRecord
        auth_context.user.team = MagicMock(spec=[])
        auth_context.preferences = attrs

        # Step 3: _resolve_user_attribute must find them — not __RBAC_DENY__
        org_result = _resolve_user_attribute("org", auth_context)
        team_result = _resolve_user_attribute("team", auth_context)

        assert org_result == str(org_uuid)
        assert team_result == str(team_uuid)
        assert org_result != "__RBAC_DENY__"
        assert team_result != "__RBAC_DENY__"

    def test_string_attrs_still_resolve(self) -> None:
        """Non-UUID scalar attrs (str, int, bool) continue to work."""
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.region = MagicMock(spec=[])
        auth_context.preferences = {"region": "eu-west", "tier": "3"}

        assert _resolve_user_attribute("region", auth_context) == "eu-west"
        assert _resolve_user_attribute("tier", auth_context) == "3"

    def test_missing_attr_returns_deny(self) -> None:
        """When the user lacks the required attr, __RBAC_DENY__ is correct."""
        from dazzle_back.runtime.route_generator import _resolve_user_attribute

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.org = MagicMock(spec=[])
        auth_context.preferences = {}  # no org set

        assert _resolve_user_attribute("org", auth_context) == "__RBAC_DENY__"
