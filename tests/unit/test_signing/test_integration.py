"""DSL → linker → router for `signable: true` (#1283 phase 5).

Closes the gap between hand-built ``EntitySpec`` unit tests and a real boot:
the DSL is parsed, linked by ``build_appspec``, and the signing-router factory
runs against the linked AppSpec. The DB layer is out of scope.
"""

from __future__ import annotations

import pathlib
import textwrap
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402

from dazzle.core import ir  # noqa: E402
from dazzle.core.linker import build_appspec  # noqa: E402
from dazzle.core.parser import parse_modules  # noqa: E402
from dazzle.http.runtime.route_validator import iter_http_route_contexts  # noqa: E402
from dazzle.signing.routes import create_signing_routes  # noqa: E402

_HEADER = 'module test\napp a "A"\n\n'
_SIGNABLE = (
    'entity Contract "Contract":\n  id: uuid pk\n  party: str(200) required\n'
    "  effective_date: date\n  signable: true\n"
    "  signing_validator: app.signing.validators.verify\n"
)
_TASK = 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'

_INJECTED = {
    "status",
    "signing_service",
    "signing_url",
    "signed_document",
    "signing_token_hash",
    "signer_ip",
    "signer_user_agent",
    "sent_at",
    "viewed_at",
    "signed_at",
    "expires_at",
}


def _appspec(body: str, tmp_path: pathlib.Path) -> ir.AppSpec:
    dsl = tmp_path / "test.dsl"
    dsl.write_text(_HEADER + textwrap.dedent(body))
    return build_appspec(parse_modules([dsl]), "test")


def _entity(appspec: ir.AppSpec, name: str) -> ir.EntitySpec:
    return next(e for e in appspec.domain.entities if e.name == name)


def test_linker_injects_signing_fields_and_audit(tmp_path: pathlib.Path) -> None:
    contract = _entity(_appspec(_SIGNABLE, tmp_path), "Contract")
    assert _INJECTED <= {f.name for f in contract.fields}
    assert (contract.signable, contract.signing_validator) == (
        True,
        "app.signing.validators.verify",
    )
    assert contract.audit is not None and contract.audit.enabled is True  # default when unset


def test_non_signable_entity_is_untouched(tmp_path: pathlib.Path) -> None:
    task = _entity(_appspec(_TASK, tmp_path), "Task")
    assert {f.name for f in task.fields} == {"id", "title"}
    assert (task.signable, task.audit) == (False, None)


def test_router_mounts_get_and_post_for_linked_signable_entity(tmp_path: pathlib.Path) -> None:
    router = create_signing_routes(
        list(_appspec(_SIGNABLE, tmp_path).domain.entities), repositories={}
    )
    assert router is not None
    app = FastAPI()
    app.include_router(router)
    routes = {
        (c.path, tuple(sorted(c.methods))) for c in iter_http_route_contexts(app) if c.methods
    }
    assert ("/sign/{entity_name}/{record_id}", ("GET",)) in routes
    assert ("/api/sign/{entity_name}/{record_id}", ("POST",)) in routes


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_TASK, id="no-signable-entity"),
        pytest.param(
            _TASK.replace('"Task":\n', '"Task":\n  signable: false\n'), id="signable-false-explicit"
        ),
    ],
)
def test_router_is_none_without_signable_entity(body: str, tmp_path: pathlib.Path) -> None:
    assert (
        create_signing_routes(list(_appspec(body, tmp_path).domain.entities), repositories={})
        is None
    )


@pytest.mark.parametrize(
    ("declared", "field", "attr", "expected"),
    [
        pytest.param(
            "status: enum[draft, signed_remote, signed_in_person, archived] required",
            "status",
            "enum_values",
            ["draft", "signed_remote", "signed_in_person", "archived"],
            id="project-status-enum-wins",
        ),
        pytest.param(
            "signing_url: str(2000)",
            "signing_url",
            "max_length",
            2000,
            id="project-widened-signing-url",
        ),
    ],
)
def test_project_declared_field_beats_auto_inject(
    declared: str, field: str, attr: str, expected: Any, tmp_path: pathlib.Path
) -> None:
    contract = _entity(
        _appspec(
            f'entity Contract "C":\n  id: uuid pk\n  party: str(200) required\n'
            f"  {declared}\n  signable: true\n",
            tmp_path,
        ),
        "Contract",
    )
    spec = next(f for f in contract.fields if f.name == field)
    assert getattr(spec.type, attr) == expected
