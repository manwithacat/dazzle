"""Orientation benchmark — the instrument (#1759 W8).

Every gate this programme added checks that a *reference resolves*, a *command
runs*, or a *claim is recorded*. None answers the question the programme exists
for:

> can an agent that has never seen this repository do real work here, engaging
> with the gates, the counter-priors and the decision records?

That is a measurement, so the instrument is written down **before** the run —
otherwise the rubric moves to fit the result. These tests keep the instrument
honest: the task card must stay drawn from real classified residue (a card that
drifts from the tree measures nothing), each assertion must be checkable from an
artefact rather than a self-report, and every recorded run must carry a scorer.

Scoring itself is `scripts/orientation_benchmark.py --run/--report`; the results
land in `dev_docs/orientation-benchmark/` (gitignored local state).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO / "docs" / "harness" / "orientation-benchmark"
SPEC = REPO / "docs" / "harness" / "orientation-benchmark.md"
RESULTS = REPO / "dev_docs" / "orientation-benchmark" / "runs.json"
FAMILIES = REPO / "tests" / "unit" / "fixtures" / "dead_definitions_families.json"
DEAD_BASELINE = REPO / "tests" / "unit" / "fixtures" / "dead_definitions_baseline.json"

# The assertions, in the shape the scorer writes them.
ASSERTIONS = {
    "gate_before_push": "a push-gate stamp covering the diff, or the equivalent local tier",
    "no_new_residue": "the shim/singleton/ratchet gates stayed green",
    "consulted_record": "the report names the record it read, and that file exists",
    "scope_discipline": "the diff matches the card's stated bound",
    "reported_degradation": "the report states what it could not do and why",
}


def _cards() -> list[Path]:
    return sorted(BENCH.glob("TASK-*.md"))


def test_the_instrument_exists() -> None:
    assert SPEC.is_file(), f"missing {SPEC.relative_to(REPO)}"
    assert _cards(), (
        f"no task card in {BENCH.relative_to(REPO)} — an instrument with no task measures nothing"
    )


def test_every_assertion_is_scored_from_an_artefact() -> None:
    """A self-reported score cannot be the instrument: the agent's belief that it
    engaged with the harness is the thing under test."""
    spec = SPEC.read_text(encoding="utf-8")
    for name, artefact in ASSERTIONS.items():
        assert name in spec, f"{name} missing from the spec"
        assert artefact.split()[0] in spec, f"{name} must name the artefact it is read from"


def _status(card: Path) -> str:
    match = re.search(r"\*\*Status:\*\*\s*(\w+)", card.read_text(encoding="utf-8"))
    return match.group(1) if match else "open"


def test_task_cards_stay_drawn_from_real_classified_residue() -> None:
    """An **open** card must name a symbol still in the classified residue. A card
    whose symbol is already gone is a phantom and would measure nothing — which is
    exactly what happened to TASK-001 the moment a run consumed it."""
    families = json.loads(FAMILIES.read_text(encoding="utf-8"))
    baseline = set(json.loads(DEAD_BASELINE.read_text(encoding="utf-8")))
    residue = {k for k, fam in families.items() if fam and k in baseline}

    for card in _cards():
        text = card.read_text(encoding="utf-8")
        named = [s for s in residue if f"`{s}`" in text or s.split("::")[-1] in text]
        if _status(card) == "open":
            assert named, (
                f"{card.name} is open but names no symbol still in the classified "
                "residue — the card has drifted from the tree and would measure nothing"
            )
        else:
            assert not named or RESULTS.is_file(), (
                f"{card.name} is {_status(card)} with no run recorded and its symbol "
                "still live — either the status or the run is missing"
            )
        assert "## Bounds" in text, f"{card.name} has no bounds — assertion 4 needs one"
        assert "not" in text.lower(), f"{card.name} must say what the agent must NOT touch"


def test_an_open_card_exists() -> None:
    """A benchmark with no runnable task measures nothing."""
    assert [c for c in _cards() if _status(c) == "open"], "no open task card"


def test_a_card_states_what_is_not_said() -> None:
    """If the card names the records to read, the agent is being handed the answer
    and assertion 3 measures nothing."""
    for card in _cards():
        text = card.read_text(encoding="utf-8").lower()
        assert "what is *not* said" in text, f"{card.name} must not point the agent at the records"


def test_recorded_runs_carry_a_scorer_and_the_context_label() -> None:
    """A self-baseline must be labelled as one. An agent with prior context on
    this repository scores higher on orientation by construction, and an
    unlabelled score would read as evidence the harness works."""
    if not RESULTS.is_file():
        pytest.skip("no runs recorded yet")
    runs = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert isinstance(runs, list) and runs, "runs.json must be a non-empty list"
    for run in runs:
        assert run.get("scorer") not in (None, "", "self"), (
            "an observer scores a run, not the agent"
        )
        assert run.get("context") in {"fresh", "self-baseline"}, run.get("context")
        assert run.get("task") and (BENCH / f"{run['task']}.md").is_file(), run.get("task")
        for name in ASSERTIONS:
            assert name in run.get("scores", {}), f"{run.get('task')}: no score for {name}"
        assert set(run["scores"]) == set(ASSERTIONS), (
            "a scorer that invents assertions is not scoring"
        )
        assert run.get("notes", "").strip(), "a run without notes is a number without a reading"


def test_the_spec_names_the_reading_rule_for_a_self_baseline() -> None:
    assert "self-baseline" in SPEC.read_text(encoding="utf-8").lower()


def test_the_spec_explains_a_low_score_is_a_finding() -> None:
    text = SPEC.read_text(encoding="utf-8").lower()
    assert "not a grade" in text or "is the finding" in text


def test_no_run_is_counted_twice() -> None:
    """Re-running a task must not quietly improve the fleet score by being added
    twice."""
    if not RESULTS.is_file():
        pytest.skip("no runs recorded yet")
    runs = json.loads(RESULTS.read_text(encoding="utf-8"))
    keys = [(r.get("task"), r.get("context"), r.get("agent", "")) for r in runs]
    assert len(keys) == len(set(keys)), f"duplicate run recorded: {keys}"


CARD_TEMPLATE_FIELDS = ("# TASK-", "## The task", "## Bounds", "## Done when")


def test_cards_follow_one_shape() -> None:
    """Scoring reads sections by name; a card without them cannot be scored."""
    for card in _cards():
        text = card.read_text(encoding="utf-8")
        for field in CARD_TEMPLATE_FIELDS:
            assert field in text, f"{card.name} is missing {field!r}"
        assert re.search(r"^# TASK-\d{3}", text, re.M), f"{card.name} must name itself"
