"""
Load profiles for PRA stress testing.

Defines various load shapes as specified in the PRA specification:
- Steady Ramp: Gradual increase to peak load
- Burst: Sudden spike (≥10× baseline) for short duration
- Skewed Burst: Burst focused on a small key set
- Failure Injection: Partial downstream failure
- Replay Mode: Processing from offset zero without live writes
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LoadPhase(StrEnum):
    """Current phase of load profile execution."""

    WARMUP = "warmup"
    RAMP = "ramp"
    PEAK = "peak"
    COOLDOWN = "cooldown"
    COMPLETE = "complete"


@dataclass
class LoadState:
    """Current state of load profile execution."""

    phase: LoadPhase
    target_rate: float  # events per second
    elapsed_seconds: float
    remaining_seconds: float
    progress_pct: float
    metadata: dict[str, Any] = field(default_factory=dict)


class LoadProfile(ABC):
    """
    Abstract base class for load profiles.

    Subclasses implement specific load shapes by calculating
    the target rate at any given time.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Profile name for reporting."""
        ...

    @property
    @abstractmethod
    def total_duration_seconds(self) -> float:
        """Total profile duration in seconds."""
        ...

    @abstractmethod
    def get_state(self, elapsed_seconds: float) -> LoadState:
        """
        Get current load state at elapsed time.

        Args:
            elapsed_seconds: Time since profile start

        Returns:
            LoadState with current target rate and phase
        """
        ...

    def is_complete(self, elapsed_seconds: float) -> bool:
        """Check if profile execution is complete."""
        return elapsed_seconds >= self.total_duration_seconds


@dataclass
class SteadyRampProfile(LoadProfile):
    """
    Gradual increase to peak load, hold, then decrease.

    Phases:
    1. Warmup: Start at warmup_rate for warmup_seconds
    2. Ramp: Linear increase from warmup_rate to peak_rate
    3. Peak: Hold at peak_rate for peak_seconds
    4. Cooldown: Linear decrease back to warmup_rate

    Example:
        profile = SteadyRampProfile(
            warmup_rate=10,
            peak_rate=1000,
            warmup_seconds=30,
            ramp_seconds=60,
            peak_seconds=300,
            cooldown_seconds=30,
        )
    """

    warmup_rate: float = 10.0
    peak_rate: float = 1000.0
    warmup_seconds: float = 30.0
    ramp_seconds: float = 60.0
    peak_seconds: float = 300.0
    cooldown_seconds: float = 30.0

    @property
    def name(self) -> str:
        return "steady_ramp"

    @property
    def total_duration_seconds(self) -> float:
        return self.warmup_seconds + self.ramp_seconds + self.peak_seconds + self.cooldown_seconds

    def get_state(self, elapsed_seconds: float) -> LoadState:
        total = self.total_duration_seconds
        remaining = max(0, total - elapsed_seconds)
        progress = min(100, (elapsed_seconds / total) * 100) if total > 0 else 100

        # Warmup phase
        if elapsed_seconds < self.warmup_seconds:
            return LoadState(
                phase=LoadPhase.WARMUP,
                target_rate=self.warmup_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Ramp phase
        ramp_start = self.warmup_seconds
        ramp_end = ramp_start + self.ramp_seconds
        if elapsed_seconds < ramp_end:
            ramp_progress = (elapsed_seconds - ramp_start) / self.ramp_seconds
            rate = self.warmup_rate + (self.peak_rate - self.warmup_rate) * ramp_progress
            return LoadState(
                phase=LoadPhase.RAMP,
                target_rate=rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Peak phase
        peak_end = ramp_end + self.peak_seconds
        if elapsed_seconds < peak_end:
            return LoadState(
                phase=LoadPhase.PEAK,
                target_rate=self.peak_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Cooldown phase
        cooldown_end = peak_end + self.cooldown_seconds
        if elapsed_seconds < cooldown_end:
            cooldown_progress = (elapsed_seconds - peak_end) / self.cooldown_seconds
            rate = self.peak_rate - (self.peak_rate - self.warmup_rate) * cooldown_progress
            return LoadState(
                phase=LoadPhase.COOLDOWN,
                target_rate=rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Complete
        return LoadState(
            phase=LoadPhase.COMPLETE,
            target_rate=0,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=0,
            progress_pct=100,
        )


@dataclass
class BurstProfile(LoadProfile):
    """
    Sudden spike (≥10× baseline) for short duration.

    Phases:
    1. Baseline: Steady rate at baseline_rate
    2. Burst: Sudden jump to burst_multiplier × baseline_rate
    3. Recovery: Return to baseline

    Example:
        profile = BurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            baseline_seconds=60,
            burst_seconds=30,
            recovery_seconds=60,
        )
    """

    baseline_rate: float = 100.0
    burst_multiplier: float = 10.0
    baseline_seconds: float = 60.0
    burst_seconds: float = 30.0
    recovery_seconds: float = 60.0

    @property
    def name(self) -> str:
        return "burst"

    @property
    def total_duration_seconds(self) -> float:
        return self.baseline_seconds + self.burst_seconds + self.recovery_seconds

    @property
    def burst_rate(self) -> float:
        return self.baseline_rate * self.burst_multiplier

    def get_state(self, elapsed_seconds: float) -> LoadState:
        total = self.total_duration_seconds
        remaining = max(0, total - elapsed_seconds)
        progress = min(100, (elapsed_seconds / total) * 100) if total > 0 else 100

        # Baseline phase
        if elapsed_seconds < self.baseline_seconds:
            return LoadState(
                phase=LoadPhase.WARMUP,
                target_rate=self.baseline_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
                metadata={"burst_multiplier": self.burst_multiplier},
            )

        # Burst phase
        burst_end = self.baseline_seconds + self.burst_seconds
        if elapsed_seconds < burst_end:
            return LoadState(
                phase=LoadPhase.PEAK,
                target_rate=self.burst_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
                metadata={"burst_active": True},
            )

        # Recovery phase
        recovery_end = burst_end + self.recovery_seconds
        if elapsed_seconds < recovery_end:
            return LoadState(
                phase=LoadPhase.COOLDOWN,
                target_rate=self.baseline_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Complete
        return LoadState(
            phase=LoadPhase.COMPLETE,
            target_rate=0,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=0,
            progress_pct=100,
        )


@dataclass
class SkewedBurstProfile(LoadProfile):
    """
    Burst focused on a small key set (hot partition stress).

    Like BurstProfile, but during burst phase, traffic is concentrated
    on hot keys to stress partition handling.

    The hot_key_probability indicates what fraction of burst traffic
    should target hot keys.

    Example:
        profile = SkewedBurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            hot_key_probability=0.95,  # 95% of burst hits hot keys
        )
    """

    baseline_rate: float = 100.0
    burst_multiplier: float = 10.0
    hot_key_probability: float = 0.95
    baseline_seconds: float = 60.0
    burst_seconds: float = 30.0
    recovery_seconds: float = 60.0

    @property
    def name(self) -> str:
        return "skewed_burst"

    @property
    def total_duration_seconds(self) -> float:
        return self.baseline_seconds + self.burst_seconds + self.recovery_seconds

    @property
    def burst_rate(self) -> float:
        return self.baseline_rate * self.burst_multiplier

    def get_state(self, elapsed_seconds: float) -> LoadState:
        total = self.total_duration_seconds
        remaining = max(0, total - elapsed_seconds)
        progress = min(100, (elapsed_seconds / total) * 100) if total > 0 else 100

        # Check if in burst phase
        burst_start = self.baseline_seconds
        burst_end = burst_start + self.burst_seconds
        in_burst = burst_start <= elapsed_seconds < burst_end

        # Baseline phase
        if elapsed_seconds < self.baseline_seconds:
            return LoadState(
                phase=LoadPhase.WARMUP,
                target_rate=self.baseline_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Burst phase (with skew metadata)
        if in_burst:
            return LoadState(
                phase=LoadPhase.PEAK,
                target_rate=self.burst_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
                metadata={
                    "skewed_burst": True,
                    "hot_key_probability": self.hot_key_probability,
                },
            )

        # Recovery phase
        recovery_end = burst_end + self.recovery_seconds
        if elapsed_seconds < recovery_end:
            return LoadState(
                phase=LoadPhase.COOLDOWN,
                target_rate=self.baseline_rate,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=remaining,
                progress_pct=progress,
            )

        # Complete
        return LoadState(
            phase=LoadPhase.COMPLETE,
            target_rate=0,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=0,
            progress_pct=100,
        )


@dataclass
class FailureInjectionProfile(LoadProfile):
    """
    Steady load with partial downstream failure injection.

    Maintains a steady rate while simulating partial failures
    of downstream services (database, external API).

    Example:
        profile = FailureInjectionProfile(
            rate=500,
            failure_probability=0.20,  # 20% of requests fail
            failure_targets=["database", "payment_gateway"],
        )
    """

    rate: float = 500.0
    failure_probability: float = 0.20
    failure_targets: list[str] = field(default_factory=lambda: ["database"])
    duration_seconds: float = 300.0

    @property
    def name(self) -> str:
        return "failure_injection"

    @property
    def total_duration_seconds(self) -> float:
        return self.duration_seconds

    def get_state(self, elapsed_seconds: float) -> LoadState:
        remaining = max(0, self.duration_seconds - elapsed_seconds)
        progress = min(100, (elapsed_seconds / self.duration_seconds) * 100)

        if elapsed_seconds >= self.duration_seconds:
            return LoadState(
                phase=LoadPhase.COMPLETE,
                target_rate=0,
                elapsed_seconds=elapsed_seconds,
                remaining_seconds=0,
                progress_pct=100,
            )

        return LoadState(
            phase=LoadPhase.PEAK,
            target_rate=self.rate,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=remaining,
            progress_pct=progress,
            metadata={
                "failure_injection": True,
                "failure_probability": self.failure_probability,
                "failure_targets": self.failure_targets,
            },
        )


@dataclass
class ReplayProfile(LoadProfile):
    """
    Processing from offset zero without live writes.

    Used to measure rebuild time for DERIVATION streams.
    Rate is "as fast as possible" (controlled by max_rate).

    Example:
        profile = ReplayProfile(
            source_stream="orders_fact",
            max_rate=10000,  # Cap at 10k/sec
        )
    """

    source_stream: str = "orders_fact"
    max_rate: float = 10000.0
    estimated_records: int = 100000

    @property
    def name(self) -> str:
        return "replay"

    @property
    def total_duration_seconds(self) -> float:
        # Estimate based on max rate
        return self.estimated_records / self.max_rate

    def get_state(self, elapsed_seconds: float) -> LoadState:
        estimated_total = self.total_duration_seconds
        remaining = max(0, estimated_total - elapsed_seconds)
        progress = min(100, (elapsed_seconds / estimated_total) * 100)

        return LoadState(
            phase=LoadPhase.PEAK,
            target_rate=self.max_rate,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=remaining,
            progress_pct=progress,
            metadata={
                "replay_mode": True,
                "source_stream": self.source_stream,
                "estimated_records": self.estimated_records,
            },
        )


def create_quick_test_profile() -> SteadyRampProfile:
    """Create a quick 60-second test profile."""
    return SteadyRampProfile(
        warmup_rate=10,
        peak_rate=100,
        warmup_seconds=10,
        ramp_seconds=10,
        peak_seconds=30,
        cooldown_seconds=10,
    )


def create_standard_test_profile() -> SteadyRampProfile:
    """Create a standard 5-minute test profile."""
    return SteadyRampProfile(
        warmup_rate=50,
        peak_rate=1000,
        warmup_seconds=30,
        ramp_seconds=60,
        peak_seconds=180,
        cooldown_seconds=30,
    )


def create_extended_test_profile() -> SteadyRampProfile:
    """Create an extended 30-minute test profile."""
    return SteadyRampProfile(
        warmup_rate=100,
        peak_rate=5000,
        warmup_seconds=60,
        ramp_seconds=180,
        peak_seconds=1200,
        cooldown_seconds=60,
    )
