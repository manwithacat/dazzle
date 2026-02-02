"""
Data factory for PRA synthetic data generation.

Generates realistic test data for all PRA entities and stream schemas.

Uses the canonical Money type for all monetary values to ensure:
- JSON serialization compatibility (int-based amount_minor)
- No precision loss (exact integer arithmetic)
- Explicit currency handling
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from dazzle.core.ir.money import Money, to_money

from .hot_keys import HotKeySelector, create_pareto_selector


@dataclass
class PRADataFactory:
    """
    Generate synthetic data for PRA stress testing.

    Creates realistic payloads for:
    - INTENT streams (order placement, payment requests)
    - FACT streams (order placed/rejected, payment succeeded/failed)
    - OBSERVATION streams (gateway webhooks, HTTP requests)
    - DERIVATION streams (account balances, daily revenue)

    Example:
        factory = PRADataFactory(seed=42)

        # Generate order placement intent
        intent = factory.order_placement_requested()

        # Generate payment success fact
        fact = factory.payment_succeeded(order_id=intent["order_id"])
    """

    seed: int | None = None
    rejection_rate: float = 0.15  # 15% of orders rejected
    payment_failure_rate: float = 0.10  # 10% of payments fail
    payment_timeout_rate: float = 0.02  # 2% of payments timeout

    # Key selectors
    actor_selector: HotKeySelector = field(default_factory=lambda: create_pareto_selector(100))
    account_selector: HotKeySelector = field(default_factory=lambda: create_pareto_selector(200))

    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.seed is not None:
            self._rng.seed(self.seed)
            self.actor_selector.reset(self.seed)
            self.account_selector.reset(self.seed + 1)

    # =========================================================================
    # INTENT Payloads
    # =========================================================================

    def order_placement_requested(
        self,
        *,
        actor_id: UUID | None = None,
        account_id: UUID | None = None,
        use_v2: bool = False,
    ) -> dict[str, Any]:
        """
        Generate OrderPlacementRequested payload.

        Args:
            actor_id: Override actor ID (default: select from hot key pool)
            account_id: Override account ID
            use_v2: Use v2 schema with idempotency_key

        Returns:
            INTENT payload dict with Money-typed amount
        """
        actor = actor_id or self.actor_selector.select()
        account = account_id or self.account_selector.select()
        money = self._random_money(10, 1000)

        payload: dict[str, Any] = {
            "request_id": uuid4(),
            "actor_id": actor,
            "account_id": account,
            # Money fields use canonical representation
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "occurred_at": datetime.now(UTC),
        }

        if use_v2:
            payload["idempotency_key"] = self._random_idempotency_key()

        return payload

    def payment_requested(
        self,
        *,
        order_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Generate PaymentRequested payload.

        Args:
            order_id: Associated order ID

        Returns:
            INTENT payload dict with Money-typed amount
        """
        money = self._random_money(10, 1000)
        return {
            "request_id": uuid4(),
            "order_id": order_id or uuid4(),
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "gateway": self._random_gateway(),
            "occurred_at": datetime.now(UTC),
        }

    # =========================================================================
    # FACT Payloads
    # =========================================================================

    def order_placed(
        self,
        *,
        order_id: UUID | None = None,
        actor_id: UUID | None = None,
        account_id: UUID | None = None,
        causation_id: UUID | None = None,
        amount: Money | None = None,
    ) -> dict[str, Any]:
        """Generate OrderPlaced fact payload with Money-typed amount."""
        money = amount or self._random_money(10, 1000)
        return {
            "order_id": order_id or uuid4(),
            "actor_id": actor_id or self.actor_selector.select(),
            "account_id": account_id or self.account_selector.select(),
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def order_placement_rejected(
        self,
        *,
        order_id: UUID | None = None,
        actor_id: UUID | None = None,
        account_id: UUID | None = None,
        causation_id: UUID | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Generate OrderPlacementRejected fact payload."""
        return {
            "order_id": order_id or uuid4(),
            "actor_id": actor_id or self.actor_selector.select(),
            "account_id": account_id or self.account_selector.select(),
            "reason": reason or self._random_rejection_reason(),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def order_fulfilled(
        self,
        *,
        order_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Generate OrderFulfilled fact payload."""
        return {
            "order_id": order_id or uuid4(),
            "fulfilled_at": datetime.now(UTC),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def payment_succeeded(
        self,
        *,
        payment_id: UUID | None = None,
        order_id: UUID | None = None,
        causation_id: UUID | None = None,
        amount: Money | None = None,
    ) -> dict[str, Any]:
        """Generate PaymentSucceeded fact payload with Money-typed amount."""
        money = amount or self._random_money(10, 1000)
        return {
            "payment_id": payment_id or uuid4(),
            "order_id": order_id or uuid4(),
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "gateway_ref": self._random_gateway_ref(),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def payment_failed(
        self,
        *,
        payment_id: UUID | None = None,
        order_id: UUID | None = None,
        causation_id: UUID | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Generate PaymentFailed fact payload."""
        return {
            "payment_id": payment_id or uuid4(),
            "order_id": order_id or uuid4(),
            "reason": reason or self._random_payment_failure_reason(),
            "gateway_error_code": self._random_error_code(),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def payment_timed_out(
        self,
        *,
        payment_id: UUID | None = None,
        order_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Generate PaymentTimedOut fact payload."""
        return {
            "payment_id": payment_id or uuid4(),
            "order_id": order_id or uuid4(),
            "timeout_ms": self._rng.randint(30000, 60000),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def ledger_credited(
        self,
        *,
        account_id: UUID | None = None,
        amount: Money | None = None,
        reference_type: str = "payment",
        reference_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Generate LedgerCredited fact payload with Money-typed amount."""
        money = amount or self._random_money(10, 1000)
        return {
            "entry_id": uuid4(),
            "account_id": account_id or self.account_selector.select(),
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "reference_type": reference_type,
            "reference_id": reference_id or uuid4(),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    def ledger_debited(
        self,
        *,
        account_id: UUID | None = None,
        amount: Money | None = None,
        reference_type: str = "order",
        reference_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Generate LedgerDebited fact payload with Money-typed amount."""
        money = amount or self._random_money(10, 1000)
        return {
            "entry_id": uuid4(),
            "account_id": account_id or self.account_selector.select(),
            "amount_minor": money.amount_minor,
            "currency": money.currency,
            "reference_type": reference_type,
            "reference_id": reference_id or uuid4(),
            "causation_id": causation_id or uuid4(),
            "occurred_at": datetime.now(UTC),
        }

    # =========================================================================
    # OBSERVATION Payloads
    # =========================================================================

    def gateway_webhook_received(
        self,
        *,
        gateway_ref: str | None = None,
        use_v2: bool = False,
    ) -> dict[str, Any]:
        """Generate GatewayWebhookReceived observation payload."""
        payload = {
            "observation_id": uuid4(),
            "gateway_ref": gateway_ref or self._random_gateway_ref(),
            "webhook_type": self._random_webhook_type(),
            "received_at": datetime.now(UTC),
            "occurred_at": datetime.now(UTC),
        }

        if use_v2:
            payload["signature_valid"] = self._rng.random() > 0.01  # 99% valid
            payload["idempotency_key"] = self._random_idempotency_key()

        return payload

    def http_request_observed(
        self,
        *,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Generate HttpRequestObserved observation payload."""
        return {
            "observation_id": uuid4(),
            "trace_id": trace_id or uuid4(),
            "span_id": uuid4(),
            "http_method": self._random_http_method(),
            "request_path": self._random_request_path(),
            "response_status": self._random_status_code(),
            "duration_ms": self._rng.randint(1, 500),
            "occurred_at": datetime.now(UTC),
        }

    # =========================================================================
    # DERIVATION Payloads
    # =========================================================================

    def account_balance_calculated(
        self,
        *,
        account_id: UUID | None = None,
        balance: Money | None = None,
        as_of_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Generate AccountBalanceCalculated derivation payload with Money-typed balance."""
        money = balance or self._random_money(-1000, 10000)
        return {
            "calculation_id": uuid4(),
            "account_id": account_id or self.account_selector.select(),
            "balance_minor": money.amount_minor,
            "currency": money.currency,
            "as_of_sequence": as_of_sequence or self._rng.randint(1, 100000),
            "occurred_at": datetime.now(UTC),
            "processed_at": datetime.now(UTC),
        }

    def daily_revenue_aggregated(
        self,
        *,
        revenue_date: datetime | None = None,
        use_v2: bool = False,
    ) -> dict[str, Any]:
        """Generate DailyRevenueAggregated derivation payload with Money-typed revenue."""
        date = revenue_date or datetime.now(UTC) - timedelta(days=self._rng.randint(0, 30))
        order_count = self._rng.randint(100, 10000)
        total_revenue = self._random_money(1000, 100000, currency="GBP")

        payload: dict[str, Any] = {
            "calculation_id": uuid4(),
            "revenue_date": date.date(),
            "total_revenue_minor": total_revenue.amount_minor,
            "currency": total_revenue.currency,
            "order_count": order_count,
            "occurred_at": datetime.now(UTC),
            "processed_at": datetime.now(UTC),
        }

        if use_v2:
            # Average order value also in minor units
            avg_minor = total_revenue.amount_minor // order_count
            payload["average_order_value_minor"] = avg_minor

        return payload

    # =========================================================================
    # Outcome Selection
    # =========================================================================

    def should_reject_order(self) -> bool:
        """Determine if an order should be rejected based on rejection_rate."""
        return self._rng.random() < self.rejection_rate

    def get_payment_outcome(self) -> str:
        """
        Determine payment outcome based on configured rates.

        Returns:
            "success", "failure", or "timeout"
        """
        r = self._rng.random()
        if r < self.payment_timeout_rate:
            return "timeout"
        elif r < self.payment_timeout_rate + self.payment_failure_rate:
            return "failure"
        else:
            return "success"

    # =========================================================================
    # Random Value Generators
    # =========================================================================

    def _random_money(self, min_val: int, max_val: int, currency: str | None = None) -> Money:
        """
        Generate random Money value.

        Args:
            min_val: Minimum amount in major units (e.g., pounds)
            max_val: Maximum amount in major units
            currency: Currency code (default: random from GBP/USD/EUR)

        Returns:
            Money object with amount_minor in minor units
        """
        whole = self._rng.randint(min_val, max_val)
        cents = self._rng.randint(0, 99)
        amount = float(f"{whole}.{cents:02d}")
        curr = currency or self._random_currency()
        return to_money(amount, curr)

    def _random_amount(self, min_val: int, max_val: int) -> float:
        """
        Generate random decimal amount (returns float).

        DEPRECATED: Use _random_money() for event payloads.
        This method is kept for non-money numeric fields.
        """
        whole = self._rng.randint(min_val, max_val)
        cents = self._rng.randint(0, 99)
        return float(f"{whole}.{cents:02d}")

    def _random_currency(self) -> str:
        """Generate random currency code."""
        return self._rng.choice(["GBP", "USD", "EUR"])

    def _random_gateway(self) -> str:
        """Generate random payment gateway name."""
        return self._rng.choice(["stripe", "adyen", "worldpay", "paypal"])

    def _random_gateway_ref(self) -> str:
        """Generate random gateway reference."""
        prefix = self._rng.choice(["pi_", "ch_", "txn_", "pay_"])
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        suffix = "".join(self._rng.choices(chars, k=24))
        return f"{prefix}{suffix}"

    def _random_rejection_reason(self) -> str:
        """Generate random order rejection reason."""
        return self._rng.choice(
            [
                "Insufficient funds",
                "Account suspended",
                "Daily limit exceeded",
                "Invalid product",
                "Region not supported",
                "Duplicate order detected",
            ]
        )

    def _random_payment_failure_reason(self) -> str:
        """Generate random payment failure reason."""
        return self._rng.choice(
            [
                "Card declined",
                "Insufficient funds",
                "Invalid card number",
                "Expired card",
                "Fraud detected",
                "Gateway error",
            ]
        )

    def _random_error_code(self) -> str | None:
        """Generate random gateway error code."""
        return self._rng.choice(
            [
                "card_declined",
                "insufficient_funds",
                "invalid_card",
                "expired_card",
                "fraud_warning",
                "processing_error",
                None,
            ]
        )

    def _random_webhook_type(self) -> str:
        """Generate random webhook type."""
        return self._rng.choice(
            [
                "payment.succeeded",
                "payment.failed",
                "payment.pending",
                "refund.created",
                "dispute.created",
            ]
        )

    def _random_http_method(self) -> str:
        """Generate random HTTP method."""
        return self._rng.choice(["GET", "POST", "PUT", "DELETE"])

    def _random_request_path(self) -> str:
        """Generate random API request path."""
        paths = [
            "/api/orders",
            "/api/orders/{id}",
            "/api/payments",
            "/api/accounts/{id}",
            "/api/accounts/{id}/balance",
            "/health",
            "/metrics",
        ]
        return self._rng.choice(paths).format(id=uuid4())

    def _random_status_code(self) -> int:
        """Generate random HTTP status code."""
        # Weighted toward success
        codes = [200] * 80 + [201] * 10 + [400] * 3 + [404] * 3 + [500] * 2 + [503] * 2
        return self._rng.choice(codes)

    def _random_idempotency_key(self) -> str:
        """Generate random idempotency key."""
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(self._rng.choices(chars, k=32))
