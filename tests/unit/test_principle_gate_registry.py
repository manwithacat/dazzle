"""Every doctrine rule in AGENTS.md has an answer to "what stops me?" (W7).

The repo's own standard, from #1749: **a claim nothing checks is a hope.**
`AGENTS.md` states 25+ bold rules across its doctrine sections; an agent that
does not know which of them are mechanically enforced will assume all of them
are review conventions and none of them can stop it — or, worse, assume a review
convention is a gate and waste a cycle discovering otherwise.

This registry answers that per rule, and keeps the answer honest:

* every bold rule in the doctrine sections of `AGENTS.md` has a row;
* every gate the registry names **exists** (a real `-m gate` test module, a real
  make target, or a named CI check) — a registry that cites a gate which was
  renamed is worse than no registry;
* `docs/harness/principle-gates.md` is **rendered from this fixture**, so the
  human view and the gate cannot drift.

Source of truth: `tests/unit/fixtures/principle_gates.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
AGENTS = REPO / "AGENTS.md"
FIXTURE = Path(__file__).parent / "fixtures" / "principle_gates.json"
DOC = REPO / "docs" / "harness" / "principle-gates.md"

# Sections of AGENTS.md that state doctrine. Bold bullets elsewhere (the
# workflow/skill lists) are names, not rules.
DOCTRINE_SECTIONS = {
    "Style Guide",
    "Architectural Decisions",
    "Ship Discipline",
    "UI Invariants",
    "Reports & Charts",
    "Test Authoring — Distillation Feedback Loop",
    "Gotchas",
}

KINDS = {"gate", "partial", "test", "ci", "review"}


def _rows() -> list[dict[str, Any]]:
    raw: list[list[Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        {"rule": r[0], "section": r[1], "kind": r[2], "gates": list(r[3]), "note": r[4]}
        for r in raw
    ]


def _bold_rules() -> list[tuple[str, str]]:
    """(section, bold lead) for every doctrine bullet in AGENTS.md."""
    out: list[tuple[str, str]] = []
    section = ""
    for line in AGENTS.read_text(encoding="utf-8").split("\n"):
        if line.startswith("## "):
            section = line[3:].strip()
        if section in DOCTRINE_SECTIONS:
            match = re.match(r"^\s*-\s+\*\*(.+?)\*\*", line)
            if match:
                out.append((section, match.group(1).strip()))
    return out


# --- the registry itself ------------------------------------------------------


def test_every_doctrine_rule_has_a_registry_row() -> None:
    """The gate on the registry. A rule added to AGENTS.md without a row means an
    agent cannot tell whether anything stops it."""
    rules = _bold_rules()
    assert len(rules) >= 20, f"only {len(rules)} doctrine rules parsed — the section list is stale"
    known = {row["rule"] for row in _rows()}
    missing = [rule for _section, rule in rules if rule not in known]
    assert not missing, (
        f"{len(missing)} doctrine rule(s) have no principle-gates row: {missing} — add one "
        "(kind `review` is a valid answer if nothing enforces it)"
    )


def test_no_registry_row_invents_a_rule() -> None:
    """A row for a rule that no longer exists is a gate citing the past."""
    rules = {rule for _section, rule in _bold_rules()}
    stale = sorted(row["rule"] for row in _rows() if row["rule"] not in rules)
    assert not stale, f"registry rows for rules AGENTS.md no longer states: {stale}"


def test_every_row_has_a_kind_and_a_reason() -> None:
    for row in _rows():
        assert row["kind"] in KINDS, f"{row['rule']}: unknown kind {row['kind']!r}"
        assert row["note"].strip(), f"{row['rule']}: a row must say why"
        if row["kind"] == "review":
            assert not row["gates"], (
                f"{row['rule']}: kind `review` means nothing enforces it, so it must not cite a gate"
            )
        else:
            assert row["gates"], f"{row['rule']}: kind {row['kind']!r} must name what enforces it"


def test_every_named_gate_exists() -> None:
    """A registry that cites a renamed gate is worse than none: an agent trusts
    it and finds nothing enforcing the rule."""
    gate_modules = {
        path.stem
        for path in (REPO / "tests" / "unit").glob("test_*.py")
        if "pytestmark = pytest.mark.gate" in path.read_text(encoding="utf-8")
    }
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    make_targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in (REPO / ".github" / "workflows").glob("*.yml")
    )

    problems: list[str] = []
    for row in _rows():
        for gate in row["gates"]:
            if gate.startswith("make "):
                target = gate.split(" ", 1)[1]
                if target not in make_targets:
                    problems.append(f"{row['rule']}: no make target {target!r}")
            elif gate.endswith(".py"):
                if not (REPO / gate).is_file():
                    problems.append(f"{row['rule']}: no such file {gate}")
                elif row["kind"] != "test" and Path(gate).stem not in gate_modules:
                    problems.append(f"{row['rule']}: {gate} is not a -m gate module")
            elif gate not in workflows:
                problems.append(f"{row['rule']}: no CI check named {gate!r}")
    assert not problems, "\n".join(problems)


# --- the human view is generated from the fixture -----------------------------


def _render(rows: list[dict[str, Any]]) -> str:
    gates = sum(1 for r in rows if r["kind"] in {"gate", "test", "ci"})
    lines = [
        "# Principle → gate registry",
        "",
        "**Rendered from `tests/unit/fixtures/principle_gates.json`** by",
        "`tests/unit/test_principle_gate_registry.py` — edit the fixture, not this page.",
        "",
        "The repo's standard, from #1749: *a claim nothing checks is a hope.* This page",
        "answers one question per doctrine rule in `AGENTS.md`, for an agent that has",
        "never seen this repo: **what stops me from breaking this?**",
        "",
        f"{gates} of {len(rows)} rules are mechanically enforced. The rest are review",
        "conventions — real, but nothing turns them red, and knowing which is which is",
        "the difference between a rule you can lean on and one you have to remember.",
        "",
        "| Rule | Enforced by | Kind |",
        "|---|---|---|",
    ]
    for row in rows:
        gates_cell = "<br>".join(f"`{g}`" for g in row["gates"]) or "—"
        lines.append(f"| **{row['rule']}** | {gates_cell} | `{row['kind']}` |")
    lines += ["", "## Notes", "", "| Rule | Why |", "|---|---|"]
    for row in rows:
        lines.append(f"| **{row['rule']}** | {row['note']} |")
    lines += [
        "",
        "## Reading the kinds",
        "",
        "| Kind | Meaning |",
        "|---|---|",
        "| `gate` | A `-m gate` test module or make target. Break it and `make ci-fast` is red. |",
        "| `test` | Enforced by behaviour (e.g. a parser error) and asserted by a test that is not itself gated. |",
        "| `ci` | A CI check rather than a pytest gate. |",
        "| `partial` | A gate defends part of the rule; the rest is review. |",
        "| `review` | Nothing enforces it. Review convention. |",
        "",
        "Part of the agent-cognition programme (W7, #1759): an alternate agent should",
        "be able to read this page and know which rules will stop it.",
        "",
    ]
    return "\n".join(lines)


def test_the_document_is_in_sync_with_the_fixture() -> None:
    assert DOC.read_text(encoding="utf-8") == _render(_rows()), (
        f"{DOC.relative_to(REPO)} is stale — it is rendered from "
        f"{FIXTURE.relative_to(REPO)}; regenerate or edit the fixture"
    )
