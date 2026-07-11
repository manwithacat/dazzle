"""Template gates for morph-safe hypermedia (decisions 0005–0008).

Implementation lives in ``tools/template_lint.py`` (shared with the CLI).
These tests assert the registry, controllers, and built-in compositions stay clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "tools"))
sys.path.insert(0, str(PKG / "site"))

from template_lint import (  # noqa: E402
    builtin_compositions,
    lint_composition,
    lint_compositions,
    lint_fragment,
    lint_js_controller,
    lint_registry,
)


def _fmt(issues: list) -> str:
    return "\n  ".join(i.format() for i in issues)


def test_registry_and_controllers_are_clean() -> None:
    """Full registry + blueprint + controller lint (decisions 0005–0008)."""
    issues = lint_registry()
    assert not issues, "template_lint registry issues:\n  " + _fmt(issues)


def test_builtin_compositions_are_clean() -> None:
    """Cross-partial compositions: grid host+rows+OOB; command host+results."""
    issues = lint_compositions()
    assert not issues, "composition lint issues:\n  " + _fmt(issues)


def test_composition_catalog_has_grid_and_command() -> None:
    comps = builtin_compositions()
    assert "grid" in comps and "command" in comps
    assert len(comps["grid"]) >= 2
    assert len(comps["command"]) >= 2


def test_composition_catches_missing_cross_fragment_id() -> None:
    """Sanity: broken aria-controls across fragments is reported."""
    host = '<button aria-controls="missing-panel" aria-expanded="false">Open</button>'
    panel = '<div id="other-panel">x</div>'
    issues = lint_composition(
        [("host", host), ("panel", panel)],
        name="broken",
    )
    codes = {i.code for i in issues}
    assert "cross-aria" in codes or "aria-ref" in codes


def test_composition_allows_oob_same_id() -> None:
    host = '<div id="foot" data-dz-grid-pagination>old</div>'
    oob = '<div id="foot" data-dz-grid-pagination hx-swap-oob="true">new</div>'
    issues = lint_composition([("host", host), ("oob", oob)], name="oob-ok")
    assert not any(i.code == "cross-dup-id" for i in issues)


def test_fragment_helper_flags_alpine() -> None:
    issues = lint_fragment('<div x-data="{n:1}">x</div>', location="t")
    assert any(i.code == "alpine" for i in issues)


@pytest.mark.parametrize("path", sorted((PKG / "controllers").glob("dz-*.js")))
def test_controllers_via_shared_helper(path: Path) -> None:
    issues = lint_js_controller(path.read_text(encoding="utf-8"), location=path.name)
    assert not issues, _fmt(issues)
