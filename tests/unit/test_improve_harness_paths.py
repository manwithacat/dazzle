"""The harness may only name things that exist.

`.agents/skills/improve/` is the most-read-by-agents surface in the repository:
SKILL.md, six lane playbooks and twenty-nine strategies are what an autonomous
cycle follows. Every one of them points at a script, a fixture or a doctrine doc
by path, and a path that has moved is a cycle that fails — or worse, a probe that
reports nothing and reads as "no residual".

Two of these had already rotted: `docs/reference/antagonist-report-post-5.8.md`
(the file is `post-5-8`) and `docs/agent/invent-safely.md` (the invention ladder
lives in the HaTchi-MaXchi package). Nothing caught them, because nothing
checked.

This is the same shape as the delegation gate in `test_pip_audit.py` (a caller
naming a target that does not exist) and as #1750 (a name that resolves to
nothing): the failure is silent, and it is invisible to review because the
document reads correctly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
IMPROVE = REPO / ".agents" / "skills" / "improve"

# Paths a playbook names. Deliberately narrow — two positions, not every mention:
#
# 1. A path handed to an interpreter or shell is runnable: if it moved, the cycle
#    runs nothing or dies.
# 2. A doctrine or handoff doc, cited in backticks. Agents read those to decide
#    what to do; a renamed file means the instruction points nowhere.
_TOP = r"(?:scripts|dev_docs|docs|packages|examples|fixtures|src|tests|\.dazzle)"
_EXT = r"(?:py|md|toml|json|sh|yml|yaml|txt)"
_RUNNABLE = re.compile(rf"(?:python|bash|sh)\s+(?:-[\w-]+\s+)*(?P<path>{_TOP}/[\w./-]+\.{_EXT})")
_CITED_DOC = re.compile(rf"`(?P<path>{_TOP}/[\w./-]+\.{_EXT})`")


def _playbooks() -> list[Path]:
    return [
        IMPROVE / "SKILL.md",
        *sorted((IMPROVE / "lanes").glob("*.md")),
        *sorted((IMPROVE / "strategies").glob("*.md")),
    ]


def _references() -> dict[Path, set[str]]:
    """Runnable paths and cited doctrine docs, per playbook.

    Deliberately *not* every path mentioned: a playbook also names files it is
    supposed to **produce** (`fixtures/scene_walks/`, `fixtures/job_claims.yaml`)
    and placeholders for whatever app the cycle is on (`examples/APP/…`). Treating
    those as references would make the gate cry wolf on its first honest run,
    and a gate that cries wolf gets ignored.
    """
    references: dict[Path, set[str]] = {}
    for playbook in _playbooks():
        if not playbook.is_file():
            continue
        text = playbook.read_text(encoding="utf-8")
        found = {m.group("path") for m in _RUNNABLE.finditer(text)}
        found |= {
            m.group("path")
            for m in _CITED_DOC.finditer(text)
            if m.group("path").startswith("docs/")
        }
        if found:
            references[playbook] = found
    return references


def test_harness_playbooks_are_present() -> None:
    """A gate over a directory that does not exist passes by finding nothing."""
    assert IMPROVE.is_dir(), f"missing {IMPROVE}"
    playbooks = _playbooks()
    assert len(playbooks) >= 30, f"only found {len(playbooks)} playbooks — did the tree move?"


def test_every_path_a_playbook_names_exists() -> None:
    references = _references()
    assert len(references) > 20, (
        f"only {len(references)} playbooks reference paths — the walk is broken"
    )

    missing: list[str] = []
    for playbook, paths in references.items():
        for path in sorted(paths):
            if not (REPO / path).exists():
                missing.append(f"{playbook.relative_to(REPO)} -> {path}")

    assert not missing, (
        "playbooks name paths that do not exist — a cycle that follows one runs nothing "
        "or fails:\n  " + "\n  ".join(missing)
    )


def test_the_walk_finds_the_paths_it_is_supposed_to_find() -> None:
    """Falsification guard: the regexes have to match real references, or the gate
    above is a tautology that can never fail."""
    references = {p for paths in _references().values() for p in paths}
    assert any(p.startswith("scripts/") for p in references), "no runnable script reference found"
    assert any(p.startswith("docs/") for p in references), "no cited doctrine doc found"
    # Spot-check two paths the driver names in its own preamble.
    assert "scripts/improve_example_probes.py" in references
    assert "docs/reference/hyperpart-presentation.md" in references


def test_output_paths_are_not_mistaken_for_references() -> None:
    """The four false positives this gate was written against: files a cycle is
    told to author, and a placeholder for the app it is working on."""
    references = {p for paths in _references().values() for p in paths}
    for artefact in (
        "fixtures/job_claims.yaml",
        "tests/test_behaviour.py",
        "examples/APP/agent_domain.json",
    ):
        assert artefact not in references, f"{artefact} is an output, not a reference"
