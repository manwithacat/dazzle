"""qa capture: viewport/theme options and filename/manifest contract."""

import json
from pathlib import Path
from types import SimpleNamespace

from dazzle.cli.qa import _plan_qa_capture
from dazzle.qa.capture import VIEWPORTS, CaptureTarget, write_manifest
from dazzle.qa.models import CapturedScreen


def test_viewports_table() -> None:
    assert VIEWPORTS["desktop"] == {"width": 1440, "height": 900}
    assert VIEWPORTS["mobile"] == {"width": 390, "height": 844}


def test_captured_screen_carries_theme_default_light() -> None:
    s = CapturedScreen(
        persona="admin",
        workspace="main",
        url="http://x/app/workspaces/main",
        screenshot=Path("/tmp/x.png"),
    )
    assert s.theme == "light"


def test_write_manifest_includes_theme(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    screens = [
        CapturedScreen(
            persona="admin",
            workspace="main",
            url="u",
            screenshot=tmp_path / "main_admin_desktop_dark.png",
            theme="dark",
        )
    ]
    write_manifest(screens, app_name="ops_dashboard", manifest_path=manifest)
    data = json.loads(manifest.read_text())
    (app,) = data["apps"]
    assert app["screens"][0]["theme"] == "dark"


def test_capture_plan_can_select_one_persona_workspace(monkeypatch, tmp_path: Path) -> None:
    app = SimpleNamespace(name="studio")
    monkeypatch.setattr("dazzle.cli.utils.load_project_appspec", lambda _path: app)
    monkeypatch.setattr(
        "dazzle.cli.qa.build_capture_plan",
        lambda _app, include_denied: [
            CaptureTarget("designer", "studio_dashboard", "/app/workspaces/studio_dashboard"),
            CaptureTarget("designer", "asset_catalog", "/app/workspaces/asset_catalog"),
            CaptureTarget("reviewer", "studio_dashboard", "/app/workspaces/studio_dashboard"),
        ],
    )

    loaded, targets = _plan_qa_capture(tmp_path, "designer", workspace="asset_catalog")

    assert loaded is app
    assert [(t.persona, t.workspace) for t in targets] == [("designer", "asset_catalog")]
