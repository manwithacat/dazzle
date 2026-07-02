"""qa capture: viewport/theme options and filename/manifest contract."""

import json
from pathlib import Path

from dazzle.qa.capture import VIEWPORTS, write_manifest
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
