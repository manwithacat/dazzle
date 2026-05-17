"""Tests for the [renderers] section of dazzle.toml (#1116).

Pre-#1116, projects had no way to declare custom renderer names —
`build_appspec(known_renderers=…)` was hardcoded to the framework
defaults via `default_renderer_names()` at 11 import sites. A project
DSL with `render: my_custom` failed link-time validation with no
manifest-aware override path. The `[renderers] extra = […]` table +
`known_renderer_names(manifest)` together restore project-side
extensibility.
"""

import textwrap
from pathlib import Path

from dazzle.core.manifest import ProjectManifest, load_manifest
from dazzle.core.renderer_registry import (
    _DEFAULT_RENDERERS,
    default_renderer_names,
    known_renderer_names,
)

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


# ---------------------------------------------------------------------------
# Manifest parse
# ---------------------------------------------------------------------------


def test_no_renderers_section_defaults_empty(tmp_path: Path) -> None:
    manifest = load_manifest(_write_toml(tmp_path))
    assert manifest.renderers.extra == []


def test_parses_renderers_extra_list(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [renderers]
        extra = ["branch_compare", "cytoscape_graph"]
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.renderers.extra == ["branch_compare", "cytoscape_graph"]


def test_renderers_extra_non_list_falls_back_to_empty(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [renderers]
        extra = "branch_compare"
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.renderers.extra == []


def test_renderers_extra_filters_non_strings(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [renderers]
        extra = ["ok_name", 42, true, "another_ok"]
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.renderers.extra == ["ok_name", "another_ok"]


# ---------------------------------------------------------------------------
# known_renderer_names — merging framework defaults with project extras
# ---------------------------------------------------------------------------


def test_known_renderer_names_with_no_manifest_returns_defaults() -> None:
    """Backstop for code paths that genuinely have no manifest (rare —
    tests + isolated parser invocations). Equivalent to the old
    `default_renderer_names()`."""
    assert known_renderer_names() == default_renderer_names()
    assert known_renderer_names() == set(_DEFAULT_RENDERERS)


def test_known_renderer_names_with_manifest_merges_extras() -> None:
    """The DSL's link-time validator should accept the union of
    framework defaults and project-declared extras."""
    manifest = ProjectManifest(
        name="x",
        version="0.1.0",
        project_root="x.core",
        module_paths=["./dsl"],
    )
    manifest.renderers.extra = ["branch_compare", "cytoscape_graph"]

    names = known_renderer_names(manifest)
    assert "fragment" in names, "framework defaults must always be included"
    assert "branch_compare" in names
    assert "cytoscape_graph" in names


def test_known_renderer_names_does_not_mutate_default_set() -> None:
    """Defensive — `default_renderer_names()` returns a fresh set each
    call. A bug where the merged set leaked back into the default
    cache would silently expand the allowlist across all manifests."""
    manifest = ProjectManifest(
        name="x",
        version="0.1.0",
        project_root="x.core",
        module_paths=["./dsl"],
    )
    manifest.renderers.extra = ["leaked_name"]
    _ = known_renderer_names(manifest)
    # The framework defaults must not have grown.
    assert default_renderer_names() == set(_DEFAULT_RENDERERS)
    assert "leaked_name" not in default_renderer_names()


def test_known_renderer_names_with_empty_extras_equals_defaults() -> None:
    manifest = ProjectManifest(
        name="x",
        version="0.1.0",
        project_root="x.core",
        module_paths=["./dsl"],
    )
    assert known_renderer_names(manifest) == default_renderer_names()
