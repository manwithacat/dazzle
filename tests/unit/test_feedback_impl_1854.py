"""The MCP ``feedback`` tool's read path (#1854, consumer-forced by aegismark).

Pins, through a real ``httpx.AsyncClient`` on an ``httpx.MockTransport`` (no
network):

* the remote target — ``DAZZLE_FEEDBACK_URL`` wins over ``.dazzle/runtime.json``
  and ``DAZZLE_FEEDBACK_COOKIE`` (``name=value``) over ``.dazzle/session.json``;
* every list filter reaching the query string, ``status`` as a comma list;
* grouping by ``review_session`` when any note carries one, today's envelope
  otherwise;
* ``anchor`` / ``context`` parsed whether the server sends objects or strings;
* ``summarise`` — by surface then severity, counts and the newest three notes;
* the MCP schema and dispatch exposing ``summarise`` and the new filters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from dazzle.cli import feedback_impl
from dazzle.mcp.server.handlers import feedback as handler_mod
from dazzle.mcp.server.tools_consolidated import _tool_feedback

_ENVELOPE: dict[str, Any] = {"items": [], "total": 0, "page": 1, "page_size": 20}


def _row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "r1",
        "status": "new",
        "category": "ux",
        "severity": "p2",
        "description": "Button label is wrong",
        "surface": "order_list",
        "review_session": None,
        "page_url": "https://app.test/app/orders",
        "created_at": "2026-10-25T10:00:00+00:00",
        "anchor": {"dz_anchor": "order_list/orders/row-1/edit"},
        "context": {"surface": "order_list"},
    }
    base.update(overrides)
    return base


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch):
    """Serve canned JSON; return the requests seen and a setter for the body."""
    seen: list[httpx.Request] = []
    state: dict[str, Any] = {"body": _ENVELOPE, "status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(
        feedback_impl,
        "_client",
        lambda cookies: httpx.AsyncClient(transport=httpx.MockTransport(handler), cookies=cookies),
    )
    monkeypatch.delenv(feedback_impl.FEEDBACK_URL_ENV, raising=False)
    monkeypatch.delenv(feedback_impl.FEEDBACK_COOKIE_ENV, raising=False)

    def respond(body: Any, status: int = 200) -> None:
        state["body"] = body
        state["status"] = status

    return seen, respond


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dz = tmp_path / ".dazzle"
    dz.mkdir()
    (dz / "runtime.json").write_text(json.dumps({"api_url": "http://127.0.0.1:3100"}))
    (dz / "session.json").write_text(json.dumps({"dazzle_session": "local-cookie"}))
    return tmp_path


def _query(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.url.query.decode())


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


async def test_local_target_reads_runtime_and_session_json(served, project) -> None:
    seen, _ = served
    await feedback_impl.feedback_list(project)
    [request] = seen
    assert str(request.url).startswith("http://127.0.0.1:3100/feedbackreports?")
    assert request.headers["cookie"] == "dazzle_session=local-cookie"


async def test_env_url_wins_over_runtime_json(served, project, monkeypatch) -> None:
    seen, _ = served
    monkeypatch.setenv(feedback_impl.FEEDBACK_URL_ENV, "https://www.app.test/")
    await feedback_impl.feedback_list(project)
    [request] = seen
    assert request.url.scheme == "https"
    assert request.url.host == "www.app.test"
    assert request.url.path == "/feedbackreports"


async def test_env_cookie_wins_over_session_json(served, project, monkeypatch) -> None:
    seen, _ = served
    monkeypatch.setenv(feedback_impl.FEEDBACK_COOKIE_ENV, " __Host-dz_session = abc=def ")
    await feedback_impl.feedback_get("r1", project)
    [request] = seen
    assert request.url.path == "/feedbackreports/r1"
    # the value keeps its own "=" and the surrounding whitespace is dropped
    assert request.headers["cookie"] == "__Host-dz_session=abc=def"


async def test_malformed_env_cookie_falls_back_to_session_json(
    served, project, monkeypatch
) -> None:
    seen, _ = served
    monkeypatch.setenv(feedback_impl.FEEDBACK_COOKIE_ENV, "no-equals-sign")
    await feedback_impl.feedback_get("r1", project)
    [request] = seen
    assert request.headers["cookie"] == "dazzle_session=local-cookie"


def test_env_vars_resolve_without_a_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(feedback_impl.FEEDBACK_URL_ENV, "https://demo.app.test")
    monkeypatch.setenv(feedback_impl.FEEDBACK_COOKIE_ENV, "s=v")
    assert feedback_impl._get_server_url(tmp_path) == "https://demo.app.test"
    assert feedback_impl._auth_cookies(tmp_path) == {"s": "v"}


# ---------------------------------------------------------------------------
# feedback_list: filters
# ---------------------------------------------------------------------------


async def test_list_default_sends_only_page_size(served, project) -> None:
    seen, _ = served
    await feedback_impl.feedback_list(project)
    assert _query(seen[0]) == {"page_size": ["20"]}


@pytest.mark.parametrize(
    ("kwarg", "value", "param", "expected"),
    [
        pytest.param("status", "new", "status", "new", id="status"),
        pytest.param("status", "new, triaged ,", "status", "new,triaged", id="status-csv"),
        pytest.param("category", "ux", "category", "ux", id="category"),
        pytest.param("severity", "p1", "severity", "p1", id="severity"),
        pytest.param("surface", "order_list", "surface", "order_list", id="surface"),
        pytest.param(
            "review_session", "2026-10-25-ab12", "review_session", "2026-10-25-ab12", id="session"
        ),
        pytest.param(
            "page_url",
            "https://app.test/app/orders",
            "page_url",
            "https://app.test/app/orders",
            id="page_url",
        ),
        pytest.param(
            "since", "2026-10-25T00:00:00+00:00", "since", "2026-10-25T00:00:00+00:00", id="since"
        ),
        pytest.param("limit", 50, "page_size", "50", id="limit"),
    ],
)
async def test_each_list_filter_reaches_the_query_string(
    served, project, kwarg: str, value: Any, param: str, expected: str
) -> None:
    seen, _ = served
    await feedback_impl.feedback_list(project, **{kwarg: value})
    query = _query(seen[0])
    assert query[param] == [expected]
    # nothing else leaks in
    assert set(query) <= {"page_size", param}


async def test_list_combines_every_filter(served, project) -> None:
    seen, _ = served
    await feedback_impl.feedback_list(
        project,
        status="new,triaged",
        category="ux",
        severity="p1",
        surface="order_list",
        review_session="2026-10-25-ab12",
        page_url="https://app.test/app/orders",
        since="2026-10-25T00:00:00Z",
        limit=5,
    )
    assert _query(seen[0]) == {
        "page_size": ["5"],
        "status": ["new,triaged"],
        "category": ["ux"],
        "severity": ["p1"],
        "surface": ["order_list"],
        "review_session": ["2026-10-25-ab12"],
        "page_url": ["https://app.test/app/orders"],
        "since": ["2026-10-25T00:00:00Z"],
    }


async def test_list_raises_on_http_error(served, project) -> None:
    _, respond = served
    respond({"detail": "Not authenticated"}, status=401)
    with pytest.raises(httpx.HTTPStatusError):
        await feedback_impl.feedback_list(project)


# ---------------------------------------------------------------------------
# feedback_list: shape
# ---------------------------------------------------------------------------


async def test_list_without_sessions_keeps_the_envelope(served, project) -> None:
    _, respond = served
    respond({"items": [_row(id="a"), _row(id="b")], "total": 2, "page": 1, "page_size": 20})
    result = await feedback_impl.feedback_list(project)
    assert set(result) == {"items", "total", "page", "page_size"}
    assert [r["id"] for r in result["items"]] == ["a", "b"]
    assert result["total"] == 2


async def test_list_groups_by_review_session_when_any_item_has_one(served, project) -> None:
    _, respond = served
    respond(
        {
            "items": [
                _row(id="a", review_session="2026-10-25-ab12"),
                _row(id="b"),
                _row(id="c", review_session="2026-10-24-zz99"),
                _row(id="d", review_session="2026-10-25-ab12"),
            ],
            "total": 40,
            "page": 1,
            "page_size": 4,
        }
    )
    result = await feedback_impl.feedback_list(project)
    assert set(result) == {"sessions", "ungrouped", "total"}
    assert result["total"] == 40
    assert [(s["review_session"], s["count"]) for s in result["sessions"]] == [
        ("2026-10-25-ab12", 2),
        ("2026-10-24-zz99", 1),
    ]
    assert [r["id"] for r in result["sessions"][0]["items"]] == ["a", "d"]
    assert [r["id"] for r in result["ungrouped"]] == ["b"]


async def test_list_wraps_a_bare_list_from_an_older_server(served, project) -> None:
    _, respond = served
    respond([_row(id="a")])
    result = await feedback_impl.feedback_list(project)
    assert result["total"] == 1
    assert result["items"][0]["id"] == "a"


# ---------------------------------------------------------------------------
# anchor / context parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anchor", "context"),
    [
        pytest.param(
            {"dz_anchor": "order_list/orders/row-1/edit", "css": "#edit-1"},
            {"surface": "order_list", "console_errors": []},
            id="objects",
        ),
        pytest.param(
            json.dumps({"dz_anchor": "order_list/orders/row-1/edit", "css": "#edit-1"}),
            json.dumps({"surface": "order_list", "console_errors": []}),
            id="json-strings",
        ),
    ],
)
async def test_get_parses_anchor_and_context_in_both_shapes(
    served, project, anchor: Any, context: Any
) -> None:
    _, respond = served
    respond(_row(anchor=anchor, context=context))
    result = await feedback_impl.feedback_get("r1", project)
    assert result["anchor"] == {"dz_anchor": "order_list/orders/row-1/edit", "css": "#edit-1"}
    assert result["context"] == {"surface": "order_list", "console_errors": []}


async def test_list_parses_anchor_and_context_on_every_item(served, project) -> None:
    _, respond = served
    respond(
        {
            "items": [_row(id="a", anchor='{"css": "#a"}', context='{"surface": "x"}')],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }
    )
    result = await feedback_impl.feedback_list(project)
    assert result["items"][0]["anchor"] == {"css": "#a"}
    assert result["items"][0]["context"] == {"surface": "x"}


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="null"),
        pytest.param("", id="empty"),
        pytest.param("not json", id="plain-text"),
        pytest.param("{broken", id="malformed"),
        pytest.param(["a", "b"], id="list"),
    ],
)
def test_parse_json_field_leaves_non_json_untouched(value: Any) -> None:
    assert feedback_impl._parse_json_field(value) == value


# ---------------------------------------------------------------------------
# feedback_summarise
# ---------------------------------------------------------------------------


_SUMMARY_ROWS = [
    _row(id="1", surface="order_list", severity="p1", created_at="2026-10-25T10:00:00Z"),
    _row(
        id="2",
        surface="order_list",
        severity="p2",
        created_at="2026-10-25T12:00:00Z",
        description="newest",
    ),
    _row(id="3", surface="order_list", severity="p1", created_at="2026-10-25T09:00:00Z"),
    _row(
        id="4",
        surface="order_list",
        severity="note",
        created_at="2026-10-25T08:00:00Z",
        description="oldest",
    ),
    _row(id="5", surface="customer_detail", severity="p3", created_at="2026-10-25T11:00:00Z"),
    # no top-level surface: falls back to context.surface
    _row(id="6", surface=None, context={"surface": "customer_detail"}, severity="p3"),
    # neither: lands in "(no surface)"
    _row(id="7", surface=None, context="plain", severity="p2", description="x" * 300),
]


async def test_summarise_defaults_to_open_statuses_and_a_wide_page(served, project) -> None:
    seen, _ = served
    await feedback_impl.feedback_summarise(project)
    assert _query(seen[0]) == {"page_size": ["200"], "status": ["new,triaged"]}


async def test_summarise_passes_status_and_since(served, project) -> None:
    seen, _ = served
    await feedback_impl.feedback_summarise(
        project, status="new", since="2026-10-25T00:00:00Z", limit=50
    )
    assert _query(seen[0]) == {
        "page_size": ["50"],
        "status": ["new"],
        "since": ["2026-10-25T00:00:00Z"],
    }


async def test_summarise_groups_by_surface_then_severity(served, project) -> None:
    _, respond = served
    respond({"items": _SUMMARY_ROWS, "total": 7, "page": 1, "page_size": 200})
    result = await feedback_impl.feedback_summarise(project)

    assert result["status"] == "new,triaged"
    assert result["total"] == 7
    assert result["fetched"] == 7

    surfaces = result["surfaces"]
    assert [s["surface"] for s in surfaces] == ["order_list", "customer_detail", "(no surface)"]

    orders = surfaces[0]
    assert orders["count"] == 4
    # most frequent severity first, ties by name
    assert list(orders["by_severity"].items()) == [("p1", 2), ("note", 1), ("p2", 1)]
    # newest three descriptions, newest first
    assert [n["id"] for n in orders["latest"]] == ["2", "1", "3"]
    assert orders["latest"][0]["description"] == "newest"
    assert {
        "id",
        "severity",
        "category",
        "status",
        "created_at",
        "review_session",
        "description",
    } <= set(orders["latest"][0])

    customers = surfaces[1]
    assert customers["count"] == 2
    assert customers["by_severity"] == {"p3": 2}

    orphan = surfaces[2]
    assert orphan["by_severity"] == {"p2": 1}
    assert len(orphan["latest"][0]["description"]) == 240
    assert orphan["latest"][0]["description"].endswith("…")


def test_summarise_reports_is_pure_and_handles_empty() -> None:
    assert feedback_impl.summarise_reports([]) == []


async def test_summarise_reports_server_total_beyond_the_page(served, project) -> None:
    _, respond = served
    respond({"items": [_row()], "total": 400, "page": 1, "page_size": 200})
    result = await feedback_impl.feedback_summarise(project)
    assert (result["total"], result["fetched"]) == (400, 1)


# ---------------------------------------------------------------------------
# Writes keep their contract
# ---------------------------------------------------------------------------


async def test_triage_and_resolve_put_the_status_payload(served, project, monkeypatch) -> None:
    seen, respond = served
    monkeypatch.setenv(feedback_impl.FEEDBACK_URL_ENV, "https://app.test")
    monkeypatch.setenv(feedback_impl.FEEDBACK_COOKIE_ENV, "s=v")
    respond(_row(status="triaged"))
    await feedback_impl.feedback_triage(
        "r1", project, agent_notes="seen", agent_classification="bug", assigned_to="me"
    )
    respond(_row(status="resolved"))
    await feedback_impl.feedback_resolve("r1", project, agent_notes="fixed", resolved_by="me")

    triage, resolve = seen
    assert (triage.method, triage.url.path) == ("PUT", "/feedbackreports/r1")
    assert json.loads(triage.content) == {
        "status": "triaged",
        "agent_notes": "seen",
        "agent_classification": "bug",
        "assigned_to": "me",
    }
    assert triage.headers["cookie"] == "s=v"
    assert json.loads(resolve.content) == {
        "status": "resolved",
        "agent_notes": "fixed",
        "resolved_by": "me",
    }


# ---------------------------------------------------------------------------
# MCP tool schema, handlers and dispatch
# ---------------------------------------------------------------------------


def test_tool_schema_exposes_summarise_and_the_new_filters() -> None:
    tool = _tool_feedback()
    props = tool.input_schema["properties"]
    assert props["operation"]["enum"] == ["list", "get", "summarise", "triage", "resolve"]
    for name in ("since", "surface", "review_session", "page_url", "status"):
        assert props[name]["type"] == "string", name
    assert "DAZZLE_FEEDBACK_URL" in (tool.description or "")
    assert "DAZZLE_FEEDBACK_COOKIE" in (tool.description or "")


def test_dispatch_table_routes_summarise() -> None:
    from dazzle.mcp.server import handlers_consolidated as hc

    ops = hc._resolve_ops(
        {
            "summarise": f"{hc._MOD_FEEDBACK}:summarise_handler",
            "list": f"{hc._MOD_FEEDBACK}:list_handler",
        }
    )
    assert callable(ops["summarise"])
    # the wired handler accepts the operation (unknown ops return an error JSON)
    unknown = json.loads(hc.handle_feedback({"operation": "nope", "project_path": "/nowhere"}))
    assert "error" in unknown


def test_list_handler_forwards_every_filter(served, project) -> None:
    seen, _ = served
    out = handler_mod.list_handler(
        project,
        {
            "status": "new,triaged",
            "surface": "order_list",
            "review_session": "2026-10-25-ab12",
            "page_url": "https://app.test/app/orders",
            "since": "2026-10-25T00:00:00Z",
            "limit": "7",
        },
    )
    assert json.loads(out)["total"] == 0
    assert _query(seen[0]) == {
        "page_size": ["7"],
        "status": ["new,triaged"],
        "surface": ["order_list"],
        "review_session": ["2026-10-25-ab12"],
        "page_url": ["https://app.test/app/orders"],
        "since": ["2026-10-25T00:00:00Z"],
    }


def test_summarise_handler_returns_grouped_json(served, project) -> None:
    seen, respond = served
    respond({"items": _SUMMARY_ROWS[:2], "total": 2, "page": 1, "page_size": 200})
    out = json.loads(handler_mod.summarise_handler(project, {}))
    assert _query(seen[0])["status"] == ["new,triaged"]
    assert out["surfaces"][0]["surface"] == "order_list"
    assert out["surfaces"][0]["by_severity"] == {"p1": 1, "p2": 1}


def test_get_handler_parses_anchor(served, project) -> None:
    _, respond = served
    respond(_row(anchor='{"css": "#a"}'))
    out = json.loads(handler_mod.get_handler(project, {"id": "r1"}))
    assert out["anchor"] == {"css": "#a"}
    assert json.loads(handler_mod.get_handler(project, {})) == {"error": "id is required"}
