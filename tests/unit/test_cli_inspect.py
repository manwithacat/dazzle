"""Unit tests for ``dazzle inspect <ext-point>`` (#1120, v0.71.23).

Five subcommands:
  - inspect renderers
  - inspect primitives
  - inspect routes
  - inspect oauth-providers
  - inspect api (renamed from `dazzle inspect-api`)

Each supports manifest-only (default, fast) and --runtime (slow, boots
the app and cross-references). Output is human-readable by default;
--json emits structured output for agent consumption.

These tests cover the manifest-only paths only — the --runtime path
needs a working PostgreSQL connection to boot the app, which is
opt-in (CI-only via pytest's postgres marker).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tests.unit.helpers.cli import invoke, run_cli


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Build a minimal Dazzle project under tmp_path with a manifest
    declaring custom renderers + extension routers + OAuth providers."""
    (tmp_path / "dazzle.toml").write_text(
        textwrap.dedent("""\
            [project]
            name = "inspect-test"
            version = "0.1.0"
            root = "inspect_test.core"

            [modules]
            paths = ["./dsl"]

            [renderers]
            extra = ["word_cloud", "branch_compare"]

            [extensions]
            routers = ["app.api.graph:router"]

            [[auth.oauth_providers]]
            provider = "google"
            client_id_env = "GOOGLE_CLIENT_ID"
            client_secret_env = "GOOGLE_CLIENT_SECRET"
            scopes = ["openid", "email"]

            [[auth.oauth_providers]]
            provider = "github"
            client_id_env = "GITHUB_CLIENT_ID"
            client_secret_env = "GITHUB_CLIENT_SECRET"
            scopes = ["user:email"]
        """)
    )
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "main.dsl").write_text(
        textwrap.dedent("""\
            module inspect_test.core
            app inspect_test "Inspect Test"

            entity Task "Task":
              id: uuid pk
              title: str(200) required
        """)
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Manifest-only output: command -> fragments that must appear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "fragments"),
    [
        pytest.param(
            ["inspect", "--help"],
            ["renderers", "primitives", "routes", "oauth-providers", "api", "rls"],
            id="inspect_help_lists_every_ext_point",
        ),
        pytest.param(
            ["inspect", "api", "--help"],
            ["dsl-constructs", "ir-types", "mcp-tools", "public-helpers", "runtime-urls"],
            id="inspect_api_help_keeps_the_old_inspect_api_subcommands",
        ),
        pytest.param(
            ["inspect", "renderers", "--project", "{project}"],
            ["fragment", "word_cloud", "branch_compare", "Manifest-only view", "--runtime"],
            id="renderers_lists_defaults_and_manifest_extra_with_runtime_note",
        ),
        pytest.param(
            ["inspect", "routes", "--project", "{project}"],
            ["app.api.graph:router"],
            id="routes_lists_extensions_routers",
        ),
        pytest.param(
            ["inspect", "oauth-providers", "--project", "{project}"],
            ["google", "github", "GOOGLE_CLIENT_ID", "user:email"],
            id="oauth_providers_lists_providers_env_vars_and_scopes",
        ),
        pytest.param(
            ["inspect", "primitives", "--project", "{project}"],
            ["(none)", "--runtime", "@primitive decorator"],
            id="primitives_manifest_only_explains_runtime_opt_in",
        ),
    ],
)
def test_inspect_manifest_only_output(
    project_root: Path, args: list[str], fragments: list[str]
) -> None:
    out = run_cli([a.format(project=project_root) for a in args])
    for fragment in fragments:
        assert fragment in out, f"{fragment!r} missing from `dazzle {' '.join(args)}`"


@pytest.mark.parametrize(
    ("ext_point", "framework", "manifest"),
    [
        pytest.param("renderers", {"fragment"}, {"word_cloud", "branch_compare"}, id="renderers"),
        pytest.param("oauth-providers", set(), {"google", "github"}, id="oauth_providers"),
    ],
)
def test_inspect_json_flags_entry_source(
    project_root: Path, ext_point: str, framework: set[str], manifest: set[str]
) -> None:
    payload = json.loads(run_cli(["inspect", ext_point, "--project", project_root, "--json"]))
    assert payload["ext_point"] == ext_point
    by_name = {e["name"]: e["source"] for e in payload["entries"]}
    assert framework <= by_name.keys() and manifest <= by_name.keys()
    assert all(by_name[n] == "framework" for n in framework)
    assert all(by_name[n] == "manifest" for n in manifest)


