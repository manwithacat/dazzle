"""``dazzle serve --watch`` re-validates the DSL on change (flense ship AB).

The watcher replaced the hot-reload manager: no browser refresh, no spec
swap — a change re-parses, links and lints the project and prints the result.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.dsl_watch import DslWatcher, validate_project

_VALID = 'module shop\napp shop "Shop"\n\nentity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'


def _project(tmp_path: Path, dsl: str = _VALID) -> Path:
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "shop"\nversion = "0.1.0"\nroot = "shop"\n\n[modules]\npaths = ["./dsl"]\n'
    )
    (tmp_path / "dsl").mkdir()
    (tmp_path / "dsl" / "app.dsl").write_text(dsl)
    return tmp_path


def _touch(path: Path, text: str) -> None:
    path.write_text(text)
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))


def test_validate_project_reports_valid_and_broken(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert validate_project(root) == []
    (root / "dsl" / "app.dsl").write_text(_VALID + "\nentity Broken\n")
    assert validate_project(root) != []


def test_change_triggers_one_revalidation_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    seen: list[Path] = []

    def validate(project_root: Path) -> list[str]:
        seen.append(project_root)
        return ["app.dsl:3: boom"]

    watcher = DslWatcher(root, validate=validate)
    assert watcher.start() is True
    watcher.stop()  # poll by hand from here
    assert watcher.check() is None  # nothing changed since the start scan

    _touch(root / "dsl" / "app.dsl", _VALID + "\n")
    assert watcher.check() == ["app.dsl:3: boom"]
    assert seen == [root]
    assert watcher.check() is None  # the same change is not re-reported
    out = capsys.readouterr().out
    assert "1 validation error(s)" in out
    assert "app.dsl:3: boom" in out


def test_valid_change_says_restart_to_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    watcher = DslWatcher(root, validate=lambda _root: [])
    watcher.start()
    watcher.stop()
    (root / "dsl" / "extra.dsl").write_text("module shop\n")
    assert watcher.check() == []
    assert "Restart `dazzle serve` to apply" in capsys.readouterr().out


def test_nothing_to_watch(tmp_path: Path) -> None:
    assert DslWatcher(tmp_path).start() is False
