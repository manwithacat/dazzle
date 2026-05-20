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
from typer.testing import CliRunner

from dazzle.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


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
# Top-level group
# ---------------------------------------------------------------------------


def test_inspect_help_lists_all_subcommands(runner: CliRunner) -> None:
    """`dazzle inspect --help` must list the five subcommands. If a
    new ext-point is added, it must be wired in alongside these."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    for subcommand in ("renderers", "primitives", "routes", "oauth-providers", "api"):
        assert subcommand in result.stdout, f"`inspect {subcommand}` missing from help"


# ---------------------------------------------------------------------------
# inspect renderers
# ---------------------------------------------------------------------------


def test_inspect_renderers_lists_framework_defaults_and_manifest_extra(
    runner: CliRunner, project_root: Path
) -> None:
    result = runner.invoke(app, ["inspect", "renderers", "--project", str(project_root)])
    assert result.exit_code == 0
    # Framework default
    assert "fragment" in result.stdout
    # Manifest [renderers] extra
    assert "word_cloud" in result.stdout
    assert "branch_compare" in result.stdout


def test_inspect_renderers_json_output_has_structured_shape(
    runner: CliRunner, project_root: Path
) -> None:
    result = runner.invoke(app, ["inspect", "renderers", "--project", str(project_root), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ext_point"] == "renderers"
    names = {e["name"] for e in payload["entries"]}
    assert "fragment" in names
    assert "word_cloud" in names
    assert "branch_compare" in names
    # Framework default flagged correctly
    fragment = next(e for e in payload["entries"] if e["name"] == "fragment")
    assert fragment["source"] == "framework"
    # Manifest-declared flagged correctly
    word_cloud = next(e for e in payload["entries"] if e["name"] == "word_cloud")
    assert word_cloud["source"] == "manifest"


def test_inspect_renderers_manifest_only_includes_note(
    runner: CliRunner, project_root: Path
) -> None:
    """Without --runtime, the output must include the note explaining
    how to opt into the cross-check — agents reading the manifest-only
    output should know they can get more."""
    result = runner.invoke(app, ["inspect", "renderers", "--project", str(project_root)])
    assert "Manifest-only view" in result.stdout
    assert "--runtime" in result.stdout


def test_inspect_renderers_exits_2_when_no_dazzle_toml(runner: CliRunner, tmp_path: Path) -> None:
    """Outside a Dazzle project, the command must fail clearly with
    exit-code 2 (CLI convention for usage errors) — not crash."""
    result = runner.invoke(app, ["inspect", "renderers", "--project", str(tmp_path)])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# inspect routes
# ---------------------------------------------------------------------------


def test_inspect_routes_lists_extensions_routers(runner: CliRunner, project_root: Path) -> None:
    result = runner.invoke(app, ["inspect", "routes", "--project", str(project_root)])
    assert result.exit_code == 0
    assert "app.api.graph:router" in result.stdout


def test_inspect_routes_empty_when_no_extensions_declared(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Minimal manifest without [extensions] yields zero entries +
    the helpful note. Must not crash."""
    (tmp_path / "dazzle.toml").write_text(
        textwrap.dedent("""\
            [project]
            name = "empty"
            version = "0.1.0"

            [modules]
            paths = ["./dsl"]
        """)
    )
    result = runner.invoke(app, ["inspect", "routes", "--project", str(tmp_path)])
    assert result.exit_code == 0
    assert "(none)" in result.stdout


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


def test_inspect_routes_runtime_without_db_hints_at_database_url(
    runner: CliRunner, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--runtime can't boot without a database — the failure note must
    tell the agent to set DATABASE_URL rather than fail silently."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = runner.invoke(app, ["inspect", "routes", "--project", str(project_root), "--runtime"])
    assert result.exit_code == 0
    assert "DATABASE_URL" in result.stdout


# ---------------------------------------------------------------------------
# inspect oauth-providers
# ---------------------------------------------------------------------------


def test_inspect_oauth_providers_lists_all_declared(runner: CliRunner, project_root: Path) -> None:
    result = runner.invoke(app, ["inspect", "oauth-providers", "--project", str(project_root)])
    assert result.exit_code == 0
    assert "google" in result.stdout
    assert "github" in result.stdout
    # Detail line includes the env vars + scopes
    assert "GOOGLE_CLIENT_ID" in result.stdout
    assert "user:email" in result.stdout


def test_inspect_oauth_providers_json_shape(runner: CliRunner, project_root: Path) -> None:
    result = runner.invoke(
        app, ["inspect", "oauth-providers", "--project", str(project_root), "--json"]
    )
    payload = json.loads(result.stdout)
    assert payload["ext_point"] == "oauth-providers"
    providers = {e["name"] for e in payload["entries"]}
    assert providers == {"google", "github"}


# ---------------------------------------------------------------------------
# inspect primitives
# ---------------------------------------------------------------------------


def test_inspect_primitives_manifest_only_includes_note(
    runner: CliRunner, project_root: Path
) -> None:
    """Primitives don't have a manifest table — without --runtime
    the command returns zero entries and a note explaining why."""
    result = runner.invoke(app, ["inspect", "primitives", "--project", str(project_root)])
    assert result.exit_code == 0
    assert "(none)" in result.stdout
    assert "--runtime" in result.stdout
    assert "@primitive decorator" in result.stdout


# ---------------------------------------------------------------------------
# inspect api (renamed from `dazzle inspect-api`)
# ---------------------------------------------------------------------------


def test_inspect_api_help_lists_existing_subcommands(runner: CliRunner) -> None:
    """`inspect api --help` must list the same five subcommands the
    old `dazzle inspect-api` exposed. The rename is a clean break —
    the subcommands themselves are unchanged."""
    result = runner.invoke(app, ["inspect", "api", "--help"])
    assert result.exit_code == 0
    for subcommand in (
        "dsl-constructs",
        "ir-types",
        "mcp-tools",
        "public-helpers",
        "runtime-urls",
    ):
        assert subcommand in result.stdout


def test_inspect_api_dsl_constructs_emits_snapshot(runner: CliRunner) -> None:
    """The api subcommands are pure introspection — emit the snapshot
    to stdout. We don't pin the contents (it's project-state-driven)
    but we confirm we get a non-empty response."""
    result = runner.invoke(app, ["inspect", "api", "dsl-constructs"])
    assert result.exit_code == 0
    assert len(result.stdout) > 100


def test_old_inspect_api_top_level_is_gone(runner: CliRunner) -> None:
    """Per #1120's clean-break decision, the old top-level
    `dazzle inspect-api` is removed (subcommands moved under
    `dazzle inspect api`). Pin that fact so a future restoration
    of the alias would have to be intentional."""
    result = runner.invoke(app, ["inspect-api", "--help"])
    # typer returns exit 2 for unknown command groups.
    assert result.exit_code != 0
