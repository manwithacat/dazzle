"""
TigerBeetle client wrapper for PRA stress testing.

Provides connection management, account creation, and transfer operations
with metrics collection and error handling.

Requires: pip install dazzle[tigerbeetle]
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_dnr_back.metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Lazy import TigerBeetle to allow running without it installed
_tb_module: ModuleType | None = None


def _get_tb() -> ModuleType:
    """Lazy import TigerBeetle module."""
    global _tb_module
    if _tb_module is None:
        try:
            import tigerbeetle as tb

            _tb_module = tb
        except ImportError as e:
            raise ImportError(
                "TigerBeetle client not installed. Install with: pip install dazzle[tigerbeetle]"
            ) from e
    return _tb_module


@dataclass
class TigerBeetleConfig:
    """Configuration for TigerBeetle connection."""

    cluster_id: int = 0
    addresses: list[str] = field(default_factory=lambda: ["127.0.0.1:3000"])
    max_concurrency: int = 32
    connect_timeout_ms: int = 5000


@dataclass
class AccountTemplate:
    """Template for creating TigerBeetle accounts."""

    ledger: int = 1
    code: int = 1000
    flags: int = 0  # AccountFlags value
    user_data_128: int = 0
    user_data_64: int = 0
    user_data_32: int = 0


@dataclass
class TransferTemplate:
    """Template for creating TigerBeetle transfers."""

    ledger: int = 1
    code: int = 1
    flags: int = 0  # TransferFlags value
    amount: int = 1000  # Default amount in minor units
    timeout: int = 0  # 0 = no timeout (for pending transfers)


@dataclass
class TigerBeetleStats:
    """Statistics for TigerBeetle operations."""

    accounts_created: int = 0
    accounts_failed: int = 0
    transfers_created: int = 0
    transfers_failed: int = 0
    lookups_performed: int = 0
    total_latency_ms: float = 0.0
    operation_count: int = 0

    @property
    def avg_latency_ms(self) -> float:
        """Average operation latency."""
        if self.operation_count == 0:
            return 0.0
        return self.total_latency_ms / self.operation_count


class TigerBeetleClient:
    """
    Async wrapper for TigerBeetle client with metrics collection.

    Provides:
    - Connection management with automatic reconnection
    - Account creation with batch support
    - Transfer execution with linked chain support
    - Balance lookups and queries
    - Latency and error metrics

    Example:
        async with TigerBeetleClient.connect() as client:
            await client.create_accounts([1, 2, 3])
            await client.transfer(1, 2, 1000)
    """

    def __init__(
        self,
        config: TigerBeetleConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        """
        Initialize client (does not connect yet).

        Args:
            config: TigerBeetle connection configuration
            metrics: Optional metrics collector for latency tracking
        """
        self._config = config or TigerBeetleConfig()
        self._metrics = metrics
        self._client = None
        self._stats = TigerBeetleStats()
        self._connected = False
        self._id_counter = 0

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        config: TigerBeetleConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> AsyncIterator[TigerBeetleClient]:
        """
        Context manager for connecting to TigerBeetle.

        Args:
            config: Optional configuration override
            metrics: Optional metrics collector

        Yields:
            Connected TigerBeetleClient
        """
        client = cls(config, metrics)
        try:
            await client._connect()
            yield client
        finally:
            await client._disconnect()

    async def _connect(self) -> None:
        """Establish connection to TigerBeetle cluster."""
        tb = _get_tb()

        # Join addresses into comma-separated string for replica_addresses
        replica_addresses = ",".join(self._config.addresses)

        logger.info(
            f"Connecting to TigerBeetle cluster {self._config.cluster_id} at {replica_addresses}"
        )

        try:
            self._client = tb.ClientAsync(
                cluster_id=self._config.cluster_id,
                replica_addresses=replica_addresses,
            )
            self._connected = True
            logger.info("TigerBeetle connection established")
        except Exception as e:
            logger.error(f"Failed to connect to TigerBeetle: {e}")
            raise

    async def _disconnect(self) -> None:
        """Close connection to TigerBeetle."""
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
            logger.info("TigerBeetle connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._client is not None

    @property
    def stats(self) -> TigerBeetleStats:
        """Get current statistics."""
        return self._stats

    def next_id(self) -> int:
        """Generate next unique ID using TigerBeetle's id() function."""
        tb = _get_tb()
        return int(tb.id())

    def _record_latency(self, operation: str, latency_ms: float) -> None:
        """Record operation latency in metrics."""
        self._stats.total_latency_ms += latency_ms
        self._stats.operation_count += 1

        if self._metrics:
            self._metrics.record_latency(f"tigerbeetle.{operation}", latency_ms)

    async def create_accounts(
        self,
        account_ids: list[int],
        template: AccountTemplate | None = None,
    ) -> list[int]:
        """
        Create accounts with given IDs.

        Args:
            account_ids: List of account IDs to create
            template: Optional template for account settings

        Returns:
            List of successfully created account IDs
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        tb = _get_tb()
        template = template or AccountTemplate()

        accounts = [
            tb.Account(
                id=acc_id,
                ledger=template.ledger,
                code=template.code,
                flags=template.flags,
                user_data_128=template.user_data_128,
                user_data_64=template.user_data_64,
                user_data_32=template.user_data_32,
            )
            for acc_id in account_ids
        ]

        start = time.perf_counter()
        try:
            results = await self._client.create_accounts(accounts)
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_accounts", latency_ms)

            # Check for failures
            failed_ids = {r.index for r in results}
            succeeded = [aid for i, aid in enumerate(account_ids) if i not in failed_ids]

            self._stats.accounts_created += len(succeeded)
            self._stats.accounts_failed += len(failed_ids)

            if failed_ids:
                logger.warning(
                    f"Failed to create {len(failed_ids)} accounts: "
                    f"{[results[i].result for i in range(len(results))]}"
                )

            return succeeded

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_accounts", latency_ms)
            self._stats.accounts_failed += len(account_ids)
            logger.error(f"Error creating accounts: {e}")
            raise

    async def create_transfer(
        self,
        debit_account_id: int,
        credit_account_id: int,
        amount: int,
        template: TransferTemplate | None = None,
        transfer_id: int | None = None,
    ) -> bool:
        """
        Create a single transfer between accounts.

        Args:
            debit_account_id: Source account (debited)
            credit_account_id: Destination account (credited)
            amount: Amount in minor units
            template: Optional template for transfer settings
            transfer_id: Optional explicit transfer ID

        Returns:
            True if transfer succeeded
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        tb = _get_tb()
        template = template or TransferTemplate()
        tid = transfer_id or self.next_id()

        transfer = tb.Transfer(
            id=tid,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            ledger=template.ledger,
            code=template.code,
            flags=template.flags,
            timeout=template.timeout,
        )

        start = time.perf_counter()
        try:
            results = await self._client.create_transfers([transfer])
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_transfer", latency_ms)

            if results:
                self._stats.transfers_failed += 1
                logger.warning(f"Transfer failed: {results[0].result}")
                return False

            self._stats.transfers_created += 1
            return True

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_transfer", latency_ms)
            self._stats.transfers_failed += 1
            logger.error(f"Error creating transfer: {e}")
            raise

    async def create_linked_transfers(
        self,
        transfers: list[tuple[int, int, int]],  # (debit, credit, amount)
        template: TransferTemplate | None = None,
    ) -> bool:
        """
        Create a chain of linked transfers (all succeed or all fail).

        Args:
            transfers: List of (debit_account_id, credit_account_id, amount) tuples
            template: Optional template for transfer settings

        Returns:
            True if all transfers succeeded
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        if not transfers:
            return True

        tb = _get_tb()
        template = template or TransferTemplate()

        tb_transfers = []
        for i, (debit, credit, amount) in enumerate(transfers):
            # Link all but the last transfer
            flags = tb.TransferFlags.LINKED if i < len(transfers) - 1 else 0
            if template.flags:
                flags |= template.flags

            tb_transfers.append(
                tb.Transfer(
                    id=self.next_id(),
                    debit_account_id=debit,
                    credit_account_id=credit,
                    amount=amount,
                    ledger=template.ledger,
                    code=template.code,
                    flags=flags,
                    timeout=template.timeout,
                )
            )

        start = time.perf_counter()
        try:
            results = await self._client.create_transfers(tb_transfers)
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_linked_transfers", latency_ms)

            if results:
                self._stats.transfers_failed += len(transfers)
                logger.warning(f"Linked transfers failed: {[r.result for r in results]}")
                return False

            self._stats.transfers_created += len(transfers)
            return True

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("create_linked_transfers", latency_ms)
            self._stats.transfers_failed += len(transfers)
            logger.error(f"Error creating linked transfers: {e}")
            raise

    async def lookup_accounts(self, account_ids: list[int]) -> list[dict[str, Any]]:
        """
        Look up account balances.

        Args:
            account_ids: Account IDs to look up

        Returns:
            List of account data dictionaries
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        start = time.perf_counter()
        try:
            accounts = await self._client.lookup_accounts(account_ids)
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("lookup_accounts", latency_ms)
            self._stats.lookups_performed += 1

            return [
                {
                    "id": acc.id,
                    "ledger": acc.ledger,
                    "code": acc.code,
                    "debits_pending": acc.debits_pending,
                    "debits_posted": acc.debits_posted,
                    "credits_pending": acc.credits_pending,
                    "credits_posted": acc.credits_posted,
                    "balance": acc.credits_posted - acc.debits_posted,
                }
                for acc in accounts
            ]

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_latency("lookup_accounts", latency_ms)
            logger.error(f"Error looking up accounts: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Perform a health check by looking up a non-existent account.

        Returns:
            True if TigerBeetle is responsive
        """
        if not self._client:
            return False

        try:
            # Lookup a non-existent account - should return empty list
            await self._client.lookup_accounts([0])
            return True
        except Exception as e:
            logger.error(f"TigerBeetle health check failed: {e}")
            return False


async def check_tigerbeetle_available(
    config: TigerBeetleConfig | None = None,
    timeout_seconds: float = 5.0,
) -> bool:
    """
    Check if TigerBeetle is available and connectable.

    Args:
        config: Optional configuration override
        timeout_seconds: Timeout for connection attempt (default 5s)

    Returns:
        True if TigerBeetle is available
    """
    import asyncio

    try:
        _get_tb()
    except ImportError:
        logger.warning("TigerBeetle client not installed")
        return False

    config = config or TigerBeetleConfig()

    try:
        async with asyncio.timeout(timeout_seconds):
            async with TigerBeetleClient.connect(config) as client:
                return await client.health_check()
    except TimeoutError:
        logger.warning("TigerBeetle connection timed out")
        return False
    except Exception as e:
        logger.warning(f"TigerBeetle not available: {e}")
        return False
