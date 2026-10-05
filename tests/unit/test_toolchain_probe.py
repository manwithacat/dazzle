"""Every probe-dependent playbook must declare the toolchain it needs (#1758 F5).

Cycle 2411 selected the forced campaign `example-apps agent_qa_smoke` and hit
a wall: `dazzle qa smoke-dig` needs Playwright, which lives in the `e2e` extra
and is not installed by `make dev-install`. The playbook's FIX bar is a table of
*findings* — there was no row for "the tool is missing", so no defined outcome
existed and the agent improvised.

This gate closes the class, not the instance: a strategy that reaches for a
browser, a database or a live app must name it in
`tests/unit/fixtures/toolchain_capabilities.json`, so (a) `improve_toolchain.py
--require <cap>` can refuse to select the strategy and (b) adding a new tool
dependency to a playbook cannot happen quietly.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
IMPROVE = REPO / ".agents" / "skills" / "improve"
CAPS = REPO / "tests" / "unit" / "fixtures" / "toolchain_capabilities.json"
PROBE = REPO / "scripts" / "improve_toolchain.py"

STRATEGIES = sorted((IMPROVE / "strategies").glob("*.md"))
LANES = sorted((IMPROVE / "lanes").glob("*.md"))
STRATEGIES_BY_NAME = {p.stem: p for p in STRATEGIES}
LANES_BY_NAME = {p.stem: p for p in LANES}

# What a playbook has to say before it can be selected. The strategies are the
# dig playbooks; the lanes own selection.
NEEDS_TOOLCHAIN = ("## FIX bar", "## When picked", "## OBSERVE")

# Signalling a tool dependency. Deliberately concrete: naming a capability
# constant, an extra, or the binary/port the step needs.
TOOL_SIGNALS = re.compile(
    r"playwright|smoke-crawl|smoke-dig|smoke-crawl|DATABASE_URL|dazzle serve|"
    r"--test-mode|visual|capture|gh issue|gh run|gh pr|QA_MODE",
    re.IGNORECASE,
)

BLOCKED_ROW = re.compile(r"\|\s*`?BLOCKED", re.IGNORECASE)


def _caps() -> list[dict[str, Any]]:
    return json.loads(CAPS.read_text(encoding="utf-8"))


def _known() -> set[str]:
    return {c["name"] for c in _caps()}


def _requires(cap: dict[str, Any], strategy: str) -> bool:
    return strategy in cap["required_for"]


def test_the_probe_runs_and_answers_help() -> None:
    """A precondition check that cannot start is not a precondition check."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(PROBE), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr[-300:]


def test_every_capability_has_a_remedy_and_a_probe() -> None:
    """A MISS line with no remedy is the dead end W5 exists to remove."""
    for cap in _caps():
        assert cap["remedy"].strip(), f"{cap['name']}: a missing capability must say what to do"
        assert cap["probe"] in {"module", "binary", "env", "url", "any"}, cap
        assert cap["required_for"], f"{cap['name']}: nothing declares needing it"


