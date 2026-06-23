"""Regression gate for GitHub issue #1308 part 2.

The `dazzle db` CLI loads Alembic assets BY FILE PATH (`script_location` /
`version_locations` in `_get_alembic_cfg`) — they are not importable modules:

  - `script.py.mako`  — the autogenerate template (`revision --autogenerate`
    fails without it)
  - `alembic.ini`     — base Alembic config
  - `versions/000*.py` — the framework BASELINE migrations

`src/dazzle/http/alembic/versions/` has no `__init__.py`, so
`[tool.setuptools.packages.find]` with `namespaces = false` never discovers it
as a package — without an explicit `package-data` entry the `.mako`, `.ini`, and
EVERY framework migration were dropped from the built wheel. Every `pip install
dazzle-dsl` was therefore missing the migrations entirely (invisible locally
because the repo install is editable).

These tests pin the config invariants. The actual wheel inclusion was verified
manually by building a wheel and confirming `script.py.mako`, `alembic.ini`, and
`versions/0019_process_runtime_tables.py` are present under `dazzle/http/alembic/`.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_DIR = _REPO_ROOT / "src/dazzle/http/alembic"


def test_pyproject_declares_alembic_package_data() -> None:
    """`pyproject.toml` must ship the alembic assets via package-data — the
    `versions/*.py` glob is load-bearing because `versions/` is not a package."""
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text()
    assert '"dazzle.http.alembic"' in pyproject, (
        "pyproject.toml [tool.setuptools.package-data] missing the "
        "'dazzle.http.alembic' entry — script.py.mako, alembic.ini, and the "
        "framework baseline migrations get dropped from the wheel (issue #1308)."
    )
    # The versions/*.py glob is the part that ships the (non-package) migrations.
    assert "versions/*.py" in pyproject, (
        "pyproject.toml package-data must include 'versions/*.py' so the "
        "framework baseline migrations (versions/ has no __init__.py) ship in "
        "the wheel (issue #1308)."
    )


def test_manifest_includes_alembic_assets() -> None:
    """MANIFEST.in must recursive-include the alembic dir so the sdist carries
    the same assets as the wheel."""
    manifest = (_REPO_ROOT / "MANIFEST.in").read_text()
    assert "src/dazzle/http/alembic" in manifest, (
        "MANIFEST.in missing a recursive-include for src/dazzle/http/alembic — "
        "the sdist would omit the migration assets (issue #1308)."
    )


def test_alembic_assets_exist_at_framework_dir() -> None:
    """The runtime load path (`_get_framework_alembic_dir`) must find the
    assets — pins their presence so a move/rename can't silently break the
    `dazzle db` CLI."""
    from dazzle.cli.db import _get_framework_alembic_dir

    framework_dir = _get_framework_alembic_dir()
    assert framework_dir == _ALEMBIC_DIR, (
        f"_get_framework_alembic_dir resolved {framework_dir}, expected {_ALEMBIC_DIR}"
    )
    assert (framework_dir / "script.py.mako").exists(), "script.py.mako missing"
    assert (framework_dir / "alembic.ini").exists(), "alembic.ini missing"
    assert (framework_dir / "versions" / "0019_process_runtime_tables.py").exists(), (
        "framework baseline migration 0019 missing"
    )


def test_versions_dir_has_no_init_py() -> None:
    """Documents WHY the package-data glob is required: versions/ is
    intentionally not a Python package (Alembic loads scripts by path), so it's
    excluded from `packages.find` and needs the explicit data-file glob to ship.
    If someone adds an __init__.py here, revisit the packaging strategy."""
    assert not (_ALEMBIC_DIR / "versions" / "__init__.py").exists(), (
        "versions/__init__.py appeared — if versions/ is now a package, the "
        "package-data 'versions/*.py' glob may be redundant; re-verify wheel "
        "inclusion either way (issue #1308)."
    )
