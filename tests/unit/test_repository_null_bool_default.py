"""DB NULL on bool-with-default must not poison entity rows (cycle 1884)."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel

from dazzle.http.runtime.repository import Repository


class _ToggleUser(BaseModel):
    id: str
    name: str
    is_starred: bool = False
    is_active: bool = True


def test_row_to_model_omits_null_for_defaulted_bool() -> None:
    """NULL is_starred → model default False (not ValidationError soft-skip)."""
    repo = object.__new__(Repository)
    repo.model_class = _ToggleUser
    repo._field_types = {}
    row = {
        "id": str(uuid4()),
        "name": "Hana",
        "is_starred": None,
        "is_active": True,
    }
    model = Repository._row_to_model(repo, row)
    assert model.is_starred is False
    assert model.is_active is True
    assert model.name == "Hana"
