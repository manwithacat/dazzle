"""#1793: hashed project URLs are served through the real static mounts.

Drives ``_mount_static_files`` with a ``StaticFingerprinter`` (as
``system_routes`` wires it) against a tmp project shaped like the consumer's:
an ``@import``-only theme entry whose imports nest, a project script, and a
renderer that declares assets outside every static dir.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.subsystems.system_routes import _mount_static_files
from dazzle.page.runtime.asset_fingerprint import StaticFingerprinter
from dazzle.render.fragment import RendererAsset, RendererRegistry

IMMUTABLE = "public, max-age=31536000, immutable"


class _Picker:
    def __init__(self, assets: list[RendererAsset]) -> None:
        self._assets = assets

    def render(self, surface: object, ctx: object) -> str:
        return "<div></div>"

    def assets(self) -> list[RendererAsset]:
        return self._assets


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def served(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, StaticFingerprinter, RendererRegistry]:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    _write(tmp_path / "static" / "js" / "brand-chrome.js", "brand();")
    _write(tmp_path / "static" / "css" / "accents.css", ":root{--a:1}")
    _write(tmp_path / "static" / "css" / "brand.css", '@import url("/static/css/accents.css");')
    _write(tmp_path / "themes" / "aegismark.css", '@import url("/static/css/brand.css");\n')
    pkg = tmp_path_factory.mktemp("renderer_pkg")
    registry = RendererRegistry()
    registry.register(
        name="picker",
        handler=_Picker(
            [
                RendererAsset(path=_write(pkg / "picker.js", "pick();"), kind="js"),
                RendererAsset(path=_write(pkg / "live.json", "{}"), kind="json", cache="no-store"),
            ]
        ),
    )
    fp = StaticFingerprinter.for_project(tmp_path)
    registry.fingerprinter = fp
    app = FastAPI()
    app.state.services = SimpleNamespace(renderer_registry=registry)
    _mount_static_files(app, project_root=tmp_path, fingerprinter=fp)
    return TestClient(app), fp, registry


def test_hashed_app_script_is_served_immutable(served) -> None:
    client, fp, _ = served
    url = fp.hashed("/static/js/brand-chrome.js")
    resp = client.get(url)
    assert resp.status_code == 200 and resp.text == "brand();"
    assert resp.headers["cache-control"] == IMMUTABLE


def test_hashed_theme_entry_rewrites_imports_and_is_immutable(served) -> None:
    client, fp, _ = served
    resp = client.get(fp.hashed("/static/themes/aegismark.css"))
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == IMMUTABLE
    assert fp.hashed("/static/css/brand.css") in resp.text
    # The nested import is rewritten when brand.css itself is served.
    nested = client.get(fp.hashed("/static/css/brand.css"))
    assert fp.hashed("/static/css/accents.css") in nested.text


def test_plain_theme_entry_is_not_immutable_but_still_rewritten(served) -> None:
    client, fp, _ = served
    resp = client.get("/static/themes/aegismark.css")
    assert resp.status_code == 200
    assert "immutable" not in resp.headers["cache-control"]
    assert "max-age=" in resp.headers["cache-control"]
    assert fp.hashed("/static/css/brand.css") in resp.text


@pytest.mark.parametrize(
    ("filename", "status", "cache"),
    [
        ("hashed", 200, IMMUTABLE),
        ("live.json", 200, "no-store"),
        ("..", 404, None),
        ("undeclared.js", 404, None),
    ],
)
def test_renderer_asset_mount(served, filename: str, status: int, cache: str | None) -> None:
    client, _, registry = served
    url = (
        registry.asset_url("picker", "picker.js")
        if filename == "hashed"
        else f"/static/dazzle-renderers/picker/{filename}"
    )
    if filename == "hashed":
        assert url.startswith("/static/dazzle-renderers/picker/picker.") and url != (
            "/static/dazzle-renderers/picker/picker.js"
        )
    resp = client.get(url)
    assert resp.status_code == status
    if cache is not None:
        assert resp.headers["cache-control"] == cache
