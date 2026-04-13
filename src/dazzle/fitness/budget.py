"""Per-cycle token budget controller + degradation ladder.

The fitness engine has a fixed token budget per cycle. When available tokens
drop, we shed work in a fixed order:

    1. Full      — all passes, pass2b with 50 steps, adversary enabled
    2. Short     — pass2b shortened to 20 steps
    3. Heavy     — adversary dropped, pass2b at 10 steps
    4. Severe    — pass2b dropped entirely (pass1 + pass2a only)
    5. Minimum   — pass1 only (the deterministic walker is never dropped)

Pass 1 is **never** degraded — the deterministic story walker is free in
token terms and provides the baseline evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.fitness.config import FitnessConfig


@dataclass(frozen=True)
class CycleProfile:
    run_pass1: bool
    run_pass2a: bool
    run_pass2b: bool
    pass2b_step_budget: int
    adversary_enabled: bool
    degraded: bool
    reason: str


# Approximate token costs per phase, used for planning only.
_TOKENS_PER_PASS2B_STEP = 1500  # ~1.5k per EXPECT/ACTION/OBSERVE cycle
_TOKENS_PASS2A_CORE = 5_000  # spec_extractor + cross_check
_TOKENS_PASS2A_ADVERSARY = 5_000

_PASS2B_FULL_STEPS = 50
_PASS2B_SHORT_STEPS = 20
_PASS2B_HEAVY_STEPS = 10


class BudgetController:
    """Plans one cycle by mapping available tokens → ``CycleProfile``."""

    def __init__(self, config: FitnessConfig) -> None:
        self._config = config

    def plan(self, available_tokens: int) -> CycleProfile:
        full_cost = (
            _TOKENS_PASS2A_CORE
            + _TOKENS_PASS2A_ADVERSARY
            + _PASS2B_FULL_STEPS * _TOKENS_PER_PASS2B_STEP
        )
        short_cost = (
            _TOKENS_PASS2A_CORE
            + _TOKENS_PASS2A_ADVERSARY
            + _PASS2B_SHORT_STEPS * _TOKENS_PER_PASS2B_STEP
        )
        heavy_cost = _TOKENS_PASS2A_CORE + _PASS2B_HEAVY_STEPS * _TOKENS_PER_PASS2B_STEP
        minimum_cost = _TOKENS_PASS2A_CORE  # Pass 1 is free in token terms

        if available_tokens >= full_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_FULL_STEPS,
                adversary_enabled=True,
                degraded=False,
                reason="full budget",
            )
        if available_tokens >= short_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_SHORT_STEPS,
                adversary_enabled=True,
                degraded=True,
                reason="pass2b shortened",
            )
        if available_tokens >= heavy_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_HEAVY_STEPS,
                adversary_enabled=False,
                degraded=True,
                reason="adversary dropped",
            )
        if available_tokens >= minimum_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=False,
                pass2b_step_budget=0,
                adversary_enabled=False,
                degraded=True,
                reason="pass2b dropped",
            )
        return CycleProfile(
            run_pass1=True,
            run_pass2a=False,
            run_pass2b=False,
            pass2b_step_budget=0,
            adversary_enabled=False,
            degraded=True,
            reason="pass1 only",
        )
