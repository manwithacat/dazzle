"""Drive the generated CRUD routes through their public factories.

``crud_route_client`` mounts a ``create_<verb>_handler`` route on a bare FastAPI
app with a fixed ``AuthContext`` and a recording service, so a test asserts on
the HTTP status, the JSON body, the calls the service received and the audit
decisions logged — the observable contract of the route — instead of calling a
private handler body with a hand-built mock request.
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from dazzle.core.ir.fk_graph import FKGraph
from dazzle.http.runtime.auth.models import AuthContext, UserRecord
from dazzle.http.runtime.route_support import HandlerConfig, RouteSpec
from dazzle.http.specs.auth import EntityAccessSpec


class RecordingService:
    """A service that records every ``execute`` call.

    ``list`` returns an empty page; ``read`` returns ``row`` (``None`` = missing).
    """

    entity_spec = None

    def __init__(self, row: Any = None) -> None:
        self.row = row
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if kwargs.get("operation") == "list":
            return {
                "items": [],
                "total": 0,
                "page": kwargs.get("page", 1),
                "page_size": kwargs.get("page_size", 20),
            }
        if kwargs.get("operation") == "read":
            return self.row
        return {"ok": True}


def signed_in(*roles: str, prefs: dict[str, str] | None = None) -> AuthContext:
    """An authenticated ``AuthContext`` holding ``roles`` and ``prefs``."""
    user = UserRecord(id=uuid4(), email="u@example.com", password_hash="x", roles=list(roles))
    return AuthContext(user=user, is_authenticated=True, roles=list(roles), preferences=prefs or {})


def crud_route_client(
    factory: Callable[..., Any],
    *,
    auth: AuthContext,
    service: RecordingService,
    access: EntityAccessSpec | None = None,
    entity_name: str = "Task",
    audit_logger: Any = None,
    fk_graph: FKGraph | None = None,
    input_schema: type[BaseModel] | None = None,
    include_field_changes: bool = False,
    method: str = "GET",
    path: str = "/items",
) -> TestClient:
    """A client whose ``method path`` is the route ``factory`` builds for ``entity_name``."""
    handler = factory(
        RouteSpec(
            handler=HandlerConfig(
                optional_auth_dep=lambda: auth,
                entity_name=entity_name,
                cedar_access_spec=access,
                audit_logger=audit_logger,
                fk_graph=fk_graph,
            ),
            service=service,  # type: ignore[arg-type]
            input_schema=input_schema,
            include_field_changes=include_field_changes,
        )
    )
    app = FastAPI()
    app.add_api_route(path, handler, methods=[method])
    return TestClient(app)
