"""SCIM 2.0 discovery documents — ResourceTypes + Schemas (#1342 Phase 3).

Static, read-only metadata an IdP fetches to learn what this server supports
(RFC 7643 §6 ResourceType, §7 Schema). The published schemas are a **faithful
subset**: they advertise only the attributes Dazzle actually honors, so an IdP or
agent reading discovery never sees a promise the runtime doesn't keep.

  User  → userName (required, server-unique), active, emails (readOnly),
          groups (readOnly — owned by /Groups, RFC 7643 server-managed)
  Group → displayName (required), members (multiValued)

Every builder is pure and parametrised by ``base`` (the request base URL) so the
``meta.location`` self-links are correct behind any host. No secrets, no per-org
data — the same document for every connection.
"""

from __future__ import annotations

from typing import Any

USER_SCHEMA_URN = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA_URN = "urn:ietf:params:scim:schemas:core:2.0:Group"
_RESOURCE_TYPE_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
_SCHEMA_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"


def _attr(
    name: str,
    *,
    type: str = "string",
    multi_valued: bool = False,
    required: bool = False,
    case_exact: bool = False,
    mutability: str = "readWrite",
    returned: str = "default",
    uniqueness: str = "none",
) -> dict[str, Any]:
    """One RFC 7643 §7 attribute definition."""
    return {
        "name": name,
        "type": type,
        "multiValued": multi_valued,
        "required": required,
        "caseExact": case_exact,
        "mutability": mutability,
        "returned": returned,
        "uniqueness": uniqueness,
    }


def user_schema(base: str) -> dict[str, Any]:
    """The User schema (faithful subset — only attributes Dazzle honors)."""
    return {
        "schemas": [_SCHEMA_SCHEMA],
        "id": USER_SCHEMA_URN,
        "name": "User",
        "description": "User Account (a membership in this org)",
        "attributes": [
            _attr("userName", required=True, uniqueness="server"),
            _attr("active", type="boolean"),
            _attr("emails", multi_valued=True, mutability="readOnly"),
            # groups is server-managed (owned by /Groups) — read-only on User.
            _attr("groups", multi_valued=True, mutability="readOnly"),
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base}/scim/v2/Schemas/{USER_SCHEMA_URN}",
        },
    }


def group_schema(base: str) -> dict[str, Any]:
    """The Group schema (faithful subset)."""
    return {
        "schemas": [_SCHEMA_SCHEMA],
        "id": GROUP_SCHEMA_URN,
        "name": "Group",
        "description": "Group (drives member roles via the connection's group_mapping)",
        "attributes": [
            _attr("displayName", required=True),
            _attr("members", type="complex", multi_valued=True),
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base}/scim/v2/Schemas/{GROUP_SCHEMA_URN}",
        },
    }


def all_schemas(base: str) -> list[dict[str, Any]]:
    """Both published schema definitions, in resource-type order."""
    return [user_schema(base), group_schema(base)]


def schema_by_id(schema_id: str, base: str) -> dict[str, Any] | None:
    """A single schema by its URN id, or ``None`` if unknown (→ caller 404s)."""
    return next((s for s in all_schemas(base) if s["id"] == schema_id), None)


def _resource_type(
    rid: str, endpoint: str, schema_urn: str, description: str, base: str
) -> dict[str, Any]:
    return {
        "schemas": [_RESOURCE_TYPE_SCHEMA],
        "id": rid,
        "name": rid,
        "endpoint": endpoint,
        "description": description,
        "schema": schema_urn,
        "schemaExtensions": [],
        "meta": {
            "resourceType": "ResourceType",
            "location": f"{base}/scim/v2/ResourceTypes/{rid}",
        },
    }


def resource_types(base: str) -> list[dict[str, Any]]:
    """The ResourceType documents for the resources this server exposes."""
    return [
        _resource_type("User", "/Users", USER_SCHEMA_URN, "User Account", base),
        _resource_type("Group", "/Groups", GROUP_SCHEMA_URN, "Group", base),
    ]


def resource_type_by_id(rid: str, base: str) -> dict[str, Any] | None:
    """A single ResourceType by id (``User``/``Group``), or ``None`` if unknown."""
    return next((rt for rt in resource_types(base) if rt["id"] == rid), None)
