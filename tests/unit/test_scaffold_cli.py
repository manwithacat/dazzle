"""Tests for dazzle scaffold CLI helpers (#1605)."""

from __future__ import annotations

from pathlib import Path

from dazzle.cli.scaffold import _display_path


def test_display_path_relative_under_root() -> None:
    root = Path("/proj/app")
    path = root / "services" / "foo.py"
    assert _display_path(path, root) == "services/foo.py"


def test_display_path_absolute_outside_root() -> None:
    root = Path("/proj/app")
    path = Path("/tmp/outside/foo.py")
    # Must not raise; absolute path string when outside project root.
    out = _display_path(path, root)
    assert out.endswith("foo.py")
    assert "tmp" in out or out.startswith("/")
