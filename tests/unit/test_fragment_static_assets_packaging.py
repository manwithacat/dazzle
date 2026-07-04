"""Issue #1032 (v0.66.127): regression test for the packaging bug
that crashed cyfuture-staging at boot.

`dazzle/render/fragment/renderer.py` calls
`importlib.resources.files("dazzle.render.fragment.static") /
"<asset>.html"` at module-import time. For this to succeed in a
packaged wheel install, the static directory must:

  1. Have an `__init__.py` so it counts as a package under
     `[tool.setuptools.packages.find]` with `namespaces = false`.
  2. Be matched by a `[tool.setuptools.package-data]` entry shipping
     the `.html` files.

This test pins both invariants. If either regresses, packaged
installs crash at boot before any request lands.
"""

from __future__ import annotations

from pathlib import Path


def test_fragment_static_directory_is_a_package() -> None:
    """`__init__.py` must exist — `namespaces = false` in
    `[tool.setuptools.packages.find]` excludes namespace packages from
    the wheel."""
    repo_root = Path(__file__).resolve().parents[2]
    init_py = repo_root / "src/dazzle/render/fragment/static/__init__.py"
    assert init_py.exists(), (
        f"{init_py} missing — without it, `dazzle.render.fragment.static` "
        "is not a discoverable package and `importlib.resources.files` "
        "raises ModuleNotFoundError on packaged installs (issue #1032)."
    )


def test_pyproject_declares_fragment_static_package_data() -> None:
    """`pyproject.toml` must include a `[tool.setuptools.package-data]`
    entry for `dazzle.render.fragment.static` — without it, the
    `.html` assets get excluded from the wheel even with the
    `__init__.py`."""
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = (repo_root / "pyproject.toml").read_text()
    assert '"dazzle.render.fragment.static"' in pyproject, (
        "pyproject.toml [tool.setuptools.package-data] missing entry for "
        "dazzle.render.fragment.static (issue #1032)."
    )


def test_static_html_assets_are_loadable_via_importlib_resources() -> None:
    """Both chrome assets (workspace drawer markup + IIFE, context
    selector script template) load via the same
    `importlib.resources.files()` path the renderer uses at module
    import. If this fails, packaged-wheel installs crash on boot."""
    # Reuse the renderer's own helper rather than calling
    # `importlib.resources.files` directly — the helper runs at
    # module import in production, so exercising it here mirrors the
    # exact load path the wheel install crashed on.
    from dazzle.render.fragment.renderer import _load_static

    drawer_text = _load_static("workspace_drawer.html")
    script_text = _load_static("workspace_context_script.html")
    assert drawer_text.startswith('<dialog id="dz-detail-drawer"'), (
        "workspace_drawer.html starts with the native <dialog> — the "
        "renderer emits it verbatim. If it doesn't, the asset got "
        "truncated or replaced."
    )
    assert "{WS_NAME_JSON}" in script_text, (
        "workspace_context_script.html must carry the {WS_NAME_JSON} "
        "placeholder the renderer fills via json.dumps."
    )
    assert "{OPTIONS_URL_JSON}" in script_text, (
        "workspace_context_script.html must carry the {OPTIONS_URL_JSON} "
        "placeholder the renderer fills via json.dumps."
    )


def test_renderer_loads_static_assets_at_module_import() -> None:
    """End-to-end check: the renderer module imports successfully
    (its `_load_static` helper calls run at module-import time and
    populate `_WORKSPACE_DRAWER_HTML` + `_WORKSPACE_CONTEXT_SCRIPT_TEMPLATE`).
    If packaging regresses, `import dazzle.render.fragment.renderer`
    raises before any test even tries to render anything."""
    from dazzle.render.fragment import renderer

    assert renderer._WORKSPACE_DRAWER_HTML.startswith('<dialog id="dz-detail-drawer"')
    assert "{WS_NAME_JSON}" in renderer._WORKSPACE_CONTEXT_SCRIPT_TEMPLATE
