"""
Performance Reference App (PRA) infrastructure.

Provides load generation, data factories, and test harness for
stress testing the Dazzle event-first architecture.
"""

from .consumers import (
    ConsumerGroup,
    DerivationConsumer,
    FailingConsumer,
    NormalConsumer,
    ProjectionConsumer,
    SlowConsumer,
    TestConsumer,
)
from .data_factory import PRADataFactory
from .generator import GeneratorConfig, LoadGenerator
from .harness import TestHarness, TestResult, TestStatus, run_quick_test, run_standard_test
from .hot_keys import HotKeySelector
from .profiles import (
    BurstProfile,
    FailureInjectionProfile,
    LoadProfile,
    ReplayProfile,
    SkewedBurstProfile,
    SteadyRampProfile,
)
from .scenarios import ScenarioType, SuccessCriteria, TestScenario, get_scenario, list_scenarios

# CLI group is imported on demand to avoid click dependency at import time
# Use: from dazzle_dnr_back.pra.cli import pra_group

__all__ = [
    # Profiles
    "BurstProfile",
    "FailureInjectionProfile",
    "LoadProfile",
    "ReplayProfile",
    "SkewedBurstProfile",
    "SteadyRampProfile",
    # Generator
    "GeneratorConfig",
    "HotKeySelector",
    "LoadGenerator",
    "PRADataFactory",
    # Consumers
    "ConsumerGroup",
    "DerivationConsumer",
    "FailingConsumer",
    "NormalConsumer",
    "ProjectionConsumer",
    "SlowConsumer",
    "TestConsumer",
    # Harness
    "TestHarness",
    "TestResult",
    "TestStatus",
    "run_quick_test",
    "run_standard_test",
    # Scenarios
    "ScenarioType",
    "SuccessCriteria",
    "TestScenario",
    "get_scenario",
    "list_scenarios",
]
