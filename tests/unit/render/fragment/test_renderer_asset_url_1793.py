"""#1793: ``RendererRegistry.asset_url`` hashes the path, never a ``?v=`` query.

Replaces the #1137 ``?v=<hash>`` contract. With the app's
``StaticFingerprinter`` wired on the registry, a declared asset's URL carries
its content hash in the filename (served ``immutable`` by the
``/static/dazzle-renderers`` mount); ``no-store``, dev/test, unregistered and
missing assets get the plain URL.
"""

from __future__ import annotations

import pathlib

import pytest

from dazzle.page.runtime.asset_fingerprint import FINGERPRINT_RE, StaticFingerprinter
from dazzle.render.fragment import RendererAsset, RendererRegistry

PLAIN = "/static/dazzle-renderers/picker/picker.js"


class _Picker:
    def __init__(self, assets: list[RendererAsset]) -> None:
        self._assets = assets

    def render(self, surface: object, ctx: object) -> str:
        return "<x/>"

    def assets(self) -> list[RendererAsset]:
        return self._assets


def _registry(
    tmp_path: pathlib.Path, *, env: str = "production", cache: str = "fingerprint"
) -> RendererRegistry:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    js = pkg / "picker.js"
    js.write_text("pick();")
    reg = RendererRegistry()
    reg.register(
        name="picker",
        handler=_Picker([RendererAsset(path=js, kind="js", cache=cache)]),  # type: ignore[arg-type]
    )
    reg.fingerprinter = StaticFingerprinter([tmp_path / "static"], env=env)
    return reg


def test_declared_asset_url_carries_hash_in_path(tmp_path: pathlib.Path) -> None:
    url = _registry(tmp_path).asset_url("picker", "picker.js")
    assert "?" not in url
    head, name = url.rsplit("/", 1)
    assert head == "/static/dazzle-renderers/picker"
    assert FINGERPRINT_RE.match(name) and name.startswith("picker.") and name.endswith(".js")


def test_asset_under_static_dir_uses_its_static_url(tmp_path: pathlib.Path) -> None:
    (tmp_path / "static" / "js").mkdir(parents=True)
    js = tmp_path / "static" / "js" / "fastmark.js"
    js.write_text("x();")
    reg = RendererRegistry()
    reg.register(name="fm", handler=_Picker([RendererAsset(path=js, kind="js")]))
    reg.fingerprinter = StaticFingerprinter([tmp_path / "static"], env="production")
    url = reg.asset_url("fm", "fastmark.js")
    assert url.startswith("/static/js/fastmark.") and FINGERPRINT_RE.match(url.rsplit("/", 1)[1])


@pytest.mark.parametrize(
    ("build", "renderer", "filename", "expected"),
    [
        (lambda p: _registry(p, cache="no-store"), "picker", "picker.js", PLAIN),
        (lambda p: _registry(p, env=""), "picker", "picker.js", PLAIN),
        (_registry, "nope", "picker.js", "/static/dazzle-renderers/nope/picker.js"),
        (lambda p: RendererRegistry(), "picker", "picker.js", PLAIN),  # no fingerprinter
    ],
)
def test_plain_url_cases(tmp_path: pathlib.Path, build, renderer, filename, expected) -> None:
    assert build(tmp_path).asset_url(renderer, filename) == expected


def test_missing_file_falls_back_to_plain(tmp_path: pathlib.Path) -> None:
    reg = _registry(tmp_path)
    (tmp_path / "pkg" / "picker.js").unlink()
    assert reg.asset_url("picker", "picker.js") == PLAIN
