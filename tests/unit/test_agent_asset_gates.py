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


def test_agents_skills_have_shims_and_index() -> None:
    """Every .agents/skills/<name> has a Claude shim (commands stub or
    skills stub) pointing at it, and a Workflows-index bullet in AGENTS.md.
    Keeps the portable home, the Claude discovery path, and the index that
    non-scanning harnesses rely on in lockstep."""
    skills = {p.name for p in (REPO_ROOT / ".agents" / "skills").iterdir() if p.is_dir()}
    assert skills, ".agents/skills is empty — the split has regressed"
    agents_text = AGENTS.read_text()
    for name in sorted(skills):
        cmd_shim = REPO_ROOT / ".claude" / "commands" / f"{name}.md"
        skill_shim = REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
        shim = cmd_shim if cmd_shim.exists() else skill_shim
        assert shim.exists(), f"no Claude shim for .agents/skills/{name}"
        body = [
            ln for ln in shim.read_text().splitlines() if ln.strip() and not ln.startswith("---")
        ]
        assert any(f".agents/skills/{name}/SKILL.md" in ln for ln in body), (
            f"shim {shim} does not point at .agents/skills/{name}/SKILL.md"
        )
        assert f"**{name}**" in agents_text, f"AGENTS.md Workflows index is missing `{name}`"


_VENDOR_RE = re.compile(r"\b(Claude|Codex|Copilot|Cursor|Grok|Anthropic|OpenAI|xAI)\b")
# Irreducible vendor mentions outside the Capability Mapping zone. Every entry
# needs a justification comment. Expected to stay empty.
_VENDOR_ALLOWLIST: tuple[str, ...] = ()


def _strip_capability_mapping(text: str) -> str:
    if "## Capability Mapping" not in text:
        return text
    head, rest = text.split("## Capability Mapping", 1)
    parts = rest.split("\n## ", 1)
    return head + ("\n## " + parts[1] if len(parts) == 2 else "")


def test_no_vendor_names_outside_capability_mapping() -> None:
    """Portable files must speak capability language (spec 2026-07-10).
    Vendor names are allowed only in AGENTS.md's Capability Mapping section."""
    offenders: list[str] = []
    scan: list[tuple[str, str]] = [("AGENTS.md", _strip_capability_mapping(AGENTS.read_text()))]
    for p in sorted((REPO_ROOT / ".agents" / "skills").rglob("*")):
        if p.is_file() and p.suffix in (".md", ".toml"):
            scan.append((str(p.relative_to(REPO_ROOT)), p.read_text()))
    for label, text in scan:
        for i, line in enumerate(text.splitlines(), 1):
            m = _VENDOR_RE.search(line)
            if m and m.group(0) not in _VENDOR_ALLOWLIST:
                offenders.append(f"{label}:{i}: {line.strip()[:100]}")
    assert not offenders, (
        "Vendor names in portable instruction files (generalise to capability "
        "language, or move to a harness adapter):\n  " + "\n  ".join(offenders)
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
