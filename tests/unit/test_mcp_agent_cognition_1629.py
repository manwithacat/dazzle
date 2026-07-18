"""#1629 — MCP agentic cognition: project binding, db URL, demo_world, policy parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_policy_consolidated_map_includes_access_matrix() -> None:
    from dazzle.mcp.server.handlers_consolidated import handle_policy
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    tools = {t.name: t for t in get_consolidated_tools()}
    ops = tools["policy"].inputSchema["properties"]["operation"]["enum"]
    assert "access_matrix" in ops
    assert "verify_status" in ops
    # Dispatch must not return unknown op for access_matrix
    raw = handle_policy(
        {
            "operation": "access_matrix",
            "project_path": str(SIMPLE),
            "_resolved_project_path": SIMPLE,
        }
    )
    data = json.loads(raw)
    assert "error" not in data
    assert "entities" in data and "cells" in data


def test_project_local_db_url_prefers_runtime_json(tmp_path: Path) -> None:
    from dazzle.db.connection import resolve_db_url

    daz = tmp_path / ".dazzle"
    daz.mkdir()
    (daz / "runtime.json").write_text(
        json.dumps(
            {
                "ui_port": 3000,
                "database_url": "postgresql://user:secret@localhost:5432/app_live_db",
            }
        ),
        encoding="utf-8",
    )
    url = resolve_db_url(project_root=tmp_path)
    assert "app_live_db" in url
    assert "secret" in url  # raw for connection; masked only in MCP payloads


def test_project_local_db_url_prefers_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dazzle.db.connection import resolve_db_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://u:p@localhost:5432/from_dotenv\n",
        encoding="utf-8",
    )
    # Ambient wrong DB must not win over project .env
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/ambient_wrong")
    url = resolve_db_url(project_root=tmp_path)
    assert "from_dotenv" in url


def test_demo_world_handler_shape() -> None:
    from dazzle.mcp.server.handlers.status import get_demo_world_handler

    if not (SIMPLE / "dazzle.toml").is_file():
        pytest.skip("simple_task missing")
    raw = get_demo_world_handler(SIMPLE, {})
    data = json.loads(raw)
    assert data["project_root"].endswith("simple_task")
    assert data["has_dazzle_toml"] is True
    assert "test_mode_secret_present" in data
    assert "stable_persona_user_ids" in data
    assert "persona_homes" in data
    assert "seed_hint" in data
    assert "member" in data["stable_persona_user_ids"]


def test_status_tool_schema_includes_demo_world() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    tools = {t.name: t for t in get_consolidated_tools()}
    ops = tools["status"].inputSchema["properties"]["operation"]["enum"]
    assert "demo_world" in ops
    assert "runtime" in ops


def test_resolve_project_path_dev_mode_refuses_monorepo_root() -> None:
    from dazzle.mcp.server import state as st

    st.reset_state()
    st.set_project_root(REPO)
    st.init_dev_mode(REPO)
    assert st.is_dev_mode()
    with pytest.raises(ValueError, match="No active Dazzle project"):
        st.resolve_project_path(None)
    # explicit path still works
    path = st.resolve_project_path(str(SIMPLE))
    assert path == SIMPLE.resolve()
    st.reset_state()


def test_mcp_status_changelog_compact_by_default() -> None:
    from dazzle.mcp.server.handlers.status import get_mcp_status_handler

    raw = get_mcp_status_handler({})
    data = json.loads(raw)
    nslc = data.get("new_since_last_check")
    if nslc is None:
        pytest.skip("changelog not available")
    # compact form is dict with count, not multi-MB list
    if isinstance(nslc, dict):
        assert "count" in nslc
        assert "hint" in nslc
    else:
        # if already seen version, may be empty list — ok
        assert isinstance(nslc, list)
