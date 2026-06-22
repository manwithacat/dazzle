"""Entity CRUD over the agent-E2E harness transport (#1446).

Extracted from ``DazzleClient`` (which had accreted transport, auth, CRUD, cleanup,
schema and data-generation onto one object). ``EntityClient`` owns entity create /
read / update / delete and the REST-endpoint derivation, preferring the
``/__test__`` routes (auth-bypassing) and falling back to standard CRUD. It composes
the transport via constructor injection — ``DazzleClient`` supplies ``_request``,
``_auth_headers``, ``api_url``, the ``_test_routes_available`` probe flag, and the
``cleanup`` tracker that created rows are registered with.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from dazzle.testing.test_runner import DazzleClient

logger = logging.getLogger(__name__)


class EntityClient:
    """Entity CRUD bound to a :class:`DazzleClient`'s transport."""

    def __init__(self, client: DazzleClient):
        self._client = client

    def _entity_endpoint(self, entity_name: str) -> str:
        """Derive the REST endpoint for an entity name.

        Uses to_api_plural for proper English pluralization:
        Contact -> /contacts, Company -> /companies, Address -> /addresses
        """
        from dazzle.core.strings import to_api_plural

        return f"/{to_api_plural(entity_name)}"

    def get_entities(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all entities of a type."""
        client = self._client
        try:
            # Prefer test endpoint (returns raw JSON)
            if client._test_routes_available is not False:
                resp = client._request(
                    "GET",
                    f"{client.api_url}/__test__/entity/{entity_name}",
                    headers=client._auth_headers(),
                )
                if resp.status_code == 200:
                    return list(resp.json())
                if resp.status_code == 404:
                    client._test_routes_available = False

            # Fallback to standard list endpoint
            endpoint = self._entity_endpoint(entity_name)
            resp = client._request(
                "GET",
                f"{client.api_url}{endpoint}",
                headers=client._auth_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                # List endpoint may return {items: [...]} or [...] directly
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "items" in data:
                    return list(data["items"])
            return []
        except Exception:
            logger.debug("ignored exception in EntityClient.get_entities", exc_info=True)
            return []

    def create_entity(self, entity_name: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new entity, preferring ``/__test__/seed`` then standard CRUD."""
        client = self._client
        try:
            # Use __test__/seed when available (bypasses auth)
            if client._test_routes_available is not False:
                # #1210: uuid4 hex (not int(time.time())) — two entities
                # created in the same second previously collided on
                # fixture_id, silently dropping one from the cleanup
                # tracking list and leaking it past --cleanup.
                fixture_id = f"test-{entity_name.lower()}-{uuid4().hex}"
                fixtures = [{"id": fixture_id, "entity": entity_name, "data": data}]
                resp = client._request(
                    "POST", f"{client.api_url}/__test__/seed", json={"fixtures": fixtures}
                )
                if resp.status_code == 200:
                    result: dict[str, Any] = resp.json()
                    created: dict[str, Any] = result.get("created", {})
                    created_entity = created.get(fixture_id)
                    if created_entity and "id" in created_entity:
                        client.cleanup.track(entity_name, str(created_entity["id"]))
                    return created_entity
                if resp.status_code == 404:
                    client._test_routes_available = False

            # Standard CRUD endpoint with auth
            endpoint = self._entity_endpoint(entity_name)
            resp = client._request(
                "POST", f"{client.api_url}{endpoint}", json=data, headers=client._auth_headers()
            )
            if resp.status_code in (200, 201):
                result_data = dict(resp.json())
                if "id" in result_data:
                    client.cleanup.track(entity_name, str(result_data["id"]))
                return result_data
            return None
        except Exception as exc:
            # Surface create failures at warning (the original code printed them);
            # a create error usually breaks the dependent steps, so don't silently
            # debug-swallow it.
            logger.warning("EntityClient.create_entity(%s) failed: %s", entity_name, exc)
            return None

    def update_entity(
        self, entity_name: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an entity."""
        client = self._client
        try:
            endpoint = f"{self._entity_endpoint(entity_name)}/{entity_id}"
            resp = client._request(
                "PUT", f"{client.api_url}{endpoint}", json=data, headers=client._auth_headers()
            )
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            logger.debug("ignored exception in EntityClient.update_entity", exc_info=True)
            return None

    def delete_entity(self, entity_name: str, entity_id: str) -> str:
        """Delete an entity by ID. Tries __test__ route first, then standard REST.

        Returns a three-state outcome (#1307):

        - ``"deleted"`` — the row was removed (HTTP 200/204).
        - ``"absent"``  — the row was already gone (HTTP 404). For *cleanup*
          this is success, not failure: a 404 means the target id does not
          exist, so there is nothing to clean up. Counting it as a failure
          produced the misleading ``"N failed"`` teardown alarm.
        - ``"failed"``  — a genuine failure (auth/permission/server error/
          network) where the row may still exist.
        """
        client = self._client
        try:
            if client._test_routes_available is not False:
                resp = client._request(
                    "DELETE", client.api_url + "/__test__/entity/" + entity_name + "/" + entity_id
                )
                if resp.status_code == 200:
                    return "deleted"
                if resp.status_code == 403:
                    # Missing X-Test-Secret — don't fall through to REST
                    return "failed"
                if resp.status_code == 404 and "Unknown entity" not in resp.text:
                    # Ambiguous: either the test route is unavailable OR the id
                    # is already gone. Preserve the established behaviour — mark
                    # test routes unavailable and fall through to REST, which
                    # disambiguates (a REST 404 → genuinely absent).
                    client._test_routes_available = False
                elif resp.status_code >= 500:
                    # Server error — don't waste time on REST fallback
                    return "failed"

            endpoint = self._entity_endpoint(entity_name)
            resp = client._request(
                "DELETE",
                client.api_url + endpoint + "/" + entity_id,
                headers=client._auth_headers(),
            )
            if resp.status_code in (200, 204):
                return "deleted"
            if resp.status_code == 404:
                # Row already gone — for cleanup this is success, not failure.
                return "absent"
            return "failed"
        except Exception:
            logger.debug("ignored exception in EntityClient.delete_entity", exc_info=True)
            return "failed"
