"""Tests for the [ui] app_scripts key of dazzle.toml (#1515).

Downstream apps had no hook to thread their own client JS into the app-shell
<head>; custom islands silently stopped loading on v0.92. `[ui] app_scripts =
[...]` lists served script URLs that `resolve_app_chrome` appends after the
framework bundle.
"""

import textwrap
from pathlib import Path

import pytest

from dazzle.core.manifest import load_manifest

_MINIMAL_TOML = textwrap.dedent("""\
    [project]
    name = "test-app"
    version = "0.1.0"

    [modules]
    paths = ["./dsl"]
""")


def _write_toml(tmp_path: Path, extra: str = "") -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(_MINIMAL_TOML + extra, encoding="utf-8")
    return p


def test_no_app_scripts_defaults_empty(tmp_path: Path) -> None:
    manifest = load_manifest(_write_toml(tmp_path))
    assert manifest.app_scripts == []


def test_app_scripts_parsed_in_order(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [ui]
        app_scripts = ["/static/js/dz-islands.js", "/static/js/charts.js"]
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.app_scripts == ["/static/js/dz-islands.js", "/static/js/charts.js"]


def test_app_scripts_non_list_rejected(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [ui]
        app_scripts = "/static/js/one.js"
    """)
    with pytest.raises(ValueError, match="app_scripts must be a list"):
        load_manifest(_write_toml(tmp_path, extra))


def test_app_scripts_non_string_entry_rejected(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [ui]
        app_scripts = ["/static/js/ok.js", 42]
    """)
    with pytest.raises(ValueError, match="app_scripts must be a list"):
        load_manifest(_write_toml(tmp_path, extra))
