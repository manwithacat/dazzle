"""#1787 — surface-action ``visible:`` and render-time state-machine guards.

One parametrised gate per invariant:

- the validator names the surface, action and predicate for a bad ``visible:``
  (actions, sections and fields alike);
- the detail page hides an action whose predicate is false (record state or
  role) and field ``visible:`` sees the record;
- a transition whose ``requires_role`` guard refuses the principal is not
  offered — on the detail page and on a list row;
- the manual-trigger POST behind ``integration X action Y`` refuses (403, the
  predicate in the detail) when the predicate is false.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation import validate_surfaces
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.action_visibility import condition_context, refused_row_transitions
from dazzle.http.runtime.handlers.list_handlers import build_data_table, list_state_transitions
from dazzle.http.runtime.page_routes import DetailPrincipal, gate_detail_affordances
from dazzle.http.runtime.subsystems.system_routes import SystemRoutesSubsystem
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

_RECORD_ID = "00000000-0000-4000-8000-000000000001"

_BASE = """\
module t
app t "T"

persona agent "Agent":
  description: "Staff"
persona manager "Manager":
  description: "Staff lead"
persona client "Client":
  description: "Customer"

entity Request "Request":
  id: uuid pk
  title: str(200) required
  status: enum[draft,sent,received]=draft
  nino_source: enum[client,hmrc] optional
  transitions:
    draft -> sent: role(agent)
    sent -> received: role(manager)

integration hmrc:
  mapping verify on Request:
    trigger: manual "Verify with HMRC"
    request: GET "/verify"
"""

_SURFACE = """
surface request_detail "Request":
  uses entity Request
  mode: view
  section main:
    field title "Title"
    field status "Status"
    field nino_source "NINO source" visible: status = sent
  action send_letter "Send letter":
    visible: status = draft and (role(agent) or role(manager))
    on click -> "/requests/{id}/letter" external
  action reconcile "Reconcile with HMRC":
    on click -> integration hmrc action verify
    visible: nino_source = client and role(agent)
