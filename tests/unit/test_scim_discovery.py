"""Unit tests for the SCIM discovery documents (#1342 Phase 3)."""

from dazzle.back.runtime.auth import scim_discovery as d

BASE = "https://app.test"


def test_resource_types_are_user_and_group() -> None:
    rts = d.resource_types(BASE)
    assert [rt["id"] for rt in rts] == ["User", "Group"]
    user, group = rts
    assert user["endpoint"] == "/Users"
    assert user["schema"] == d.USER_SCHEMA_URN
    assert group["endpoint"] == "/Groups"
    assert group["schema"] == d.GROUP_SCHEMA_URN
    assert user["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"]
    assert user["meta"]["location"] == f"{BASE}/scim/v2/ResourceTypes/User"


def test_resource_type_by_id() -> None:
    assert d.resource_type_by_id("Group", BASE)["id"] == "Group"
    assert d.resource_type_by_id("Nope", BASE) is None


def test_schemas_are_user_and_group_with_core_urns() -> None:
    schemas = d.all_schemas(BASE)
    assert [s["id"] for s in schemas] == [d.USER_SCHEMA_URN, d.GROUP_SCHEMA_URN]
    for s in schemas:
        assert s["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:Schema"]
        assert s["meta"]["resourceType"] == "Schema"


def test_user_schema_is_faithful_subset() -> None:
    user = d.user_schema(BASE)
    names = {a["name"] for a in user["attributes"]}
    # Exactly what Dazzle honors — nothing advertised that the runtime ignores.
    assert names == {"userName", "active", "emails", "groups"}
    by_name = {a["name"]: a for a in user["attributes"]}
    assert by_name["userName"]["required"] is True
    assert by_name["userName"]["uniqueness"] == "server"
    # groups is server-managed (owned by /Groups) — read-only on the User resource.
    assert by_name["groups"]["mutability"] == "readOnly"
    assert by_name["emails"]["mutability"] == "readOnly"
    assert by_name["active"]["type"] == "boolean"


def test_group_schema_is_faithful_subset() -> None:
    group = d.group_schema(BASE)
    names = {a["name"] for a in group["attributes"]}
    assert names == {"displayName", "members"}
    by_name = {a["name"]: a for a in group["attributes"]}
    assert by_name["displayName"]["required"] is True
    assert by_name["members"]["multiValued"] is True


def test_schema_by_id() -> None:
    assert d.schema_by_id(d.USER_SCHEMA_URN, BASE)["name"] == "User"
    assert d.schema_by_id("urn:bogus", BASE) is None


def test_locations_are_base_relative() -> None:
    user = d.schema_by_id(d.USER_SCHEMA_URN, BASE)
    assert user["meta"]["location"] == f"{BASE}/scim/v2/Schemas/{d.USER_SCHEMA_URN}"
