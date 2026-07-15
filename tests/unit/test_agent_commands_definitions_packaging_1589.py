"""#1589 — agent_commands definitions/*.toml must ship in the wheel.

Same packaging class as #1032 / #1308 / #1572: asset lives under a
non-package directory, so setuptools `find` drops it unless
`[tool.setuptools.package-data]` lists it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
DEFINITIONS = ROOT / "src" / "dazzle" / "services" / "agent_commands" / "definitions"
EXPECTED = (
    "improve.toml",
    "issues.toml",
    "ship.toml",
    "qa.toml",
    "explore.toml",
    "polish.toml",
    "spec_sync.toml",
    "ux_maturity.toml",
)


def test_definitions_tomls_exist_in_source_tree() -> None:
    assert DEFINITIONS.is_dir(), f"missing {DEFINITIONS}"
    names = {p.name for p in DEFINITIONS.glob("*.toml")}
    missing = set(EXPECTED) - names
    assert not missing, f"source tree missing definition files: {missing}"


def test_pyproject_declares_agent_commands_package_data() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "dazzle.services.agent_commands" in text, (
        "pyproject.toml [tool.setuptools.package-data] missing entry for "
        "dazzle.services.agent_commands (definitions/*.toml) — #1589"
    )
    assert "definitions/*.toml" in text, (
        "package-data must include 'definitions/*.toml' so agent sync/seed "
        "loads commands from a pip-installed wheel — #1589"
    )


def test_loader_finds_definitions() -> None:
    from dazzle.services.agent_commands.loader import DEFINITIONS_DIR, load_all_commands

    assert DEFINITIONS_DIR.is_dir(), DEFINITIONS_DIR
    cmds = load_all_commands()
    assert len(cmds) >= len(EXPECTED), (
        f"expected ≥{len(EXPECTED)} commands, got {len(cmds)} from {DEFINITIONS_DIR}"
    )
    names = {c.name for c in cmds}
    assert "improve" in names, f"improve command missing from {names}"
