"""Structural gates for the multi-harness agent-instruction layout.

AGENTS.md is canonical (see docs/superpowers/specs/
2026-07-10-multi-agent-instruction-consistency-design.md). History: the
pre-#1367 full-content AGENTS.md rotted 21 minor versions behind the
codebase because nothing watched it; the durable fix is single-source +
structural gates. These gates pin the adapters thin so duplicated facts
cannot accrete, and pin the canonical file's version stamp to pyproject.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "AGENTS.md"
ADAPTER = REPO_ROOT / ".claude" / "CLAUDE.md"
COPILOT = REPO_ROOT / ".github" / "copilot-instructions.md"

# Markers whose presence in an adapter means canonical content leaked in.
_CANONICAL_MARKERS = ("**Constructs**:", "### MCP Tools", "Working Dazzle apps in `examples/`:")


def test_claude_md_is_a_thin_adapter() -> None:
    text = ADAPTER.read_text()
    first = next(ln for ln in text.splitlines() if ln.strip())
    assert re.fullmatch(r"@(\.\./)?AGENTS\.md", first.strip()), (
        ".claude/CLAUDE.md must start with the @AGENTS.md import — canonical "
        "policy lives in AGENTS.md."
    )
    lines = len(text.splitlines())
    assert lines <= 120, (
        f".claude/CLAUDE.md is {lines} lines (cap 120). It is a Claude-runtime "
        f"adapter; project facts belong in AGENTS.md."
    )
    for marker in _CANONICAL_MARKERS:
        assert marker not in text, (
            f".claude/CLAUDE.md contains canonical-content marker {marker!r} — "
            f"that content is drift-gated in AGENTS.md and must not be duplicated."
        )


def test_copilot_instructions_is_a_stub() -> None:
    text = COPILOT.read_text()
    assert "AGENTS.md" in text, ".github/copilot-instructions.md must point at AGENTS.md."
    lines = len(text.splitlines())
    assert lines <= 25, (
        f".github/copilot-instructions.md is {lines} lines (cap 25) — it rotted "
        f"once as a full copy; it stays a stub."
    )
    assert not re.search(r"\*\*Version\*\*:", text), (
        "copilot-instructions.md must not carry a version stamp."
    )


def test_agents_md_version_matches_pyproject() -> None:
    agents_match = re.search(r"\*\*Version\*\*: (\d+\.\d+\.\d+)", AGENTS.read_text())
    assert agents_match, "AGENTS.md has lost its version footer (bump target)."
    py_match = re.search(
        r'^version = "(\d+\.\d+\.\d+)"', (REPO_ROOT / "pyproject.toml").read_text(), re.M
    )
    assert py_match
    assert agents_match.group(1) == py_match.group(1), (
        f"AGENTS.md footer says {agents_match.group(1)} but pyproject.toml is "
        f"{py_match.group(1)} — the bump workflow must update both."
    )