def test_the_probe_reports_every_capability_without_raising() -> None:
    """Including on a host with nothing installed — the report is what an agent
    reads when it is blocked."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("improve_toolchain", PROBE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    rows = mod.report()

    assert {r["name"] for r in rows} == _known()
    for row in rows:
        assert isinstance(row["ok"], bool), row
        if not row["ok"]:
            assert row["remedy"].strip(), row


def test_every_toolchain_requiring_strategy_declares_its_capabilities() -> None:
    """The durable half: a playbook that reaches for a tool must be covered here.

    The five strategies below are the ones that reached for a browser, a database
    or a live app without saying so.
    """
    known = _known()
    covered = {strategy for cap in _caps() for strategy in cap["required_for"]}

    for playbook in STRATEGIES + LANES:
        name = playbook.stem
        text = playbook.read_text(encoding="utf-8")
        if not TOOL_SIGNALS.search(text) or name in covered:
            continue
        # A lane dispatches sub-strategies, so its toolchain is their union; it
        # is exempt when it points at the capability list, which is where that
        # union is read from.
        if playbook in LANES and CAPS.name in text:
            continue
        pytest.fail(
            f"{playbook.name} uses a harness tool but declares no required "
            f"capability. Add it to {CAPS.name} under one of {sorted(known)} "
            "so improve_toolchain.py --require can refuse to select it."
        )


def test_strategies_with_tool_requirements_state_a_blocked_outcome() -> None:
    """A missing tool has to be a *first-class outcome*. The vocabulary already
    has `BLOCKED` (Step 2's outcome union); these playbooks must use it."""
    for playbook in STRATEGIES:
        name = playbook.stem
        text = playbook.read_text(encoding="utf-8")
        needs = any(_requires(cap, name) for cap in _caps())
        if not needs:
            continue
        assert BLOCKED_ROW.search(text) or "BLOCKED" in text, (
            f"{playbook.name} declares a toolchain requirement but has no BLOCKED "
            "row in its FIX bar — a missing tool must be a first-class outcome, "
            "not an improvised dead end (#1758 F5)"
        )


# --- the chain marker (#1759 W6) ---------------------------------------------
# `scheduler_create` is the only capability whose absence is invisible: every
# other missing tool errors when used, and this one produces silence — the cycle
# completes, logs a scheduling decision, and no further cycle ever runs. That is
# indistinguishable from a loop with nothing to do, which is how this loop sat
# parked for 30 days.


def test_schedule_records_whether_the_chain_was_armed(tmp_path: Path) -> None:
    """`--chain-armed 0` must leave a machine-readable marker, because the
    agent that could not arm the chain is exactly the agent nobody is watching."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "sched", REPO / "scripts" / "improve_schedule_next.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sched"] = mod
    spec.loader.exec_module(mod)
    monkey_state = tmp_path / "improve-schedule-state.json"
    monkey_state.write_text("{}", encoding="utf-8")
    mod.STATE = monkey_state

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert mod.main(["--result", "PASS", "--ci", "green", "--chain-armed", "0"]) == 0

    state = json.loads(monkey_state.read_text(encoding="utf-8"))
    if state["action"] == "schedule":
        assert state["chain_armed"] is False
        assert "scheduler_create" in state["chain_blocked_reason"]

    # And the armed case is the default, so a host that did arm it is not
    # reported as broken.
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        mod.main(["--result", "PASS", "--ci", "green"])
    armed = json.loads(monkey_state.read_text(encoding="utf-8"))
    if armed["action"] == "schedule":
        assert armed["chain_armed"] is True
        assert armed["chain_blocked_reason"] is None


def test_reconcile_reports_an_unarmed_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "reconcile", REPO / "scripts" / "repo_reconcile.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reconcile"] = mod
    spec.loader.exec_module(mod)

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "action": "schedule",
                "interval": "15m",
                "chain_armed": False,
                "chain_blocked_reason": "host provides no scheduler_create",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "SCHEDULE_STATE", state)

    report = mod.Report()
    mod.check_chain(report)

    chain = [f for f in report.findings if f.kind == "improve-chain"]
    assert chain and chain[0].severity == "action", report.findings
    assert "never armed" in chain[0].detail


def test_reconcile_is_quiet_when_the_chain_is_armed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "reconcile", REPO / "scripts" / "repo_reconcile.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reconcile"] = mod
    spec.loader.exec_module(mod)

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"action": "schedule", "interval": "15m", "chain_armed": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "SCHEDULE_STATE", state)

    report = mod.Report()
    mod.check_chain(report)

    assert report.findings == []


# --- the other direction: a declaration that is not true ----------------------
# Everything above catches a dependency that exists and was not declared. This
# catches the opposite, and it is the half that makes the inventory trustworthy:
# a capability listed for a strategy that does not use it, or a BLOCKED row that
# names a probe which cannot answer for it. Both make the toolchain report
# confidently wrong — the failure mode this programme has spent its life on.


def test_the_fixture_equals_the_derivation() -> None:
    """`required_for` is derived from the playbooks and pinned here.

    The first version of this inventory was written by hand and got it wrong
    twice: five names that resolve to no playbook at all, and eleven strategies
    listed for a database they never mention. A hand-kept capability map is a
    claim; this makes it a reading of the playbooks.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "toolchain_probe_src", REPO / "scripts" / "improve_toolchain.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    derived = mod.derive_requirements()
    for cap in _caps():
        want = derived.get(cap["name"])
        if want is None:
            continue
        assert cap["required_for"] == want, (
            f"{cap['name']}: fixture says {cap['required_for']}, the playbooks say {want}. "
            "Run: uv run python scripts/improve_toolchain.py --refresh"
        )


def test_no_capability_claims_a_strategy_that_does_not_use_it() -> None:
    """`required_for` is a claim. A wrong claim sends an operator to install
    something a strategy never needed, and teaches the next reader that the
    strategy needs it."""
    wrong: list[str] = []
    for cap in _caps():
        for strategy in cap["required_for"]:
            playbook = STRATEGIES_BY_NAME.get(strategy) or LANES_BY_NAME.get(strategy)
            if playbook is None:
                wrong.append(f"{cap['name']} requires {strategy}, which does not exist")
                continue
            text = playbook.read_text(encoding="utf-8")
            if not TOOL_SIGNALS.search(text) and "## Toolchain" not in text:
                wrong.append(f"{cap['name']} requires {strategy}, which names no tool")
    assert not wrong, "capabilities requiring a strategy that does not use them:\n  " + "\n  ".join(
        wrong
    )


def _toolchain_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "toolchain_probe_src", REPO / "scripts" / "improve_toolchain.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_declared_requirement_is_a_real_tool_signal() -> None:
    """Each capability's signal must appear in the playbooks it claims.

    Reads the signal table from `improve_toolchain.py` rather than keeping a
    second copy: the first copy drifted (it matched the word "render" and claimed
    a browser for a strategy that never drives one).
    """
    signals = _toolchain_module().SIGNALS
    unsubstantiated: list[str] = []
    for cap in _caps():
        pattern = signals.get(cap["name"])
        if pattern is None:
            continue
        for strategy in cap["required_for"]:
            playbook = STRATEGIES_BY_NAME.get(strategy) or LANES_BY_NAME.get(strategy)
            if playbook is None:
                continue
            if not re.search(pattern, playbook.read_text(encoding="utf-8"), re.IGNORECASE):
                unsubstantiated.append(f"{cap['name']} -> {strategy} (no matching signal)")
    assert not unsubstantiated, "\n".join(unsubstantiated)


def test_a_strategy_that_declares_a_toolchain_says_how_to_report_it_blocked() -> None:
    """Every BLOCKED outcome must be reachable by name. A playbook that says
    `BLOCKED` without naming the probe leaves the next agent to invent the
    command."""
    unnamed: list[str] = []
    for cap in _caps():
        for strategy in cap["required_for"]:
            playbook = STRATEGIES_BY_NAME.get(strategy)
            if playbook is None or "BLOCKED" not in playbook.read_text(encoding="utf-8"):
                continue
            if "improve_toolchain.py" not in playbook.read_text(encoding="utf-8"):
                unnamed.append(f"{strategy} reports BLOCKED without naming improve_toolchain.py")
    assert not unnamed, "\n".join(unnamed)
