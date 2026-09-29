"""A URL explains the same winning declaration the page compiler uses."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.cli.inspect import _live_page_html
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.page.inspection import explain_page, explain_workspace_region
from dazzle.page.route_owners import page_route_owners

ROOT = Path(__file__).resolve().parents[2]
RECORD_ID = "123e4567-e89b-12d3-a456-426614174000"


def test_payment_detail_url_names_its_owner_and_entity() -> None:
    project = ROOT / "examples/invoice_ops"
    result = explain_page(
        load_project_appspec(project), f"/app/paymentattempt/{RECORD_ID}?from_ws=pay_desk", project
    )

    assert result is not None
    assert result.route_pattern == "/app/paymentattempt/{id}"
    assert result.name == "payment_attempt_detail"
    assert result.source is not None and result.source.startswith("dsl/payments.dsl:")
    assert result.module == "invoice_ops.payments"
    assert [(ref.kind, ref.name) for ref in result.dependencies] == [("entity", "PaymentAttempt")]


def test_firmware_workspace_url_names_composed_declarations() -> None:
    project = ROOT / "examples/fieldtest_hub"
    result = explain_page(load_project_appspec(project), "/app/workspaces/draft_releases", project)

    assert result is not None
    assert result.name == "draft_releases"
    assert result.module == "fieldtest_hub.firmware"
    assert {(ref.kind, ref.name) for ref in result.dependencies} == {
        ("entity", "FirmwareRelease"),
        ("surface", "firmware_release_edit"),
    }


def test_workspace_region_traces_data_auth_fragment_and_action() -> None:
    project = ROOT / "examples/fieldtest_hub"
    appspec = load_project_appspec(project)
    page = explain_page(appspec, "/app/workspaces/engineering_dashboard", project)
    assert page is not None

    trace = explain_workspace_region(appspec, page, "triage_pressure", project)

    assert trace is not None
    assert trace.endpoint == "/api/workspaces/engineering_dashboard/regions/triage_pressure"
    assert trace.source_name == "IssueReport"
    assert trace.source_declaration is not None
    assert trace.source_declaration.startswith("dsl/app.dsl:")
    assert trace.display == "queue"
    assert trace.filter_ir is not None
    assert trace.sort_ir == [
        {"field": "severity", "direction": "desc"},
        {"field": "reported_at", "direction": "desc"},
    ]
    assert trace.limit == 4
    assert trace.workspace_access == "persona"
    assert trace.allowed_personas == ["engineer", "manager"]
    assert len(trace.list_permission_ir) == 1
    assert len(trace.list_scope_ir) == 2
    assert {persona for rule in trace.list_scope_ir for persona in rule["personas"]} == {
        "engineer",
        "manager",
        "tester",
    }
    assert trace.action_surface == "issue_report_edit"
    assert trace.action_declaration is not None
    assert trace.action_declaration.startswith("dsl/app.dsl:")
    assert trace.action_route == "/app/issuereport/{id}/edit"
    assert trace.mutation_method == "PUT"
    assert trace.mutation_endpoint == "/issuereports/{id}"


def test_region_trace_rejects_unknown_region_and_surface_page() -> None:
    project = ROOT / "examples/fieldtest_hub"
    appspec = load_project_appspec(project)
    workspace = explain_page(appspec, "/app/workspaces/engineering_dashboard", project)
    surface = explain_page(appspec, f"/app/issuereport/{RECORD_ID}/edit", project)
    assert workspace is not None and surface is not None
    assert explain_workspace_region(appspec, workspace, "unknown", project) is None
    assert explain_workspace_region(appspec, surface, "triage_pressure", project) is None


def test_inspect_page_reads_page_and_region_html_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def fake_html(url: str, *, origin: str, headers_file: Path | None) -> tuple[str, str]:
        assert headers_file is None
        assert origin == "http://localhost:3000"
        observed.append(url)
        return ("<html>page</html>" if len(observed) == 1 else "<div>region</div>"), url

    monkeypatch.setattr("dazzle.cli.inspect._live_page_html", fake_html)
    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "page",
            "/app/workspaces/engineering_dashboard",
            "-p",
            str(ROOT / "examples/fieldtest_hub"),
            "--region",
            "triage_pressure",
            "--html",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed == [
        "/app/workspaces/engineering_dashboard",
        "/api/workspaces/engineering_dashboard/regions/triage_pressure",
    ]
    payload = json.loads(result.output)
    assert payload["html"] == "<html>page</html>"
    assert payload["region_html"] == "<div>region</div>"


def test_unknown_url_does_not_invent_a_page_owner() -> None:
    project = ROOT / "examples/invoice_ops"
    assert explain_page(load_project_appspec(project), "/app/not-a-page", project) is None
    assert (
        explain_page(load_project_appspec(project), "/app/paymentattempt/not-a-uuid", project)
        is None
    )


def test_static_create_route_wins_before_dynamic_detail_route() -> None:
    project = ROOT / "examples/invoice_ops"
    result = explain_page(load_project_appspec(project), "/app/paymentattempt/create", project)
    assert result is not None
    assert result.name == "payment_attempt_create"


@pytest.mark.parametrize(
    "example",
    sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "dazzle.toml").exists()),
)
def test_inspection_route_index_matches_compiled_page_contexts(example: str) -> None:
    appspec = load_project_appspec(ROOT / "examples" / example)
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
    owners = page_route_owners(appspec, "/app")
    assert {route: owner.name for route, owner in owners.items()} == {
        route: context.view_name for route, context in contexts.items()
    }


class _Response:
    def __init__(self, final_url: str, *, redirect: bool = False) -> None:
        self.url = final_url
        self.is_redirect = redirect
        self.headers = {"content-type": "text/html"}
        self.encoding = "utf-8"

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self) -> list[bytes]:
        return [b"<html><main>Live page</main></html>"]


def test_live_html_reads_current_response_without_creating_a_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stream(method: str, target: str, **kwargs: Any) -> _Response:
        assert method == "GET"
        assert target == f"http://localhost:3000/app/paymentattempt/{RECORD_ID}"
        assert kwargs["timeout"] == 10.0
        assert kwargs["follow_redirects"] is False
        return _Response(target)

    monkeypatch.setattr("dazzle.cli.inspect.httpx.stream", fake_stream)
    html, fetched = _live_page_html(
        f"/app/paymentattempt/{RECORD_ID}", origin="http://localhost:3000", headers_file=None
    )
    assert html == "<html><main>Live page</main></html>"
    assert fetched == f"http://localhost:3000/app/paymentattempt/{RECORD_ID}"


def test_live_html_rejects_login_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dazzle.cli.inspect.httpx.stream",
        lambda *_args, **_kwargs: _Response("http://localhost:3000/login", redirect=True),
    )
    with pytest.raises(ValueError, match="redirected"):
        _live_page_html(
            f"/app/paymentattempt/{RECORD_ID}", origin="http://localhost:3000", headers_file=None
        )


def test_inspect_page_cli_reports_source() -> None:
    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "page",
            f"/app/paymentattempt/{RECORD_ID}",
            "-p",
            str(ROOT / "examples/invoice_ops"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "invoice_ops.payments" in result.output
    assert "dsl/payments.dsl:" in result.output
