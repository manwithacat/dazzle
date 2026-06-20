"""Regression gate for GitHub issue #1330.

Project themes live at ``<project>/themes/<name>.css`` and are served under the
``/static/themes`` URL prefix. The catch-all ``/static`` mount (CombinedStaticFiles
over ``<project>/static`` + framework_static) was registered FIRST, and Starlette
matches mounts in registration order — so ``/static`` swallowed every
``/static/themes/*.css`` request into CombinedStaticFiles, which does not look
under ``<project>/themes/`` → 404 on every project theme.

The fix (`_mount_static_files`): register the more-specific ``/static/themes``
mount BEFORE the catch-all ``/static``. These tests pin both the registration
order and the end-to-end serve (a real GET returns the project theme's bytes).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.subsystems.system_routes import _mount_static_files


def _make_project(tmp_path: Path) -> Path:
    """A project root with a themes/ dir (and a sibling static/ dir that would
    shadow it under the buggy ordering)."""
    (tmp_path / "static").mkdir()
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "midnight.css").write_text(":root { --bg: #000; }", encoding="utf-8")
    return tmp_path


def test_themes_mount_registered_before_catchall_static(tmp_path: Path) -> None:
    """#1330: /static/themes must be registered before /static so Starlette's
    in-order matcher reaches the specific mount first."""
    project_root = _make_project(tmp_path)
    app = FastAPI()
    _mount_static_files(app, project_root=project_root)

    mount_paths = [getattr(r, "path", None) for r in app.routes]
    assert "/static/themes" in mount_paths, "project_themes mount missing"
    assert "/static" in mount_paths, "catch-all static mount missing"
    assert mount_paths.index("/static/themes") < mount_paths.index("/static"), (
        "specific /static/themes mount must precede the catch-all /static"
    )


def test_project_theme_css_served_not_404(tmp_path: Path) -> None:
    """End-to-end: GET /static/themes/<name>.css returns 200 with the project
    theme's bytes — the exact path that 404'd before the reorder."""
    project_root = _make_project(tmp_path)
    app = FastAPI()
    _mount_static_files(app, project_root=project_root)

    client = TestClient(app)
    resp = client.get("/static/themes/midnight.css")
    assert resp.status_code == 200
    assert "--bg: #000" in resp.text


def test_no_themes_dir_skips_specific_mount(tmp_path: Path) -> None:
    """A project with no themes/ dir mounts only the catch-all /static (no
    spurious /static/themes mount)."""
    (tmp_path / "static").mkdir()
    app = FastAPI()
    _mount_static_files(app, project_root=tmp_path)

    mount_paths = [getattr(r, "path", None) for r in app.routes]
    assert "/static" in mount_paths
    assert "/static/themes" not in mount_paths
