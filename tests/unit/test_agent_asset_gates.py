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


def test_operator_playbooks_have_one_open_home() -> None:
    """Host command discovery must point at a portable source, never duplicate it."""
    operators = ("improve", "issues", "fuzz", "xproject")
    for name in operators:
        canonical = REPO_ROOT / ".agents" / "skills" / name / "SKILL.md"
        shim = REPO_ROOT / ".claude" / "commands" / f"{name}.md"
        assert canonical.read_text().startswith(f"---\nname: {name}\n")
        shim_text = shim.read_text()
        assert f".agents/skills/{name}/SKILL.md" in shim_text
        assert len(shim_text.splitlines()) <= 5

    improve = REPO_ROOT / ".agents" / "skills" / "improve"
    assert (improve / "capability-map.md").is_file()
    assert list((improve / "lanes").glob("*.md"))
    assert list((improve / "strategies").glob("*.md"))


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


# Every file that carries the project's canonical version. A bumped pyproject
# with a forgotten homebrew formula ships a formula pointing at a nonexistent
# tag, with zero test failure — that is the hole this closes.
#
# Deliberately EXCLUDED: packages/hatchi-maxchi/package.json, which declares
# in its own `//` field that its "version tracks the standalone releases,
# independent of Dazzle's version". Gating it would encode a falsehood. If
# that ever stops being true, remove the note and add the file here.
_CANONICAL_VERSION_FILES: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", r'^version = "(\d+\.\d+\.\d+)"'),
    ("src/dazzle/mcp/semantics_kb/core.toml", r'^version = "(\d+\.\d+\.\d+)"'),
    ("AGENTS.md", r"\*\*Version\*\*: (\d+\.\d+\.\d+)"),
    ("ROADMAP.md", r"\*\*Current Version\*\*: v(\d+\.\d+\.\d+)"),
    ("homebrew/dazzle.rb", r'^  version "(\d+\.\d+\.\d+)"'),
    ("homebrew/dazzle.rb", r"tags/v(\d+\.\d+\.\d+)\.tar\.gz"),
    ("package.json", r'"version": "(\d+\.\d+\.\d+)"'),
)

_INDEPENDENT_VERSION_FILES = ("packages/hatchi-maxchi/package.json",)


def test_every_canonical_version_location_matches_pyproject() -> None:
    """All version locations move together, or this fails.

    Previously only AGENTS.md ↔ pyproject.toml was gated. `package.json` sat ten
    minors behind (0.104.17 vs 0.114.10) because the bump skill and
    `scripts/bump-version.py` each listed a *different* set of files, so
    whichever ran last stranded the others.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    canonical = re.search(r'^version = "(\d+\.\d+\.\d+)"', pyproject, re.M)
    assert canonical, "pyproject.toml has lost its version line"
    expected = canonical.group(1)

    drift: list[str] = []
    for rel, pattern in _CANONICAL_VERSION_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"version location {rel} moved — update the gate"
        found = re.search(pattern, path.read_text(), re.M)
        if not found:
            drift.append(f"{rel}: no line matching {pattern!r}")
        elif found.group(1) != expected:
            drift.append(f"{rel}: {found.group(1)} != pyproject.toml {expected}")

    assert not drift, (
        f"Version drift against pyproject.toml ({expected}). Every location in "
        "`_CANONICAL_VERSION_FILES` must move in the same bump — see "
        "`.agents/skills/bump/SKILL.md`.\n  " + "\n  ".join(drift)
    )


def test_independent_version_files_are_documented_as_independent() -> None:
    """A file may opt out of the version gate, but only by saying so.

    Without this, an excluded file silently drifts and nobody notices — which is
    how `package.json` reached ten minors behind in the first place.
    """
    for rel in _INDEPENDENT_VERSION_FILES:
        text = (REPO_ROOT / rel).read_text()
        assert "independent of Dazzle" in text, (
            f"{rel} is excluded from the version gate but no longer declares "
            "that its version is independent. Either restore the note or add it "
            "to _CANONICAL_VERSION_FILES."
        )


def test_bump_implementations_agree_on_the_location_set() -> None:
    """The skill and the script must cover the same files.

    They drifted: the skill knew core.toml and ROADMAP.md but not package.json;
    the script knew package.json but not the other two. A bump that used one
    path stranded whatever only the other knew about — which is how package.json
    reached ten minors behind.

    The script's list is **parsed**, not substring-matched. An earlier version of
    this test grepped the file for the filename, which a commented-out entry
    satisfied — so removing a location did not fail it.
    """
    import importlib.util

    expected = {rel for rel, _ in _CANONICAL_VERSION_FILES}

    spec = importlib.util.spec_from_file_location(
        "bump_version_under_test", REPO_ROOT / "scripts/bump-version.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scripted = {rel for rel, _, _ in module.VERSION_FILES}

    missing_from_script = sorted(expected - scripted)
    extra_in_script = sorted(scripted - expected)
    assert not missing_from_script, (
        f"`scripts/bump-version.py` does not bump these version locations: {missing_from_script}"
    )
    assert not extra_in_script, (
        f"`scripts/bump-version.py` bumps locations that are not canonical: "
        f"{extra_in_script}. If one is genuinely independent, add it to "
        "_INDEPENDENT_VERSION_FILES with a rationale rather than bumping it."
    )

    # The skill is prose, so it can only be substring-checked — but assert on the
    # final verification `grep` line, which is what actually enforces coverage.
    skill = (REPO_ROOT / ".agents/skills/bump/SKILL.md").read_text()
    # The grep is a line-continuation: the pattern on one line, the file list on
    # the next. Take both, or the file list is invisible to the check.
    lines = skill.splitlines()
    verification = ""
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("grep -E"):
            continue
        chunk = [line]
        while lines[idx].rstrip().endswith("\\"):
            idx += 1
            chunk.append(lines[idx])
        verification += " " + " ".join(chunk)
    assert verification.strip(), "SKILL.md lost its verification grep"
    missing_from_skill = sorted(rel for rel in expected if rel not in verification)
    assert not missing_from_skill, (
        "`.agents/skills/bump/SKILL.md` verification grep does not cover these "
        f"version locations: {missing_from_skill}"
    )
