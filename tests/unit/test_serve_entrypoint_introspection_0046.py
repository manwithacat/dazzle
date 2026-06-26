"""ADR-0046 — runtime introspection boots the app's declared real entrypoint.

`inspect … --runtime` (renderers / primitives / routes) boots via
`cli/inspect.py::_boot_app`. When `dazzle.toml` declares `[serve] app =
"module:attr"`, that entrypoint is imported and introspected instead of the
framework-default `create_app`, so post-build wiring done in the app's own
server (e.g. renderer registration in `server.py`) is visible — closing the
#1401 / #1485 false-negative class. A declared entrypoint that can't import
falls back to `create_app` with an informational note (never a silent or fatal
result).
"""

import sys
from pathlib import Path

import pytest

from dazzle.cli.inspect import _boot_app, _boot_declared_entrypoint
from dazzle.core.manifest import load_manifest

_ENTRYPOINT_SRC = """\
from types import SimpleNamespace


class _Registry:
    def registered_names(self):
        return {"fragment", "author_ethics"}


# Mirrors PD's pattern: post-build wiring (renderer registration) done in the
# app's own entrypoint module, synchronously at import.
app = SimpleNamespace(
    state=SimpleNamespace(services=SimpleNamespace(renderer_registry=_Registry()))
)
"""

_DAZZLE_TOML = """\
[project]
name = "entrypoint_probe"
[modules]
paths = ["./dsl"]
[stack]
name = "dnr"
[serve]
app = "{entry}:app"
"""


@pytest.fixture
def project_with_entrypoint(tmp_path: Path):
    """A project whose dazzle.toml declares a real ASGI entrypoint that
    registers a custom renderer at import time. Unique module name per test
    so Python's import cache doesn't leak across cases."""
    module_name = "pd_entry_" + tmp_path.name.replace("-", "_")
    (tmp_path / f"{module_name}.py").write_text(_ENTRYPOINT_SRC)
    (tmp_path / "dazzle.toml").write_text(_DAZZLE_TOML.format(entry=module_name))
    try:
        yield tmp_path, module_name
    finally:
        sys.modules.pop(module_name, None)
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_serve_app_parsed_from_manifest(project_with_entrypoint):
    project_root, module_name = project_with_entrypoint
    manifest = load_manifest(project_root / "dazzle.toml")
    assert manifest.serve.app == f"{module_name}:app"


def test_serve_app_absent_is_none(tmp_path: Path):
    (tmp_path / "dazzle.toml").write_text(
        "[project]\nname = 't'\n[modules]\npaths = ['./dsl']\n[stack]\nname = 'dnr'\n"
    )
    manifest = load_manifest(tmp_path / "dazzle.toml")
    assert manifest.serve.app is None


def test_boot_declared_entrypoint_imports_the_real_app(project_with_entrypoint):
    project_root, module_name = project_with_entrypoint
    app = _boot_declared_entrypoint(f"{module_name}:app", project_root)
    assert not isinstance(app, str), app
    names = app.state.services.renderer_registry.registered_names()
    assert "author_ethics" in names  # the entrypoint-registered renderer


def test_boot_declared_entrypoint_bad_spec_returns_error(tmp_path: Path):
    # No colon → not 'module:attr'
    err = _boot_declared_entrypoint("server_app", tmp_path)
    assert isinstance(err, str) and "expected 'module:attr'" in err


def test_boot_declared_entrypoint_missing_attr_returns_error(project_with_entrypoint):
    project_root, module_name = project_with_entrypoint
    err = _boot_declared_entrypoint(f"{module_name}:nope", project_root)
    assert isinstance(err, str) and "no attribute" in err


def test_boot_declared_entrypoint_unimportable_module_returns_error(tmp_path: Path):
    err = _boot_declared_entrypoint("definitely_not_a_module_xyz:app", tmp_path)
    assert isinstance(err, str) and "import of" in err


def test_boot_declared_entrypoint_does_not_pollute_sys_path(project_with_entrypoint):
    """The import must not leave the project root on sys.path (the module stays
    cached in sys.modules)."""
    project_root, module_name = project_with_entrypoint
    assert str(project_root) not in sys.path  # precondition
    app = _boot_declared_entrypoint(f"{module_name}:app", project_root)
    assert not isinstance(app, str)
    assert str(project_root) not in sys.path  # cleaned up after import


def test_boot_and_get_registered_names_honours_passed_project_root(
    project_with_entrypoint,
):
    """Fix for the --project regression: the registry helper must read the
    [serve] app from the *passed* project_root, not re-resolve from cwd."""
    from dazzle.cli.inspect import _boot_and_get_registered_names

    project_root, _ = project_with_entrypoint
    # cwd here is the Dazzle repo, NOT project_root — so if the helper ignored
    # the passed root it would never see the entrypoint's renderer.
    names, error, note = _boot_and_get_registered_names("renderer_registry", project_root)
    assert error is None
    assert note is None
    assert "author_ethics" in names


def test_boot_app_prefers_declared_entrypoint(project_with_entrypoint):
    """The headline ADR-0046 behavior: _boot_app returns the app's real
    entrypoint (with its import-time renderer registration), not create_app,
    and emits no fallback note."""
    project_root, _ = project_with_entrypoint
    app, note = _boot_app(project_root)
    assert app is not None
    assert note is None  # booted the real entrypoint cleanly, no fallback
    assert "author_ethics" in app.state.services.renderer_registry.registered_names()
