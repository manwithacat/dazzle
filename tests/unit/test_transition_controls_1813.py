"""#1813 — transition labels + confirms in the DSL, and ``row_transitions: none``.

AegisMark's legal records (an agreement, a parent's consent) must not offer a
one-click ``Set to Withdrawn`` next to a status badge. One gate per invariant:

- the transition grammar takes an optional label and ``confirm`` (bare or with
  a question) without breaking the guard forms;
- ``row_transitions:`` is validated to ``mode: list``;
- every transition control (list row, detail, queue) carries the authored label
  and asks the authored confirm on its own explicit click trigger (INV-10);
- ``row_transitions: none`` drops the controls from that list's rows only;
- the labelled control's PUT still fires the transition.
"""

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel
from starlette.testclient import TestClient

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation import validate_surfaces
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.handlers.list_handlers import build_data_table, list_state_transitions
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.http.runtime.route_generator import HandlerConfig, RouteSpec, create_update_handler
from dazzle.http.runtime.workspace_region_computes import compute_queue
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

_ID = "00000000-0000-4000-8000-000000000001"

_DSL = """\
module t
app t "T"

entity Agreement "Agreement":
  id: uuid pk
  title: str(200) required
  status: enum[draft,sent,signed,withdrawn]=draft
  transitions:
    draft -> sent "Send for signature" confirm "Email the signatory now?"
    sent -> withdrawn "Withdraw" confirm
    sent -> signed

surface agreement_list "Agreements":
  uses entity Agreement
  mode: list
  section main:
    field title "Title"
    field status "Status"

surface agreement_detail "Agreement":
  uses entity Agreement
  mode: view
  section main:
    field title "Title"
    field status "Status"
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


_APPSPEC = _appspec(_DSL)
_ENTITY = _APPSPEC.get_entity("Agreement")


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "label", "confirm", "guards"),
    [
        pytest.param("draft -> sent", None, None, 0, id="bare-edge-unchanged"),
        pytest.param('draft -> sent "Send"', "Send", None, 0, id="label-only"),
        pytest.param(
            'draft -> sent "Send" confirm "Email them?"',
            "Send",
            "Email them?",
            0,
            id="label-confirm",
        ),
        pytest.param(
            'draft -> sent "Send" confirm', "Send", "Send — are you sure?", 0, id="bare-confirm"
        ),
        pytest.param(
            "draft -> sent confirm",
            None,
            "Set to Sent — are you sure?",
            0,
            id="bare-confirm-default-label",
        ),
        pytest.param(
            'draft -> sent "Send" confirm "Sure?": role(admin)', "Send", "Sure?", 1, id="with-guard"
        ),
        pytest.param(
            'draft -> sent "Send" requires title', "Send", None, 1, id="colon-free-requires"
        ),
        pytest.param(
            'draft -> sent "Send" confirm:\n      role(admin)',
            "Send",
            "Send — are you sure?",
            1,
            id="block-form",
        ),
    ],
)
def test_transition_label_and_confirm_parse(
    line: str, label: str | None, confirm: str | None, guards: int
) -> None:
    dsl = (
        'module t\napp t "T"\nentity A "A":\n  id: uuid pk\n  title: str(20)\n'
        f"  status: enum[draft,sent]=draft\n  transitions:\n    {line}\n"
    )
    (t,) = _appspec(dsl).get_entity("A").state_machine.transitions
    assert (t.to_state, t.label, t.confirm, len(t.guards)) == ("sent", label, confirm, guards)


@pytest.mark.parametrize(
    ("mode", "error"),
    [pytest.param("list", False, id="list-ok"), pytest.param("view", True, id="view-refused")],
)
def test_row_transitions_only_on_list(mode: str, error: bool) -> None:
    dsl = _DSL + (
        f'\nsurface extra "Extra":\n  uses entity Agreement\n  mode: {mode}\n'
        '  row_transitions: none\n  section main:\n    field title "Title"\n'
    )
    spec = _appspec(dsl)
    assert spec.get_surface("extra").offers_row_transitions is False
    errors, _ = validate_surfaces(spec)
    assert any("row_transitions" in e for e in errors) is error


# ---------------------------------------------------------------------------
# Rendering — every control carries the label, the confirm and its own click
# ---------------------------------------------------------------------------


def _list_row_html(status: str) -> str:
    transitions, status_field, endpoint = list_state_transitions(
        convert_entity(_ENTITY), "Agreement"
    )
    table = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Agreement",
        "state_transitions": transitions,
        "status_field": status_field,
        "transition_endpoint": endpoint,
    }
    return render_data_table_rows(
        build_data_table(table, [{"id": _ID, "title": "A", "status": status}])
    )


class _RC:
    table = None
    form = None

    def __init__(self, detail: Any) -> None:
        self.detail = detail


def _detail_html(status: str) -> str:
    from dazzle.http.runtime.page_routes import gate_detail_transitions

    surface = _APPSPEC.get_surface("agreement_detail")
    detail = compile_surface_to_context(surface, _ENTITY, "/app").detail.model_copy(deep=True)
    detail.item = {"id": _ID, "title": "A", "status": status}
    detail.transitions = gate_detail_transitions(detail.transitions, detail.item, "status")
    ctx = _build_dispatch_ctx(_RC(detail), surface)
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(surface, ctx))


class _QueueRegion:
    name = "agreements"
    title = "Agreements"
    empty_message = "None"


def _queue_html(status: str) -> str:
    transitions, status_field, endpoint = compute_queue(convert_entity(_ENTITY), "Agreement")
    ctx = {
        "items": [{"id": _ID, "title": "A", "status": status}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "total": 1,
        "display_key": "title",
        "queue_status_field": status_field,
        "queue_api_endpoint": endpoint,
        "queue_transitions": transitions,
        "region_name": "agreements",
    }
    surface = WorkspaceRegionAdapter()._build_queue(_QueueRegion(), ctx)  # type: ignore[arg-type]
    return FragmentRenderer().render(surface)


def _control(html: str, label: str) -> str:
    """The opening tag of the button whose text is ``label``."""
    match = re.search(rf"<button\b[^>]*>\s*{re.escape(label)}\s*</button>", html)
    assert match, f"no control labelled {label!r} in:\n{html}"
    return match.group(0)


_CASES = [
    ("authored", "draft", "Send for signature", "Email the signatory now?"),
    ("bare-confirm", "sent", "Withdraw", "Withdraw \u2014 are you sure?"),
    ("default-label-no-confirm", "sent", "Set to Signed", None),
]
_RENDERS = [("list-row", _list_row_html), ("detail", _detail_html), ("queue", _queue_html)]


@pytest.mark.parametrize(
    ("render", "status", "label", "confirm"),
    [
        pytest.param(render, status, label, confirm, id=f"{case}-{where}")
        for case, status, label, confirm in _CASES
        for where, render in _RENDERS
        # The queue caps its row actions at two; the unlabelled third edge is
        # pinned on the list-row and detail controls.
        if not (where == "queue" and confirm is None)
    ],
)
def test_transition_control_label_and_confirm(
    render: Any, status: str, label: str, confirm: str | None
) -> None:
    html = render(status)
    assert "Set to Sent" not in html and "Set to Withdrawn" not in html
    tag = _control(html, label)
    assert 'hx-trigger="click"' in tag
    if confirm is None:
        assert "hx-confirm" not in tag
    else:
        assert f'hx-confirm="{confirm}"' in tag


# ---------------------------------------------------------------------------
# row_transitions: none — list rows only, through the /api row-hydrate route
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("row_transitions", "offered"),
    [
        pytest.param("", True, id="unset-offers"),
        pytest.param("  row_transitions: all\n", True, id="all-offers"),
        pytest.param("  row_transitions: none\n", False, id="none-drops"),
    ],
)
def test_row_transitions_none_drops_list_row_controls(row_transitions: str, offered: bool) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from dazzle.http.runtime.handlers.list_handlers import create_list_handler

    dsl = _DSL.replace("  mode: list\n", "  mode: list\n" + row_transitions, 1)
    surface = _appspec(dsl).get_surface("agreement_list")
    by_table = {
        "agreement_list": surface.offers_row_transitions,
        "dt-agreement_list": surface.offers_row_transitions,
    }
    service = MagicMock()
    service.entity_spec = convert_entity(_ENTITY)
    service.execute = AsyncMock(
        return_value={"items": [{"id": _ID, "title": "A", "status": "draft"}], "total": 1}
    )
    handler = create_list_handler(
        RouteSpec(handler=HandlerConfig(entity_name="Agreement"), service=service),
        htmx_columns=[{"key": "title", "label": "Title", "type": "text"}],
        htmx_entity_name="Agreement",
        htmx_row_transitions=all(by_table.values()),
        htmx_row_transitions_by_table_id=by_table,
    )
    app = FastAPI()
    app.get("/agreements")(handler)
    resp = TestClient(app).get(
        "/agreements",
        headers={"HX-Request": "true", "HX-Target": "dt-agreement_list-body"},
    )
    assert resp.status_code == 200
    assert ("Send for signature" in resp.text) is offered


# ---------------------------------------------------------------------------
# The labelled control still fires the transition
# ---------------------------------------------------------------------------


class _Update(BaseModel):
    title: str | None = None
    status: str | None = None


class _Model(BaseModel):
    id: Any = None
    title: str | None = None
    status: str | None = None


def test_labelled_control_put_fires_the_transition() -> None:
    from dazzle.http.runtime.service_generator import CRUDService

    spec = convert_entity(_ENTITY)
    service = CRUDService(
        entity_name="Agreement",
        model_class=_Model,
        create_schema=_Update,
        update_schema=_Update,
        state_machine=spec.state_machine,
        entity_spec=spec,
    )
    service._store[UUID(_ID)] = _Model(id=UUID(_ID), title="A", status="draft")
    handler = create_update_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Agreement"), service=service, input_schema=_Update
        )
    )
    app = FastAPI()

    @app.put("/agreements/{id}")
    async def _put(id: UUID, request: Request) -> Any:
        return await handler(id, request)

    tag = _control(_list_row_html("draft"), "Send for signature")
    put_url = re.search(r'hx-put="([^"]+)"', tag).group(1)  # type: ignore[union-attr]
    vals = json.loads(re.search(r"hx-vals='([^']+)'", tag).group(1))  # type: ignore[union-attr]
    resp = TestClient(app).put(put_url, data=vals)
    assert resp.status_code == 200, resp.text
    assert service._store[UUID(_ID)].status == "sent"
