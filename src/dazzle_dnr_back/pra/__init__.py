"""
Performance Reference App (PRA) infrastructure.

Provides load generation, data factories, and test harness for
stress testing the Dazzle event-first architecture.
"""

from .data_factory import PRADataFactory
from .generator import GeneratorConfig, LoadGenerator
from .hot_keys import HotKeySelector
from .profiles import (
    BurstProfile,
    FailureInjectionProfile,
    LoadProfile,
    ReplayProfile,
    SkewedBurstProfile,
    SteadyRampProfile,
)

__all__ = [
    "BurstProfile",
    "FailureInjectionProfile",
    "GeneratorConfig",
    "HotKeySelector",
    "LoadGenerator",
    "LoadProfile",
    "PRADataFactory",
    "ReplayProfile",
    "SkewedBurstProfile",
    "SteadyRampProfile",
]
