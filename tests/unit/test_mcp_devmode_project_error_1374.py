"""#1374: dev-mode `_project_error` must give actionable per-project guidance.

When the MCP is rooted at a framework checkout (dev mode) and a project tool is
invoked with no `select_project` and no explicit `project_path`, the error must
point the user at a project-scoped MCP config rather than returning an opaque
"no project" message — otherwise a framework-rooted global server silently
mis-roots every other project.
"""

import json
from pathlib import Path
from unittest.mock import patch


def test_dev_mode_error_recommends_project_scoped_config() -> None:
    from dazzle.mcp.server.handlers_consolidated import _project_error

    with (
        patch("dazzle.mcp.server.handlers_consolidated.is_dev_mode", return_value=True),
        patch(
            "dazzle.mcp.server.handlers_consolidated.get_available_projects",
            return_value={"simple_task": "/x/simple_task"},
        ),
    ):
        payload = json.loads(_project_error())

    assert payload["mode"] == "dev"
    assert payload["available_projects"] == ["simple_task"]
    err = payload["error"]
    # The actionable guidance: project-scoped config + the three escape hatches.
    assert "--working-dir" in err
    assert "select_project" in err
    assert "project_path" in err


def test_normal_mode_error_is_unchanged() -> None:
    from dazzle.mcp.server.handlers_consolidated import _project_error

    with (
        patch("dazzle.mcp.server.handlers_consolidated.is_dev_mode", return_value=False),
        patch(
            "dazzle.mcp.server.handlers_consolidated.get_project_root",
            return_value=Path("/p"),
        ),
    ):
        payload = json.loads(_project_error())

    # Normal mode keeps its concise message — no dev-mode "mode" key.
    assert "mode" not in payload
    assert payload["project_root"] == "/p"
