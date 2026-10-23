"""#1848: an update writes exactly the fields the client sent.

An optional field sent empty (the write handlers map ``""`` to ``None``) or as
null clears the column; a field the client did not send is left alone; a
``required`` field sent empty is a validation error. Before the fix the service
and the repository both dropped every ``None``, so "the user cleared this" and
"the client didn't send this" collapsed into "leave it", and no optional field
could be cleared from an edit form.

The real-Postgres proof through the generated form endpoint is
``tests/integration/test_update_clears_optional_pg.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from dazzle.http.runtime.model_generator import (
    generate_create_schema,
    generate_entity_model,
    generate_update_schema,
)
from dazzle.http.runtime.repository import Repository
from dazzle.http.runtime.service_generator import CRUDService
from dazzle.http.specs import EntitySpec, FieldSpec, FieldType, ScalarType

_AGENT_ID = uuid4()


def _ticket_entity() -> EntitySpec:
    return EntitySpec(
        name="Ticket",
        label="Ticket",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                required=True,
            ),
            FieldSpec(
                name="initials",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=3),
            ),
            FieldSpec(name="assignee", type=FieldType(kind="ref", ref_entity="Agent")),
            FieldSpec(name="due", type=FieldType(kind="scalar", scalar_type=ScalarType.DATE)),
        ],
    )


_STARTING = {
    "title": "Printer jam",
    "initials": "XQ",
    "assignee": _AGENT_ID,
    "due": date(2026, 11, 1),
}

# Each optional kind cyfuture hit: str, ref, date.
_OPTIONAL_FIELDS = pytest.mark.parametrize("field", ["initials", "assignee", "due"])


class _SpyRepository:
    """Holds one row; records the dict ``CRUDService.update`` hands the repository."""

    def __init__(self, model_class: type[BaseModel], row: dict[str, Any]) -> None:
        self.model_class = model_class
        self.row = row
        self.writes: list[dict[str, Any]] = []

    async def read(self, id: UUID, **_kw: Any) -> BaseModel:
        return self.model_class(**self.row)

    async def update(self, id: UUID, data: dict[str, Any]) -> BaseModel:
        self.writes.append(dict(data))
        self.row = {**self.row, **data}
        return self.model_class(**self.row)


def _service() -> tuple[CRUDService[Any, Any, Any], type[BaseModel], _SpyRepository]:
    entity = _ticket_entity()
    model = generate_entity_model(entity)
    update_schema = generate_update_schema(entity)
    service: CRUDService[Any, Any, Any] = CRUDService(
        entity_name="Ticket",
        model_class=model,
        create_schema=generate_create_schema(entity),
        update_schema=update_schema,
        entity_spec=entity,
    )
    repo = _SpyRepository(model, {"id": uuid4(), **_STARTING})
    service.set_repository(repo)  # type: ignore[arg-type]

    async def _refs_exist(data: dict[str, Any]) -> None:  # FK existence is not under test
        return None

    service._validate_references = _refs_exist  # type: ignore[method-assign]
    return service, update_schema, repo


@_OPTIONAL_FIELDS
async def test_optional_field_sent_empty_is_cleared(field: str) -> None:
    service, update_schema, repo = _service()
    # The edit form posts every rendered field; the cleared one arrives as None.
    body = {**_STARTING, field: None}
    updated = await service.update(repo.row["id"], update_schema.model_validate(body))

    assert repo.writes[-1][field] is None
    assert getattr(updated, field) is None
    untouched = {k for k in _STARTING if k != field}
    assert {k: getattr(updated, k) for k in untouched} == {k: _STARTING[k] for k in untouched}


@_OPTIONAL_FIELDS
async def test_field_not_sent_is_left_untouched(field: str) -> None:
    service, update_schema, repo = _service()
    await service.update(repo.row["id"], update_schema.model_validate({"title": "Renamed"}))

    assert field not in repo.writes[-1]
    assert repo.row[field] == _STARTING[field]
    assert repo.row["title"] == "Renamed"


def test_required_field_sent_empty_fails_validation() -> None:
    update_schema = generate_update_schema(_ticket_entity())
    with pytest.raises(ValidationError) as exc_info:
        update_schema.model_validate({"title": None})
    (err,) = exc_info.value.errors()
    assert (err["loc"], err["type"], err["msg"]) == (("title",), "missing", "Field required")
    # Omitting it is still a valid partial update.
    assert update_schema.model_validate({}).model_dump(exclude_unset=True) == {}


async def test_soft_delete_dict_payload_reaches_the_repository() -> None:
    # The soft-delete route stamps ``deleted_at`` with a plain dict.
    service, _schema, repo = _service()
    await service.update(repo.row["id"], {"initials": None})
    assert repo.writes[-1] == {"initials": None}


class _Cursor:
    def __init__(self, log: list[tuple[str, list[Any]]]) -> None:
        self.log = log
        self.rowcount = 1

    def execute(self, sql: str, values: list[Any]) -> None:
        self.log.append((sql, values))


class _Conn:
    def __init__(self) -> None:
        self.log: list[tuple[str, list[Any]]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self.log)


class _Db:
    placeholder = "%s"


async def test_repository_update_writes_explicit_null(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = _ticket_entity()
    repo: Repository[Any] = Repository(
        db_manager=_Db(), entity_spec=entity, model_class=generate_entity_model(entity)
    )
    monkeypatch.setattr(repo, "_read_on_conn", lambda conn, id: {"id": id})
    conn = _Conn()
    await repo.update(uuid4(), {"initials": None, "title": "Kept"}, conn=conn)

    ((sql, values),) = conn.log
    assert '"initials" = %s' in sql and '"title" = %s' in sql
    assert values[:2] == [None, "Kept"]
