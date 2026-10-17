"""Tests for domain user attribute resolution in scope rules (#532).

Verifies that current_user.<attr> references in scope rules resolve
domain attributes from the DSL User entity when they don't exist on
the auth UserRecord or preferences.
"""

from typing import Any
from unittest.mock import patch

import pytest


def _make_user_and_session() -> tuple[Any, Any]:
    """Create real UserRecord and SessionRecord for tests."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from dazzle.http.runtime.auth.models import SessionRecord, UserRecord

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
        from dazzle.http.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(database_url="postgresql://localhost/test")
        assert store._load_domain_user_attributes("test@example.com") == {}

    def test_returns_scalar_fields_from_domain_row(self) -> None:
        from dazzle.http.runtime.auth.store import AuthStore

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

        from dazzle.http.runtime.auth.store import AuthStore

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
        from dazzle.http.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )
        with patch.object(store, "_execute", return_value=[]):
            result = store._load_domain_user_attributes("unknown@example.com")
        assert result == {}

    def test_returns_empty_on_db_error(self) -> None:
        from dazzle.http.runtime.auth.store import AuthStore

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
        """Full #684 path: a psycopg3 ``UUID`` FK on the domain User row reaches
        ``preferences`` as a string, so a ``current_user.org`` scope can bind it."""
        from uuid import uuid4

        from dazzle.http.runtime.auth.store import AuthStore

        with patch.object(AuthStore, "_init_db"):
            store = AuthStore(
                database_url="postgresql://localhost/test",
                user_entity_table="User",
            )

        user, session = _make_user_and_session()
        org_uuid = uuid4()

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
                            "org": org_uuid,
                            "email": "admin@oakwood.sch.uk",
                            "id": "x",
                        }
                    ],  # domain user query
                ],
            ),
        ):
            ctx = store.validate_session("session-abc")

        assert ctx.is_authenticated
        assert ctx.preferences == {
            "school": "school-456",
            "department": "maths",
            "org": str(org_uuid),
            "entity_id": "x",
        }

    def test_explicit_preferences_take_priority(self) -> None:
        from dazzle.http.runtime.auth.store import AuthStore

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


_DENY = "__RBAC_DENY__"
_ORG = "b3b49b49-02d1-50f5-9266-e20ecfd8c103"


def _auth(*, prefs: dict[str, str] | None = None, membership_tenant: str | None = None) -> Any:
    """A real ``AuthContext`` for the authenticated school admin."""
    from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord

    user, session = _make_user_and_session()
    membership = (
        MembershipRecord(id="m-1", tenant_id=membership_tenant, identity_id=str(user.id))
        if membership_tenant
        else None
    )
    return AuthContext(
        user=user,
        session=session,
        is_authenticated=True,
        preferences=prefs or {},
        active_membership=membership,
    )


# One row per resolution rule of ``current_user.<attr>`` in a scope predicate.
# The deny rows are the fail-closed contract: each is its own case id.
_RESOLUTION_CASES = [
    pytest.param("email", {}, "admin@oakwood.sch.uk", id="builtin-userrecord-field"),
    pytest.param(
        "school", {"school": "school-uuid-456"}, "school-uuid-456", id="domain-attr-from-prefs"
    ),
    pytest.param(
        "school", {"school_id": "school-uuid-99"}, "school-uuid-99", id="id-variant-from-prefs"
    ),
    pytest.param(
        "entity_id", {"entity_id": "dsl-user-789"}, "dsl-user-789", id="entity-id-from-prefs-#534"
    ),
    pytest.param("org", {"org": _ORG}, _ORG, id="uuid-string-pref-resolves-#684"),
    pytest.param("tier", {"tier": "3"}, "3", id="int-like-string-pref"),
    pytest.param("school", {}, _DENY, id="deny-when-attr-missing"),
    pytest.param(
        "tenant_id", {"tenant_id": "spoofed"}, _DENY, id="deny-tenant-id-from-prefs-not-membership"
    ),
]


@pytest.mark.parametrize(("attr", "prefs", "expected"), _RESOLUTION_CASES)
def test_current_user_attribute_resolution(attr: str, prefs: dict[str, str], expected: str) -> None:
    from dazzle.http.runtime.rls_bind import resolve_user_attribute

    assert resolve_user_attribute(attr, _auth(prefs=prefs)) == expected


def test_current_user_tenant_id_binds_the_active_membership() -> None:
    from dazzle.http.runtime.rls_bind import resolve_user_attribute

    assert resolve_user_attribute("tenant_id", _auth(membership_tenant="t-1")) == "t-1"


def test_current_user_attribute_denies_without_auth_context() -> None:
    from dazzle.http.runtime.rls_bind import resolve_user_attribute

    assert resolve_user_attribute("school", None) == _DENY
