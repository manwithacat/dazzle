"""Tests for the fitness budget controller + degradation ladder (v1 task 6)."""

from __future__ import annotations

from dazzle.fitness.budget import BudgetController, CycleProfile
from dazzle.fitness.config import FitnessConfig


def test_full_budget_runs_all_passes() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile: CycleProfile = bc.plan(available_tokens=100_000)
    assert profile.run_pass1 is True
    assert profile.run_pass2a is True
    assert profile.run_pass2b is True
    assert profile.pass2b_step_budget == 50
    assert profile.adversary_enabled is True
    assert profile.degraded is False


def test_moderate_pressure_shortens_pass2b() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=60_000)
    assert profile.run_pass2b is True
    assert profile.pass2b_step_budget == 20
    assert profile.adversary_enabled is True
    assert profile.degraded is True


def test_heavy_pressure_drops_adversary() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=25_000)
    assert profile.run_pass2b is True
    assert profile.adversary_enabled is False
    assert profile.degraded is True


def test_severe_pressure_drops_pass2b() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=10_000)
    assert profile.run_pass2b is False
    assert profile.run_pass1 is True
    assert profile.degraded is True


def test_pass1_is_never_dropped() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=0)
    assert profile.run_pass1 is True