"""


def _appspec(dsl: str) -> Any:
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    module = ModuleIR(
        name=n or "t",
        file=Path("t.dsl"),
        app_name=a,
        app_title=t,
        app_config=c,
        uses=u,
        fragment=frag,
    )
    return build_appspec([module], "t")


_APPSPEC = _appspec(_BASE + _SURFACE)


def _auth(roles: list[str]) -> Any:
    return SimpleNamespace(
        is_authenticated=True,
        active_membership=None,
        roles=roles,
        user=SimpleNamespace(id="11111111-1111-4111-8111-111111111111", roles=roles),
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("surface_tail", "expected"),
    [
        pytest.param(
            '  action a "A":\n    visible: status = draft and role(agent)\n'
            '    on click -> "/x" external\n',
            None,
            id="valid-field-and-role",
        ),
        pytest.param(
            '  action a "A":\n    visible: stauts = draft\n    on click -> "/x" external\n',
            "Surface 'request_detail' action 'a' visible: `stauts = draft` references "
            "non-existent field 'stauts'",
            id="unknown-field",
        ),
        pytest.param(
            '  action a "A":\n    visible: role(auditor)\n    on click -> "/x" external\n',
            "Surface 'request_detail' action 'a' visible: `role(auditor)` references "
            "role(auditor) but no persona 'auditor' is declared",
            id="unknown-role",
        ),
        pytest.param(
            '  action a "A":\n    visible: title.owner = x\n    on click -> "/x" external\n',
            "field 'title' is not a reference field",
            id="fk-path-through-non-ref",
        ),
        pytest.param(
            '  action a "A":\n    visible: status = draft and current_user.team = x\n'
            '    on click -> "/x" external\n',
            None,
            id="current-user-path-is-context-not-a-field",
        ),
        pytest.param(
            '  action a "A":\n    visible: role(agent)\n    on click -> integration hmrc action nope\n',
            "is not a mapping with a manual trigger",
            id="integration-outcome-must-be-manual-mapping",
        ),
        pytest.param(
            '  section extra:\n    visible: role(ghost)\n    field title "T"\n',
            "Surface 'request_detail' section 'extra' visible: `role(ghost)`",
            id="section-visible-validated",
        ),
        pytest.param(
            '  section extra:\n    field title "T" visible: titel = x\n',
            "Surface 'request_detail' field 'title' visible: `titel = x` references "
            "non-existent field 'titel'",
            id="field-visible-validated",
        ),
    ],
)
def test_visible_predicates_validated(surface_tail: str, expected: str | None) -> None:
    dsl = (
        _BASE
        + '\nsurface request_detail "Request":\n  uses entity Request\n  mode: view\n'
        + '  section main:\n    field title "Title"\n'
        + surface_tail
    )
    errors, _ = validate_surfaces(_appspec(dsl))
    visible_errors = [e for e in errors if "visible" in e]
    if expected is None:
        assert visible_errors == []
    else:
        assert any(expected in e for e in visible_errors), visible_errors


# ---------------------------------------------------------------------------
# Detail page gating
# ---------------------------------------------------------------------------


def _gated_detail(record: dict[str, Any], roles: list[str]) -> Any:
    surface = _APPSPEC.get_surface("request_detail")
    entity = _APPSPEC.get_entity("Request")
    detail = compile_surface_to_context(surface, entity, "/app").detail.model_copy(deep=True)
    detail.item = record
    # Mirror the runtime: manual triggers are injected onto the detail context.
    from dazzle.render.context import IntegrationActionContext

    detail.integration_actions = [
        IntegrationActionContext(
            label="Verify with HMRC",
            integration_name="hmrc",
            mapping_name="verify",
            api_url="/requests/{id}/integrations/hmrc/verify",
        )
    ]
    gate_detail_affordances(
        detail,
        appspec=_APPSPEC,
        surface=surface,
        principal=DetailPrincipal(
            roles=roles,
            current_user="u1",
            condition_ctx=condition_context(user_roles=roles, current_user_id="u1"),
        ),
        state_machine=convert_entity(entity).state_machine,
    )
    return detail


@pytest.mark.parametrize(
    ("record", "roles", "links", "integrations", "transitions", "nino_visible"),
    [
        pytest.param(
            {"status": "draft", "nino_source": "client"},
            ["agent"],
            ["send_letter"],
            ["verify"],
            ["sent"],
            False,
            id="agent-on-draft-sees-letter-reconcile-and-send",
        ),
        pytest.param(
            {"status": "sent", "nino_source": "client"},
            ["agent"],
            [],
            ["verify"],
            [],  # sent -> received is role(manager)
            True,
            id="state-hides-letter-guard-hides-transition-field-sees-record",
        ),
        pytest.param(
            {"status": "draft", "nino_source": "client"},
            ["client"],
            [],
            [],
            [],
            False,
            id="role-hides-actions-and-transition",
        ),
        pytest.param(
            {"status": "sent", "nino_source": "hmrc"},
            ["role_manager"],
            [],
            [],
            ["received"],
            True,
            id="manager-offered-received-integration-hidden-by-record",
        ),
    ],
)
def test_detail_affordances_gated(
    record: dict[str, Any],
    roles: list[str],
    links: list[str],
    integrations: list[str],
    transitions: list[str],
    nino_visible: bool,
) -> None:
    detail = _gated_detail(record, roles)
    assert [a.name for a in detail.external_link_actions] == links
    assert [a.mapping_name for a in detail.integration_actions] == integrations
    assert [t.to_state for t in detail.transitions] == transitions
    nino = next(f for f in detail.fields if f.name == "nino_source")
    assert nino.visible is nino_visible


# ---------------------------------------------------------------------------
# List rows (C)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("roles", "offered"),
    [
        pytest.param(["agent"], True, id="role-holder-offered"),
        pytest.param(["client"], False, id="role-lacking-not-offered"),
    ],
)
def test_list_row_transition_honours_requires_role(roles: list[str], offered: bool) -> None:
    entity_spec = convert_entity(_APPSPEC.get_entity("Request"))
    transitions, status_field, endpoint = list_state_transitions(entity_spec, "Request")
    items = [{"id": _RECORD_ID, "title": "R", "status": "draft"}]
    table = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Request",
        "state_transitions": transitions,
        "status_field": status_field,
        "transition_endpoint": endpoint,
        "refused_transitions": refused_row_transitions(
            entity_spec.state_machine, items, transitions, status_field, _auth(roles)
        ),
    }
    html = render_data_table_rows(build_data_table(table, items))
    assert ("dz-tr-transition" in html) is offered


# ---------------------------------------------------------------------------
# Integration POST refusal (B)
# ---------------------------------------------------------------------------


def _trigger_client(record: dict[str, Any], roles: list[str]) -> TestClient:
    app = FastAPI()
    repo = MagicMock()
    repo.read = AsyncMock(return_value={"id": _RECORD_ID, **record})
    executor = MagicMock()
    executor.execute_manual = AsyncMock(
        return_value=SimpleNamespace(success=True, message="ok", mapped_fields={}, cache_hit=False)
    )
    ctx = SimpleNamespace(
        app=app,
        appspec=_APPSPEC,
        repositories={"Request": repo},
        auth_middleware=SimpleNamespace(get_auth_context=lambda _req: _auth(roles)),
        auth_config=None,
    )
    SystemRoutesSubsystem()._register_manual_trigger_routes(ctx, executor)  # type: ignore[arg-type]
    return TestClient(app)


@pytest.mark.parametrize(
    ("record", "roles", "status"),
    [
        pytest.param({"nino_source": "client"}, ["agent"], 200, id="predicate-true-runs"),
        pytest.param({"nino_source": "hmrc"}, ["agent"], 403, id="record-state-refused"),
        pytest.param({"nino_source": "client"}, ["client"], 403, id="role-refused"),
    ],
)
def test_integration_trigger_refuses_when_predicate_false(
    record: dict[str, Any], roles: list[str], status: int
) -> None:
    resp = _trigger_client(record, roles).post(f"/requests/{_RECORD_ID}/integrations/hmrc/verify")
    assert resp.status_code == status
    if status == 403:
        detail = resp.json()["detail"]
        assert "surface 'request_detail' action 'reconcile'" in detail
        assert "visible: nino_source = client and role(agent)" in detail
