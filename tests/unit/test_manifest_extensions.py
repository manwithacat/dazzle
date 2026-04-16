"""Tests for the [extensions] section of dazzle.toml (#786)."""

import textwrap
from pathlib import Path

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


def test_no_extensions_section_defaults_empty(tmp_path: Path) -> None:
    manifest = load_manifest(_write_toml(tmp_path))
    assert manifest.extensions.routers == []


def test_parses_routers_list(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\

        [extensions]
        routers = [
            "app.routes.graph:router",
            "app.routes.search:router",
        ]
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.extensions.routers == [
        "app.routes.graph:router",
        "app.routes.search:router",
    ]


def test_empty_routers_list(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\

        [extensions]
        routers = []
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.extensions.routers == []


def test_non_string_entries_filtered(tmp_path: Path) -> None:
    # If the TOML contains a non-string, we silently drop it rather than
    # blowing up at load time — a bad config shouldn't break app startup.
    extra = textwrap.dedent("""\

        [extensions]
        routers = ["app.routes.graph:router", 42, "app.routes.search:router"]
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.extensions.routers == [
        "app.routes.graph:router",
        "app.routes.search:router",
    ]
