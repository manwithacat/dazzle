"""
TigerBeetle load generator for PRA stress testing.

Generates synthetic account and transfer workloads to exercise
TigerBeetle under various load patterns.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .tigerbeetle_client import (
    AccountTemplate,
    TigerBeetleClient,
    TigerBeetleConfig,
    TransferTemplate,
)

if TYPE_CHECKING:
    from dazzle_back.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class TBLoadPhase(str, Enum):
    """Phases of TigerBeetle load generation."""

    WARMUP = "warmup"
    ACCOUNT_CREATION = "account_creation"
    STEADY_TRANSFERS = "steady_transfers"
    BURST_TRANSFERS = "burst_transfers"
    MULTI_LEG = "multi_leg"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"


@dataclass
class TBGeneratorConfig:
    """Configuration for TigerBeetle load generator."""

    # Account settings
    num_accounts: int = 1000
    accounts_per_batch: int = 100
    ledger_id: int = 1
    account_code: int = 1000

    # Transfer settings
    transfers_per_second: int = 100
    min_transfer_amount: int = 100  # Minor units
    max_transfer_amount: int = 100000
    multi_leg_probability: float = 0.1  # 10% multi-leg transactions
    max_legs_per_transaction: int = 4

    # Hot key settings (Pareto distribution)
    hot_account_probability: float = 0.8  # 80% of transfers use hot accounts
    hot_account_count: int = 10  # Number of "hot" accounts

    # Failure injection
    failure_probability: float = 0.0  # Probability of intentional failures
    overdraft_probability: float = 0.02  # 2% overdraft attempts

    # Duration
    warmup_seconds: int = 5
    steady_seconds: int = 30
    burst_seconds: int = 10
    burst_multiplier: float = 5.0
    cooldown_seconds: int = 5

    # Reproducibility
    seed: int = 42


@dataclass
class TBGeneratorStats:
    """Statistics from TigerBeetle load generation."""

    accounts_created: int = 0
    accounts_failed: int = 0
    transfers_created: int = 0
    transfers_failed: int = 0
    multi_leg_transfers: int = 0
    overdraft_attempts: int = 0
    total_amount_transferred: int = 0
    phase: TBLoadPhase = TBLoadPhase.WARMUP
    elapsed_seconds: float = 0.0
    current_rate: float = 0.0


@dataclass
class TBGeneratorState:
    """Current state of the generator."""

    phase: TBLoadPhase
    progress_pct: float
    target_rate: float
    actual_rate: float
    accounts_created: int
    transfers_completed: int


class TigerBeetleLoadGenerator:
    """
    Load generator for TigerBeetle stress testing.

    Generates synthetic workloads including:
    - Account creation (batch)
    - Single transfers (steady and burst)
    - Multi-leg linked transfers
    - Hot key concentration (Pareto)
    - Overdraft attempts (for constraint testing)

    Example:
        config = TBGeneratorConfig(num_accounts=500, transfers_per_second=50)
        generator = TigerBeetleLoadGenerator(config)
        async with TigerBeetleClient.connect() as client:
            stats = await generator.run(client)
            print(f"Transfers: {stats.transfers_created}")
    """

    def __init__(
        self,
        config: TBGeneratorConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        """
        Initialize the load generator.

        Args:
            config: Generator configuration
            metrics: Optional metrics collector
        """
        self._config = config or TBGeneratorConfig()
        self._metrics = metrics
        self._stats = TBGeneratorStats()
        self._running = False
        self._rng = random.Random(self._config.seed)

        # Account pools
        self._accounts: list[int] = []
        self._hot_accounts: list[int] = []
        self._cold_accounts: list[int] = []

        # State tracking
        self._start_time: float = 0.0
        self._phase_start: float = 0.0
        self._transfers_this_second: int = 0
        self._last_rate_check: float = 0.0

    @property
    def is_running(self) -> bool:
        """Check if generator is running."""
        return self._running

    @property
    def stats(self) -> TBGeneratorStats:
        """Get current statistics."""
        return self._stats

    def get_current_state(self) -> TBGeneratorState:
        """Get current generator state."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        total_duration = (
            self._config.warmup_seconds
            + self._config.steady_seconds
            + self._config.burst_seconds
            + self._config.cooldown_seconds
        )
        progress = min(100.0, (elapsed / total_duration) * 100) if total_duration > 0 else 0

        return TBGeneratorState(
            phase=self._stats.phase,
            progress_pct=progress,
            target_rate=self._get_target_rate(),
            actual_rate=self._stats.current_rate,
            accounts_created=self._stats.accounts_created,
            transfers_completed=self._stats.transfers_created,
        )

    def _get_target_rate(self) -> float:
        """Get target transfer rate for current phase."""
        phase = self._stats.phase
        base_rate = self._config.transfers_per_second

        if phase == TBLoadPhase.WARMUP:
            return base_rate * 0.1
        elif phase == TBLoadPhase.BURST_TRANSFERS:
            return base_rate * self._config.burst_multiplier
        elif phase == TBLoadPhase.COOLDOWN:
            return base_rate * 0.5
        else:
            return base_rate

    async def run(self, client: TigerBeetleClient) -> TBGeneratorStats:
        """
        Run the full load generation sequence.

        Args:
            client: Connected TigerBeetle client

        Returns:
            Final statistics
        """
        self._running = True
        self._start_time = time.monotonic()

        try:
            # Phase 1: Account creation
            await self._run_account_creation(client)

            # Phase 2: Warmup transfers
            await self._run_transfer_phase(
                client,
                TBLoadPhase.WARMUP,
                self._config.warmup_seconds,
                rate_multiplier=0.1,
            )

            # Phase 3: Steady state transfers
            await self._run_transfer_phase(
                client,
                TBLoadPhase.STEADY_TRANSFERS,
                self._config.steady_seconds,
                rate_multiplier=1.0,
            )

            # Phase 4: Burst transfers
            await self._run_transfer_phase(
                client,
                TBLoadPhase.BURST_TRANSFERS,
                self._config.burst_seconds,
                rate_multiplier=self._config.burst_multiplier,
            )

            # Phase 5: Cooldown
            await self._run_transfer_phase(
                client,
                TBLoadPhase.COOLDOWN,
                self._config.cooldown_seconds,
                rate_multiplier=0.5,
            )

            self._stats.phase = TBLoadPhase.COMPLETED
            self._stats.elapsed_seconds = time.monotonic() - self._start_time

        finally:
            self._running = False

        return self._stats

    async def _run_account_creation(self, client: TigerBeetleClient) -> None:
        """Create accounts in batches."""
        self._stats.phase = TBLoadPhase.ACCOUNT_CREATION
        self._phase_start = time.monotonic()

        logger.info(f"Creating {self._config.num_accounts} accounts...")

        template = AccountTemplate(
            ledger=self._config.ledger_id,
            code=self._config.account_code,
            # No overdraft protection initially - accounts start with zero balance
            flags=0,
        )

        account_ids = [client.next_id() for _ in range(self._config.num_accounts)]

        # Create in batches
        for i in range(0, len(account_ids), self._config.accounts_per_batch):
            batch = account_ids[i : i + self._config.accounts_per_batch]
            created = await client.create_accounts(batch, template)
            self._accounts.extend(created)
            self._stats.accounts_created += len(created)
            self._stats.accounts_failed += len(batch) - len(created)

        # Designate hot accounts
        if len(self._accounts) >= self._config.hot_account_count:
            self._hot_accounts = self._accounts[: self._config.hot_account_count]
            self._cold_accounts = self._accounts[self._config.hot_account_count :]
        else:
            self._hot_accounts = self._accounts
            self._cold_accounts = []

        logger.info(
            f"Created {self._stats.accounts_created} accounts "
            f"({len(self._hot_accounts)} hot, {len(self._cold_accounts)} cold)"
        )

    async def _run_transfer_phase(
        self,
        client: TigerBeetleClient,
        phase: TBLoadPhase,
        duration_seconds: int,
        rate_multiplier: float,
    ) -> None:
        """Run a transfer generation phase."""
        self._stats.phase = phase
        self._phase_start = time.monotonic()
        target_rate = self._config.transfers_per_second * rate_multiplier

        logger.info(f"Starting {phase.value} phase ({duration_seconds}s, {target_rate:.0f}/s)")

        transfers_completed = 0
        phase_start = time.monotonic()
        last_second_start = phase_start

        while time.monotonic() - phase_start < duration_seconds:
            # Rate limiting
            current_time = time.monotonic()
            elapsed_in_second = current_time - last_second_start

            if elapsed_in_second >= 1.0:
                self._stats.current_rate = transfers_completed / (current_time - phase_start)
                transfers_completed = self._transfers_this_second
                self._transfers_this_second = 0
                last_second_start = current_time

            # Check if we should generate a transfer
            expected_transfers = int(elapsed_in_second * target_rate)
            if self._transfers_this_second < expected_transfers:
                await self._generate_transfer(client)
                self._transfers_this_second += 1
                transfers_completed += 1
            else:
                # Rate limit - sleep briefly
                await asyncio.sleep(0.001)

        self._stats.current_rate = transfers_completed / duration_seconds if duration_seconds else 0

    async def _generate_transfer(self, client: TigerBeetleClient) -> None:
        """Generate a single transfer or multi-leg transaction."""
        if len(self._accounts) < 2:
            return

        # Decide if multi-leg
        if self._rng.random() < self._config.multi_leg_probability:
            await self._generate_multi_leg_transfer(client)
        else:
            await self._generate_single_transfer(client)

    async def _generate_single_transfer(self, client: TigerBeetleClient) -> None:
        """Generate a single transfer between two accounts."""
        debit_account = self._select_account()
        credit_account = self._select_account(exclude=debit_account)

        if debit_account == credit_account:
            return

        amount = self._rng.randint(
            self._config.min_transfer_amount,
            self._config.max_transfer_amount,
        )

        # Occasionally attempt overdraft
        if self._rng.random() < self._config.overdraft_probability:
            amount = 10**15  # Very large amount
            self._stats.overdraft_attempts += 1

        template = TransferTemplate(
            ledger=self._config.ledger_id,
            code=1,
        )

        success = await client.create_transfer(debit_account, credit_account, amount, template)

        if success:
            self._stats.transfers_created += 1
            self._stats.total_amount_transferred += amount
        else:
            self._stats.transfers_failed += 1

    async def _generate_multi_leg_transfer(self, client: TigerBeetleClient) -> None:
        """Generate a multi-leg linked transfer chain."""
        num_legs = self._rng.randint(2, self._config.max_legs_per_transaction)

        if len(self._accounts) < num_legs + 1:
            return

        # Select accounts for the chain
        chain_accounts = self._rng.sample(self._accounts, num_legs + 1)

        # Create transfer chain
        transfers = []
        total_amount = 0
        for i in range(num_legs):
            amount = self._rng.randint(
                self._config.min_transfer_amount,
                self._config.max_transfer_amount,
            )
            transfers.append((chain_accounts[i], chain_accounts[i + 1], amount))
            total_amount += amount

        template = TransferTemplate(
            ledger=self._config.ledger_id,
            code=2,  # Different code for multi-leg
        )

        success = await client.create_linked_transfers(transfers, template)

        if success:
            self._stats.transfers_created += num_legs
            self._stats.multi_leg_transfers += 1
            self._stats.total_amount_transferred += total_amount
        else:
            self._stats.transfers_failed += num_legs

    def _select_account(self, exclude: int | None = None) -> int:
        """Select an account with hot key bias."""
        if self._rng.random() < self._config.hot_account_probability and self._hot_accounts:
            pool = [a for a in self._hot_accounts if a != exclude] or self._hot_accounts
        else:
            pool = (
                [a for a in self._cold_accounts if a != exclude]
                or self._cold_accounts
                or self._accounts
            )

        if not pool:
            pool = self._accounts

        return self._rng.choice(pool)


async def run_quick_tb_test(
    config: TBGeneratorConfig | None = None,
    tb_config: TigerBeetleConfig | None = None,
) -> TBGeneratorStats:
    """
    Run a quick TigerBeetle stress test.

    Args:
        config: Optional generator configuration
        tb_config: Optional TigerBeetle connection configuration

    Returns:
        Test statistics
    """
    config = config or TBGeneratorConfig(
        num_accounts=100,
        transfers_per_second=50,
        warmup_seconds=2,
        steady_seconds=10,
        burst_seconds=5,
        cooldown_seconds=2,
    )

    async with TigerBeetleClient.connect(tb_config) as client:
        generator = TigerBeetleLoadGenerator(config)
        return await generator.run(client)
