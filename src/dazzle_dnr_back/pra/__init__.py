"""
Performance Reference App (PRA) infrastructure.

Provides load generation, data factories, and test harness for
stress testing the Dazzle event-first architecture.

Includes TigerBeetle stress testing for ledger operations (v0.5.0).
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
from .harness import RunResult, RunStatus, StressHarness, run_quick_test, run_standard_test
from .hot_keys import HotKeySelector
from .profiles import (
    BurstProfile,
    FailureInjectionProfile,
    LoadProfile,
    ReplayProfile,
    SkewedBurstProfile,
    SteadyRampProfile,
)
from .scenarios import ScenarioType, StressScenario, SuccessCriteria, get_scenario, list_scenarios

# TigerBeetle imports (require optional tigerbeetle dependency)
# These are lazy-loaded to avoid import errors when tigerbeetle isn't installed
try:
    from .tigerbeetle_client import (
        AccountTemplate,
        TigerBeetleClient,
        TigerBeetleConfig,
        TigerBeetleStats,
        TransferTemplate,
        check_tigerbeetle_available,
    )
    from .tigerbeetle_generator import (
        TBGeneratorConfig,
        TBGeneratorStats,
        TBLoadPhase,
        TigerBeetleLoadGenerator,
        run_quick_tb_test,
    )
    from .tigerbeetle_harness import (
        TBCriteriaResult,
        TBRunResult,
        TBRunStatus,
        TigerBeetleHarness,
        run_quick_tb_scenario,
        run_tb_scenario,
    )
    from .tigerbeetle_scenarios import (
        TBScenario,
        TBScenarioType,
        TBSuccessCriteria,
        get_tb_scenario,
        list_tb_scenarios,
    )

    _TB_AVAILABLE = True
except ImportError:
    _TB_AVAILABLE = False

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
    "RunResult",
    "RunStatus",
    "StressHarness",
    "run_quick_test",
    "run_standard_test",
    # Scenarios
    "ScenarioType",
    "StressScenario",
    "SuccessCriteria",
    "get_scenario",
    "list_scenarios",
    # TigerBeetle (v0.5.0)
    "_TB_AVAILABLE",
]

# Conditionally add TigerBeetle exports
if _TB_AVAILABLE:
    __all__.extend(
        [
            # TigerBeetle Client
            "AccountTemplate",
            "TigerBeetleClient",
            "TigerBeetleConfig",
            "TigerBeetleStats",
            "TransferTemplate",
            "check_tigerbeetle_available",
            # TigerBeetle Generator
            "TBGeneratorConfig",
            "TBGeneratorStats",
            "TBLoadPhase",
            "TigerBeetleLoadGenerator",
            "run_quick_tb_test",
            # TigerBeetle Harness
            "TBCriteriaResult",
            "TBRunResult",
            "TBRunStatus",
            "TigerBeetleHarness",
            "run_quick_tb_scenario",
            "run_tb_scenario",
            # TigerBeetle Scenarios
            "TBScenario",
            "TBScenarioType",
            "TBSuccessCriteria",
            "get_tb_scenario",
            "list_tb_scenarios",
        ]
    )
