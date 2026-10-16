"""Vendored static assets must ship in the distributions (#1308, #1572).

A repo checkout serves any file from source, so CI and every quality gate are
blind to wheel/sdist exclusions. Three times an asset existed in-repo but the
packaging manifest omitted it: the PDF.js ``.mjs`` files (#1308, hx-pdf P3), the
fragment HTML (#1032) and the Geist fonts (#1572; every pip-installed deploy
404'd on both ``@font-face`` URLs).

``static/`` has no ``__init__.py``, so the assets reach the distributions through
the ``MANIFEST.in`` recursive-include plus ``include-package-data``; the fonts
also have an explicit ``dazzle.page.runtime`` package-data entry. OFL 1.1
requires the licence to accompany the fonts.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "src" / "dazzle" / "page" / "runtime" / "static"


def _manifest_in_static_patterns() -> list[str]:
    lines = [
        ln.split()
        for ln in (REPO / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        if ln.startswith("recursive-include src/dazzle/page/runtime/static")
    ]
    assert lines, "MANIFEST.in lost its page/runtime/static recursive-include"
    return [pattern for line in lines for pattern in line[2:]]


@pytest.mark.parametrize("subdir", ["vendor", "fonts"])
def test_every_vendored_file_is_in_the_sdist(subdir: str) -> None:
    patterns = _manifest_in_static_patterns()
    files = [p for p in (STATIC / subdir).rglob("*") if p.is_file()]
    assert files, f"static/{subdir} is empty"
    missing = sorted(
        str(p.relative_to(STATIC)) for p in files if not any(fnmatch(p.name, g) for g in patterns)
    )
    assert not missing, (
        "vendored assets excluded from the distributions (extend the MANIFEST.in "
        "static recursive-include):\n  " + "\n  ".join(missing)
    )


def _page_runtime_package_data() -> str:
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    entry = re.search(r'^"dazzle\.page\.runtime" = \[([^\]]*)\]', pyproject, re.M)
    assert entry, "pyproject lost the dazzle.page.runtime package-data entry (#1572)"
    return entry.group(1)


def test_fonts_and_licence_ship_in_the_wheel() -> None:
    for name in ("geist-var.woff2", "geist-mono-var.woff2", "OFL.txt"):
        assert (STATIC / "fonts" / name).is_file(), f"static/fonts/{name} missing (#1572)"
    entry = _page_runtime_package_data()
    assert "static/**/*.woff2" in entry
    assert "static/fonts/OFL.txt" in entry


@pytest.mark.parametrize(
    ("relative", "package_data_glob"),
    [
        ("assets/dazzle-favicon.svg", "static/**/*.svg"),
        ("css/themes/linear-dark.toml", "static/css/themes/*.toml"),
    ],
    ids=["default-favicon", "theme-manifest"],
)
def test_runtime_read_assets_ship_in_the_distributions(
    relative: str, package_data_glob: str
) -> None:
    """The favicon `app_chrome` defaults to and the theme manifests
    `app_theme_registry` reads next to each theme CSS (both missing from every
    wheel until 2026-10-16)."""
    path = STATIC / relative
    assert path.is_file(), f"static/{relative} missing"
    assert any(fnmatch(path.name, g) for g in _manifest_in_static_patterns()), (
        f"MANIFEST.in static recursive-include does not match static/{relative}"
    )
    assert package_data_glob in _page_runtime_package_data()


def test_served_css_references_the_shipped_fonts() -> None:
    """The pin cannot outlive the @font-face rules silently."""
    css = (STATIC / "dist" / "dazzle.min.css").read_text(encoding="utf-8")
    refs = set(re.findall(r"/static/fonts/([\w.-]+\.woff2)", css))
    assert refs == {"geist-var.woff2", "geist-mono-var.woff2"}
    assert all((STATIC / "fonts" / ref).is_file() for ref in refs)
