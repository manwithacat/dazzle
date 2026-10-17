"""#1807: ``on_transition`` effects must reach the service of the *target entity*.

The executor looks services up by ``effect.entity_name``; the runtime registry is keyed
by service name. The wiring must hand the executor the entity-keyed view.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.runtime.service_generator import CRUDService
from dazzle.http.runtime.subsystems.system_routes import SystemRoutesSubsystem

DSL = """module t
app t "T"

entity Doc "Doc":
  id: uuid pk
  status: enum[draft, sent] = draft

  transitions:
    draft -> sent

  on_transition:
    draft -> sent:
      create Audit:
        note: "sent"

entity Audit "Audit":
  id: uuid pk
  note: str(50)
"""


class _Crud(CRUDService):
    """Service-registry stand-in: CRUD surface only, records creates."""

    def __init__(self, entity_name: str) -> None:
        self.entity_name = entity_name
        self.callbacks: list[Any] = []
        self.created: list[dict[str, Any]] = []
        self.create_schema = lambda **kw: kw

    def on_updated(self, cb: Any) -> None:
        self.callbacks.append(cb)

    async def create(self, data: dict[str, Any], **_: Any) -> Any:  # type: ignore[override]
        self.created.append(data)
        return SimpleNamespace(id="a-1")


@pytest.mark.asyncio
async def test_on_transition_create_effect_runs_against_service_name_keyed_registry() -> None:
    *_, fragment = parse_dsl(DSL, Path("t.dsl"))
    doc, audit = _Crud("Doc"), _Crud("Audit")
    ctx = SimpleNamespace(
        appspec=SimpleNamespace(domain=SimpleNamespace(entities=fragment.entities)),
        # keyed by service name, exactly as the runtime builds it
        services={"update_doc": doc, "create_audit": audit},
        config=SimpleNamespace(entity_status_fields={"Doc": "status"}),
    )
    SystemRoutesSubsystem._init_transition_effects(
        SystemRoutesSubsystem.__new__(SystemRoutesSubsystem), ctx
    )
    assert len(doc.callbacks) == 1

    await doc.callbacks[0]("Doc", "d-1", {"status": "sent"}, {"status": "draft"})

    assert audit.created == [{"note": "sent"}]
