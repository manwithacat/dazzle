"""
Hot key selector for partition skew simulation.

Implements weighted key selection to simulate hot partitions where
a small percentage of keys receive a disproportionate amount of traffic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TypeVar
from uuid import UUID, uuid4

T = TypeVar("T")


@dataclass
class HotKeySelector:
    """
    Select keys with configurable hot partition skew.

    Simulates real-world scenarios where a small percentage of accounts
    or entities generate a large percentage of traffic.

    Example:
        # 10% of keys get 80% of traffic (Pareto-ish)
        selector = HotKeySelector(
            hot_key_count=10,
            hot_key_probability=0.8,
            total_keys=100,
        )

        # Get a key (will be hot ~80% of the time)
        key = selector.select()
    """

    hot_key_count: int = 10
    hot_key_probability: float = 0.8
    total_keys: int = 100
    seed: int | None = None

    _hot_keys: list[UUID] = field(default_factory=list)
    _cold_keys: list[UUID] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random)
    _initialized: bool = field(default=False)

    def __post_init__(self) -> None:
        """Initialize key pools."""
        if self.seed is not None:
            self._rng.seed(self.seed)
        self._initialize_keys()

    def _initialize_keys(self) -> None:
        """Generate hot and cold key pools."""
        if self._initialized:
            return

        # Generate hot keys
        self._hot_keys = [uuid4() for _ in range(self.hot_key_count)]

        # Generate cold keys (rest of total)
        cold_count = max(0, self.total_keys - self.hot_key_count)
        self._cold_keys = [uuid4() for _ in range(cold_count)]

        self._initialized = True

    def select(self) -> UUID:
        """
        Select a key with hot partition bias.

        Returns:
            UUID key (hot keys selected with hot_key_probability)
        """
        if not self._initialized:
            self._initialize_keys()

        if self._rng.random() < self.hot_key_probability:
            # Select from hot keys
            return self._rng.choice(self._hot_keys)
        elif self._cold_keys:
            # Select from cold keys
            return self._rng.choice(self._cold_keys)
        else:
            # Fallback to hot keys if no cold keys
            return self._rng.choice(self._hot_keys)

    def select_hot(self) -> UUID:
        """Select specifically from hot keys."""
        if not self._initialized:
            self._initialize_keys()
        return self._rng.choice(self._hot_keys)

    def select_cold(self) -> UUID:
        """Select specifically from cold keys."""
        if not self._initialized:
            self._initialize_keys()
        if self._cold_keys:
            return self._rng.choice(self._cold_keys)
        return self._rng.choice(self._hot_keys)

    def get_hot_keys(self) -> list[UUID]:
        """Get all hot keys."""
        if not self._initialized:
            self._initialize_keys()
        return list(self._hot_keys)

    def get_cold_keys(self) -> list[UUID]:
        """Get all cold keys."""
        if not self._initialized:
            self._initialize_keys()
        return list(self._cold_keys)

    def is_hot(self, key: UUID) -> bool:
        """Check if a key is in the hot set."""
        return key in self._hot_keys

    def reset(self, seed: int | None = None) -> None:
        """Reset and regenerate keys."""
        if seed is not None:
            self.seed = seed
            self._rng.seed(seed)
        self._initialized = False
        self._hot_keys.clear()
        self._cold_keys.clear()
        self._initialize_keys()


@dataclass
class WeightedKeySelector:
    """
    Select from a weighted distribution of keys.

    More flexible than HotKeySelector for custom distributions.

    Example:
        selector = WeightedKeySelector()
        selector.add_key(uuid4(), weight=100)  # Very hot
        selector.add_key(uuid4(), weight=10)   # Warm
        selector.add_key(uuid4(), weight=1)    # Cold

        key = selector.select()
    """

    seed: int | None = None
    _keys: list[tuple[UUID, float]] = field(default_factory=list)
    _total_weight: float = field(default=0.0)
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.seed is not None:
            self._rng.seed(self.seed)

    def add_key(self, key: UUID, weight: float = 1.0) -> None:
        """Add a key with weight."""
        self._keys.append((key, weight))
        self._total_weight += weight

    def add_keys(self, keys: list[UUID], weight: float = 1.0) -> None:
        """Add multiple keys with same weight."""
        for key in keys:
            self.add_key(key, weight)

    def select(self) -> UUID:
        """Select a key based on weights."""
        if not self._keys:
            return uuid4()

        r = self._rng.random() * self._total_weight
        cumulative = 0.0

        for key, weight in self._keys:
            cumulative += weight
            if r <= cumulative:
                return key

        # Fallback to last key
        return self._keys[-1][0]

    def clear(self) -> None:
        """Clear all keys."""
        self._keys.clear()
        self._total_weight = 0.0


def create_pareto_selector(
    total_keys: int = 100,
    pareto_ratio: float = 0.2,
    traffic_share: float = 0.8,
    seed: int | None = None,
) -> HotKeySelector:
    """
    Create a selector following Pareto-like distribution.

    The classic 80/20 rule: 20% of keys get 80% of traffic.

    Args:
        total_keys: Total number of keys
        pareto_ratio: Fraction of keys that are "hot" (default 0.2 = 20%)
        traffic_share: Fraction of traffic to hot keys (default 0.8 = 80%)
        seed: Random seed for reproducibility

    Returns:
        Configured HotKeySelector
    """
    hot_count = max(1, int(total_keys * pareto_ratio))

    return HotKeySelector(
        hot_key_count=hot_count,
        hot_key_probability=traffic_share,
        total_keys=total_keys,
        seed=seed,
    )


def create_extreme_skew_selector(
    total_keys: int = 100,
    seed: int | None = None,
) -> HotKeySelector:
    """
    Create a selector with extreme skew (1% keys get 90% traffic).

    Used for stress testing hot partition handling.

    Args:
        total_keys: Total number of keys
        seed: Random seed for reproducibility

    Returns:
        Configured HotKeySelector
    """
    hot_count = max(1, int(total_keys * 0.01))

    return HotKeySelector(
        hot_key_count=hot_count,
        hot_key_probability=0.9,
        total_keys=total_keys,
        seed=seed,
    )