def test_inspect_renderers_exits_2_when_no_dazzle_toml(tmp_path: Path) -> None:
    """Outside a Dazzle project the command fails as a usage error (exit 2), not a crash."""
    run_cli(["inspect", "renderers", "--project", tmp_path], exit_code=2)


def test_inspect_routes_empty_when_no_extensions_declared(tmp_path: Path) -> None:
    """A manifest without [extensions] yields zero entries and must not crash."""
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "empty"\nversion = "0.1.0"\n\n[modules]\npaths = ["./dsl"]\n'
    )
    assert "(none)" in run_cli(["inspect", "routes", "--project", tmp_path])


def test_old_inspect_api_top_level_is_gone() -> None:
    """#1120 clean break: `dazzle inspect-api` is removed; restoring it must be intentional."""
    assert invoke(["inspect-api", "--help"]).exit_code != 0


def test_inspect_api_dsl_constructs_emits_snapshot() -> None:
    """Pure introspection to stdout; contents are project-state-driven, so only
    the presence of a construct name is pinned."""
    assert "entity" in run_cli(["inspect", "api", "dsl-constructs"])


def test_categorise_route_buckets_each_route_kind() -> None:
    """The --runtime walk buckets every live route so an agent can tell
    a traceable page route from framework plumbing."""
    from dazzle.cli.inspect import _categorise_route

    ws = frozenset({"command_center"})
    assert _categorise_route("/api/workspaces/x/regions/y", ws) == "api"
    assert _categorise_route("/_dazzle/health", ws) == "internal"
    assert _categorise_route("/static/app.css", ws) == "internal"
    assert _categorise_route("/docs", ws) == "docs"
    assert _categorise_route("/openapi.json", ws) == "docs"
    assert _categorise_route("/login", ws) == "auth"
    assert _categorise_route("/auth/login/password", ws) == "auth"
    assert _categorise_route("/command_center/alerts", ws) == "workspace"
    assert _categorise_route("/alerts", ws) == "surface"
    assert _categorise_route("/alerts/{id}", ws) == "surface"
    # Without the AppSpec, workspace routes degrade to "surface" — never crash.
    assert _categorise_route("/command_center/alerts", frozenset()) == "surface"


def test_walk_runtime_routes_categorises_sorts_and_strips_head_options() -> None:
    """The runtime walk buckets routes, sorts page-routes-first, drops
    pathless routes, and strips Starlette's auto-added HEAD/OPTIONS."""
    from types import SimpleNamespace

    from dazzle.cli.inspect import _walk_runtime_routes

    routes = [
        SimpleNamespace(path="/api/workspaces/x", methods={"GET"}),
        SimpleNamespace(path="/alerts", methods={"GET", "HEAD"}),
        SimpleNamespace(path="/command_center/alerts", methods={"GET", "POST", "OPTIONS"}),
        SimpleNamespace(path="/login", methods={"GET"}),
        SimpleNamespace(path="", methods={"GET"}),  # pathless — dropped
        SimpleNamespace(path=None, methods=None),  # pathless — dropped
    ]
    entries = _walk_runtime_routes(routes, frozenset({"command_center"}))

    # Pathless routes dropped; rest sorted workspace < surface < auth < api.
    assert [e.name for e in entries] == [
        "/command_center/alerts",
        "/alerts",
        "/login",
        "/api/workspaces/x",
    ]
    assert [e.detail.split()[0] for e in entries] == ["workspace", "surface", "auth", "api"]
    # HEAD/OPTIONS stripped, real verbs kept.
    assert entries[0].detail == "workspace  GET POST"
    assert entries[1].detail == "surface  GET"


def test_inspect_routes_runtime_without_db_hints_at_database_url(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--runtime can't boot without a database — the failure note must
    tell the agent to set DATABASE_URL rather than fail silently."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    out = run_cli(["inspect", "routes", "--project", project_root, "--runtime"])
    assert "DATABASE_URL" in out
