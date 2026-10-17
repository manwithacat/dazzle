"""#1793: ``StaticFingerprinter`` content-hashes every project asset the chrome links.

Pre-#1793 only the framework bundle was fingerprinted; ``[ui] app_scripts``,
project theme entries (and the sheets they ``@import``), ``custom.css`` and
renderer assets were served plain, so a fix reached a returning browser only
when its cache expired. These tests pin the resolver, the chain digest and the
``@import`` rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.page.runtime.asset_fingerprint import (
    FINGERPRINT_RE,
    StaticFingerprinter,
    static_root_dirs,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _write(tmp_path / "static" / "js" / "brand-chrome.js", "brand();")
    _write(tmp_path / "static" / "css" / "accents.css", ":root{--a:1}")
    _write(
        tmp_path / "static" / "css" / "brand.css",
        '@import url("/static/css/accents.css");\n.brand{}',
    )
    _write(
        tmp_path / "themes" / "aegismark.css",
        '@import url("/static/css/brand.css") layer(brand);\n',
    )
    return tmp_path


def _prod(project: Path, *, extra: list[Path] | None = None) -> StaticFingerprinter:
    return StaticFingerprinter(
        static_root_dirs(project, extra), project / "themes", env="production"
    )


def test_resolve_precedence_extra_then_project_then_framework(
    project: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    extra = tmp_path_factory.mktemp("extra")
    _write(extra / "js" / "brand-chrome.js", "extra();")
    fp = _prod(project, extra=[extra])
    assert fp.resolve("js/brand-chrome.js") == extra / "js" / "brand-chrome.js"
    assert _prod(project).resolve("js/brand-chrome.js") == project / "static/js/brand-chrome.js"
    # Not in the project → the framework's copy.
    assert _prod(project).resolve("dist/dazzle.min.js") is not None
    assert fp.resolve("themes/aegismark.css") == project / "themes" / "aegismark.css"
    assert fp.resolve("../etc/passwd") is None


@pytest.mark.parametrize(
    "url",
    ["/static/js/brand-chrome.js", "/static/css/brand.css", "/static/themes/aegismark.css"],
)
def test_project_urls_are_hashed_in_production(project: Path, url: str) -> None:
    out = _prod(project).hashed(url)
    assert out != url
    stem, ext = url.rsplit(".", 1)
    assert out.startswith(stem + ".") and out.endswith("." + ext)
    assert FINGERPRINT_RE.match(out.rsplit("/", 1)[-1])


@pytest.mark.parametrize(
    "url",
    [
        "/static/js/brand-chrome.js?v=8",  # hand-bumped — left alone
        "/static/js/nope.js",  # nothing serves it
        "https://cdn.example/x.js",
    ],
)
def test_unhashable_urls_pass_through(project: Path, url: str) -> None:
    assert _prod(project).hashed(url) == url


def test_dev_env_emits_plain_urls(project: Path) -> None:
    fp = StaticFingerprinter(static_root_dirs(project), project / "themes", env="")
    assert fp.hashed("/static/js/brand-chrome.js") == "/static/js/brand-chrome.js"


def test_editing_an_imported_sheet_changes_the_entry_url(project: Path) -> None:
    before = _prod(project)
    entry_a = before.hashed("/static/themes/aegismark.css")
    brand_a = before.hashed("/static/css/brand.css")
    # Nested: accents is imported by brand, which is imported by the entry.
    _write(project / "static" / "css" / "accents.css", ":root{--a:2}")
    after = _prod(project)
    assert after.hashed("/static/css/brand.css") != brand_a
    assert after.hashed("/static/themes/aegismark.css") != entry_a


def test_cyclic_import_terminates(project: Path) -> None:
    _write(project / "static" / "css" / "accents.css", '@import "/static/css/brand.css";')
    assert FINGERPRINT_RE.match(_prod(project).hashed("/static/css/brand.css").rsplit("/", 1)[-1])


def test_rewrite_css_imports_keeps_clauses_and_relative_imports(project: Path) -> None:
    fp = _prod(project)
    text = (
        '@import url("/static/css/brand.css") layer(brand);\n'
        "@import '/static/css/accents.css' screen and (min-width: 40em);\n"
        '@import url("parts/local.css");\n'
    )
    out = fp.rewrite_css_imports(text)
    brand = fp.hashed("/static/css/brand.css")
    accents = fp.hashed("/static/css/accents.css")
    assert f'@import url("{brand}") layer(brand);' in out
    assert f"@import '{accents}' screen and (min-width: 40em);" in out
    assert '@import url("parts/local.css");' in out
