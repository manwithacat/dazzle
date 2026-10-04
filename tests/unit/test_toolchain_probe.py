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
