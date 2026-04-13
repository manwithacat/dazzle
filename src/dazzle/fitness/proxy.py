"""Pass 2b proxy dispatcher.

Builds a free-roam mission and runs it through a pre-constructed
:class:`dazzle.agent.core.DazzleAgent`. The agent's tool layer must
already be wrapped in :func:`dazzle.fitness.interlock.interlocked_tool_call`
at registration time — that is the fitness engine's responsibility, not
this module's.
"""

from __future__ import annotations

from typing import Any

from dazzle.fitness.missions.free_roam import build_free_roam_mission


async def run_proxy_mission(
    agent: Any,
    persona: Any,
    intent: str,
    step_budget: int,
    ledger: Any,
) -> Any:
    """Dispatch a Pass 2b behavioural proxy mission via ``DazzleAgent``.

    Parameters
    ----------
    agent:
        A constructed :class:`DazzleAgent` (or compatible) whose tool
        registry has already been wrapped with interlock guards.
    persona:
        The persona being proxied — must expose ``id`` or ``name``.
    intent:
        Natural-language goal for this run.
    step_budget:
        Maximum number of steps the mission may take.
    ledger:
        The fitness ledger (held for future engine-side wiring).

    Returns
    -------
    Whatever ``agent.run`` returns (typically an ``AgentTranscript``).
    """
    del ledger  # Reserved for future engine-side integration.
    mission = build_free_roam_mission(
        persona=persona,
        intent=intent,
        step_budget=step_budget,
    )
    return await agent.run(mission)
