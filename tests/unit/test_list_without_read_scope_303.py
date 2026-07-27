"""#303 — list-without-read scope validator + repository read soft-skip."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_validate_list_without_read_warns() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.validation.rbac import validate_list_without_read_scope

    app = load_project_appspec(SIMPLE)
    # Drop all read scopes on first entity that has list scopes
    for e in app.domain.entities:
        if not e.access or not e.access.scopes:
            continue
        list_rules = [
            r for r in e.access.scopes if str(getattr(r.operation, "value", r.operation)) == "list"
        ]
        if not list_rules:
            continue
        # Keep list rules; strip read rules
        e.access.scopes[:] = [
            r for r in e.access.scopes if str(getattr(r.operation, "value", r.operation)) != "read"
        ]
        entity_name = e.name
        break
    else:
        pytest.skip("no list scopes in simple_task")

    _errors, warnings = validate_list_without_read_scope(app)
    assert any(
        entity_name in w and "#303" in w and "without matching scope read" in w for w in warnings
    ), warnings


def test_validate_list_with_matching_read_clean() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.validation.rbac import validate_list_without_read_scope

    app = load_project_appspec(SIMPLE)
    _errors, warnings = validate_list_without_read_scope(app)
    assert warnings == []


def test_validate_list_wildcard_read_covers() -> None:
    from dazzle.core import ir
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.validation.rbac import validate_list_without_read_scope

    app = load_project_appspec(SIMPLE)
    for e in app.domain.entities:
        if not e.access or not e.access.scopes:
            continue
        list_rules = [
            r for r in e.access.scopes if str(getattr(r.operation, "value", r.operation)) == "list"
        ]
        if not list_rules:
            continue
        # Replace read scopes with a single wildcard read
        non_read = [
            r for r in e.access.scopes if str(getattr(r.operation, "value", r.operation)) != "read"
        ]
        wild = list_rules[0].model_copy(
            update={"operation": ir.PermissionKind.READ, "personas": ["*"]}
        )
        e.access.scopes[:] = non_read + [wild]
        break
    else:
        pytest.skip("no list scopes")

    _errors, warnings = validate_list_without_read_scope(app)
    assert warnings == []


def test_safe_row_to_model_soft_skips_invalid() -> None:
    """Invalid enum on a domain row must not raise out of repository.read."""
    from dazzle.http.runtime.repository import Repository

    class _User(BaseModel):
        id: str
        role: str = Field(pattern=r"^(admin|manager|member)$")

    repo = object.__new__(Repository)
    repo.model_class = _User
    repo.table_name = "User"
    repo._field_types = {}

    # Patch _row_to_model path via real call
    good = repo._safe_row_to_model({"id": "1", "role": "member"})
    assert good is not None
    assert good.role == "member"

    bad = repo._safe_row_to_model({"id": "2", "role": "user"})
    assert bad is None


def test_safe_row_to_model_raises_nothing_on_validation_error() -> None:
    from dazzle.http.runtime.repository import Repository

    class _Row(BaseModel):
        id: str
        n: int

    repo = object.__new__(Repository)
    repo.model_class = _Row
    repo.table_name = "X"
    repo._field_types = {}

    assert repo._safe_row_to_model({"id": "a", "n": "not-int"}) is None
