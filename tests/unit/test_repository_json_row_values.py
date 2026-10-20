"""A json column's payload is a value, never a relation (#1835)."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.http.runtime.repository import Repository
from dazzle.http.specs.entity import FieldType, ScalarType


def _repo(field_types: dict[str, FieldType]) -> Repository:
    repo = object.__new__(Repository)
    repo._field_types = field_types
    repo._computed_fields = []
    return repo


_JSON = FieldType(kind="scalar", scalar_type=ScalarType.JSON)
_DATE = FieldType(kind="scalar", scalar_type=ScalarType.DATE)


@pytest.mark.parametrize(
    "payload",
    [
        {"plan": ["three quotations", "one timed paragraph"]},
        ["a", "b"],
        [{"id": 1}, {"id": 2}],
        {},
        {"due": "2026-10-20"},
    ],
)
def test_json_field_payload_reads_back_unchanged(payload: Any) -> None:
    repo = _repo({"tutor_json": _JSON, "due": _DATE})
    row = Repository._convert_row_dict(repo, {"tutor_json": payload})
    assert row["tutor_json"] == payload


def test_untyped_list_of_scalars_is_a_plain_value() -> None:
    repo = _repo({})
    row = Repository._convert_row_dict(repo, {"tags": ["x", 1, None]})
    assert row["tags"] == ["x", 1, None]
