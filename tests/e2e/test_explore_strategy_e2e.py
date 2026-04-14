"""E2E verification for cycle 197 Layer 4 work.

Runs run_explore_strategy against each of the 5 examples/ apps with
auto-picked business personas and asserts D2's acceptance bar.

Marked @pytest.mark.e2e — excluded from default pytest runs. Invoke
manually:

    pytest tests/e2e/test_explore_strategy_e2e.py -m e2e -v

Environment requirements (all must be present):
- DATABASE_URL and REDIS_URL reachable per-example .env files
- ANTHROPIC_API_KEY in the current shell
- Postgres running locally (pg_isready must succeed)
- Redis running locally (redis-cli ping must return PONG)

Cost: ~$0.50 per full sweep at sonnet-4-6 rates.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

EXAMPLES = [
    "simple_task",
    "contact_manager",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
]

DAZZLE_ROOT = Path(__file__).resolve().parents[2]
ARTEFACTS_DIR = DAZZLE_ROOT / "dev_docs" / "cycle_197_verification"


def _load_example_env(example_root: Path) -> None:
    """Load DATABASE_URL and REDIS_URL from the example's .env file into os.environ."""
    env_path = example_root / ".env"
    if not env_path.exists():
        pytest.skip(f"{env_path} not found — example not configured for e2e")
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        os.environ[k] = v  # overwrite — each example has its own DB


@pytest.fixture(scope="module")
def artefacts_dir() -> Path:
    ARTEFACTS_DIR.mkdir(parents=True, exist_ok=True)
    # Clean stale artefacts from prior runs — prevents the sweep test
    # from reading files left over by an earlier successful run and
    # masking a current-run regression.
    for artefact in ARTEFACTS_DIR.glob("*.json"):
        artefact.unlink()
    return ARTEFACTS_DIR


@pytest.mark.e2e
@pytest.mark.parametrize("example_name", EXAMPLES)
async def test_explore_strategy_against_example(example_name: str, artefacts_dir: Path) -> None:
    """run_explore_strategy produces non-degraded outcome against each example."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    example_root = DAZZLE_ROOT / "examples" / example_name
    _load_example_env(example_root)

    from dazzle.agent.missions.ux_explore import Strategy
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=None,  # ModeRunner doesn't need explicit list; strategy picks
        db_policy="preserve",
    ) as conn:
        outcome = await run_explore_strategy(
            conn,
            example_root=example_root,
            strategy=Strategy.MISSING_CONTRACTS,
            personas=None,  # auto-pick business personas
        )

    # Record the outcome as an artefact for debugging / cross-cycle comparison
    artefact = artefacts_dir / f"{example_name}.json"
    artefact.write_text(
        json.dumps(
            {
                "strategy": outcome.strategy,
                "summary": outcome.summary,
                "degraded": outcome.degraded,
                "proposals": outcome.proposals,
                "findings": outcome.findings,
                "blocked_personas": [
                    {"persona_id": pid, "reason": r} for (pid, r) in outcome.blocked_personas
                ],
                "steps_run": outcome.steps_run,
                "tokens_used": outcome.tokens_used,
                "raw_proposals_by_persona": outcome.raw_proposals_by_persona,
            },
            indent=2,
        )
    )

    # Primary assertion: the strategy ran cleanly
    assert outcome.degraded is False, (
        f"{example_name}: degraded=True indicates a per-persona failure "
        f"or infrastructure problem (see {artefact})"
    )


@pytest.mark.e2e
async def test_sweep_has_three_apps_with_proposals(artefacts_dir: Path) -> None:
    """After running all 5 apps, at least 3 must have ≥1 proposal each.

    This test MUST run AFTER the parametrised test above — it reads the
    artefacts that test wrote. pytest orders tests lexically within a
    file, so this test's name ('test_sweep_has_...') comes after the
    parametrised ones alphabetically. If you reorder, check the ordering.
    """
    apps_with_proposals = 0
    missing: list[str] = []
    for example in EXAMPLES:
        artefact = artefacts_dir / f"{example}.json"
        if not artefact.exists():
            missing.append(example)
            continue
        data = json.loads(artefact.read_text())
        if len(data.get("proposals", [])) >= 1:
            apps_with_proposals += 1

    if missing:
        pytest.skip(f"sweep check requires parametrised test to run first; missing: {missing}")

    assert apps_with_proposals >= 3, (
        f"D2 acceptance bar: ≥3 of 5 apps should have ≥1 proposal, "
        f"got {apps_with_proposals}. See artefacts in {artefacts_dir}"
    )


@pytest.mark.e2e
def test_bail_nudge_demonstrably_fires(artefacts_dir: Path) -> None:
    """At least one persona-cycle across the sweep shows the bail-nudge text.

    Since the current spec doesn't plumb transcript text into the outcome
    artefact, this test is currently a SKIP until we add transcript
    capture. Tracked as a cycle-198 item. For now, verify manually that
    some persona-run's transcript log contains 'You appear to be stuck'.
    """
    pytest.skip(
        "bail-nudge introspection needs transcript capture in outcome artefact "
        "(cycle 198 follow-up)"
    )
