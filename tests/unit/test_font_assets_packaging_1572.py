"""Issue #1572: regression test for the wheel dropping the vendored Geist fonts.

The HM design-system CSS `@font-face`-declares Geist / Geist Mono pointing at
`/static/fonts/geist-var.woff2` + `geist-mono-var.woff2`. The woff2 files (and
their OFL 1.1 licence) are vendored and git-tracked under
`src/dazzle/page/runtime/static/fonts/`, but the `[tool.setuptools.package-data]`
globs originally shipped only `*.js`/`*.css`/`*.mjs` — so every pip-installed
deploy 404'd on both fonts while source/editable installs looked fine.

Third instance of the "asset exists in-repo, wheel glob omits it" class
(#1032 fragment HTML, #1308 alembic assets). This test pins:

  1. The font files + OFL.txt exist on disk.
  2. `pyproject.toml` package-data globs match `.woff2` and ship the licence
     (OFL 1.1 requires the licence to accompany font distribution).
  3. The served CSS actually references the fonts (so the pin can't outlive
     the @font-face rules silently).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = REPO_ROOT / "src/dazzle/page/runtime/static/fonts"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_font_files_and_licence_exist() -> None:
    for name in ("geist-var.woff2", "geist-mono-var.woff2", "OFL.txt"):
        assert (FONTS_DIR / name).exists(), f"{FONTS_DIR / name} missing (issue #1572)"


def test_pyproject_ships_woff2_and_licence() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    pkg_data = text.split("[tool.setuptools.package-data]", 1)[1].split("[tool.", 1)[0]
    assert "*.woff2" in pkg_data, (
        "package-data no longer ships .woff2 — pip-installed deploys will 404 on the "
        "Geist @font-face URLs (issue #1572)"
    )
    assert "OFL.txt" in pkg_data, (
        "package-data no longer ships fonts/OFL.txt — OFL 1.1 requires the licence "
        "to accompany font distribution (issue #1572)"
    )


def test_manifest_in_ships_woff2_and_licence() -> None:
    """MANIFEST.in is the mechanism that ACTUALLY gates these assets: the
    `dazzle.page.runtime.static` package-data key has never matched (static/ has
    no __init__.py — not a package), so static assets flow via MANIFEST.in +
    include-package-data. This is the pin that reproduces #1572's root cause:
    the recursive-include listed only *.js *.css *.mjs."""
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    static_lines = [
        ln for ln in manifest.splitlines() if "page/runtime/static" in ln and "include" in ln
    ]
    assert static_lines, "MANIFEST.in lost its page/runtime/static recursive-include"
    joined = " ".join(static_lines)
    assert "*.woff2" in joined, (
        "MANIFEST.in's static recursive-include no longer ships .woff2 (issue #1572 "
        "root cause — package-data alone does NOT cover these files)"
    )
    assert "OFL.txt" in joined, (
        "MANIFEST.in no longer ships the OFL licence alongside the fonts (OFL 1.1 "
        "requires it to accompany distribution)"
    )


def test_served_css_references_the_fonts() -> None:
    dist_css = REPO_ROOT / "src/dazzle/page/runtime/static/dist/dazzle.min.css"
    text = dist_css.read_text(encoding="utf-8")
    refs = re.findall(r"/static/fonts/([\w.-]+\.woff2)", text)
    assert set(refs) >= {"geist-var.woff2", "geist-mono-var.woff2"}, (
        f"dist CSS font refs changed ({sorted(set(refs))}) — update this pin and the "
        "package-data globs together"
    )
