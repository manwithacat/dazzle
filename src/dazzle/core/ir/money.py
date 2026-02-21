"""
Money value object for DAZZLE IR and event payloads.

This module provides a canonical representation for monetary values that:
1. Is always JSON-serializable (int-based)
2. Has no precision loss (exact integer arithmetic)
3. Makes units explicit (amount_minor = pence/cents, not pounds/dollars)

The Money type is REQUIRED for all monetary fields in FACT and INTENT streams.
Using float or Decimal for money in event payloads is forbidden and will be
rejected by the linter.

Usage:
    # Creating Money values
    price = Money(currency="GBP", amount_minor=1999)  # £19.99

    # Converting from Decimal (in business logic)
    money = to_money(Decimal("19.99"), "GBP")  # Money(currency="GBP", amount_minor=1999)

    # Converting to Decimal (for calculations)
    amount = from_money(money)  # Decimal("19.99")

    # JSON serialization (automatic, just use dict())
    payload = money.model_dump()  # {"currency": "GBP", "amount_minor": 1999}

See: dev_docs/architecture/event_first/money_representation.md
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# ISO 4217 Currency Scales
# =============================================================================
# Number of decimal places for each currency.
# Most currencies use 2 (cents/pence), but some differ.

CURRENCY_SCALES: dict[str, int] = {
    # Major currencies with 2 decimal places
    "GBP": 2,  # British Pound (pence)
    "USD": 2,  # US Dollar (cents)
    "EUR": 2,  # Euro (cents)
    "AUD": 2,  # Australian Dollar
    "CAD": 2,  # Canadian Dollar
    "CHF": 2,  # Swiss Franc
    "CNY": 2,  # Chinese Yuan
    "INR": 2,  # Indian Rupee
    "NZD": 2,  # New Zealand Dollar
    "SGD": 2,  # Singapore Dollar
    "HKD": 2,  # Hong Kong Dollar
    "SEK": 2,  # Swedish Krona
    "NOK": 2,  # Norwegian Krone
    "DKK": 2,  # Danish Krone
    "ZAR": 2,  # South African Rand
    "MXN": 2,  # Mexican Peso
    "BRL": 2,  # Brazilian Real
    # Zero decimal places
    "JPY": 0,  # Japanese Yen (no minor unit)
    "KRW": 0,  # South Korean Won
    "VND": 0,  # Vietnamese Dong
    "CLP": 0,  # Chilean Peso
    "ISK": 0,  # Icelandic Króna
    # Three decimal places
    "BHD": 3,  # Bahraini Dinar
    "KWD": 3,  # Kuwaiti Dinar
    "OMR": 3,  # Omani Rial
    "TND": 3,  # Tunisian Dinar
    "JOD": 3,  # Jordanian Dinar
    "IQD": 3,  # Iraqi Dinar
    "LYD": 3,  # Libyan Dinar
}

# Default scale for unknown currencies
DEFAULT_CURRENCY_SCALE = 2


def get_currency_scale(currency: str) -> int:
    """
    Get the decimal scale for a currency.

    Args:
        currency: ISO 4217 currency code (e.g., "GBP", "USD", "JPY")

    Returns:
        Number of decimal places (e.g., 2 for GBP, 0 for JPY, 3 for BHD)
    """
    return CURRENCY_SCALES.get(currency.upper(), DEFAULT_CURRENCY_SCALE)


# =============================================================================
# Money Value Object
# =============================================================================


class Money(BaseModel):
    """
    Canonical money representation for event payloads.

    This is the REQUIRED format for all monetary values in FACT and INTENT streams.
    It uses integer minor units (pence/cents) to avoid floating-point precision issues.

    Attributes:
        currency: ISO 4217 currency code (e.g., "GBP", "USD", "EUR")
        amount_minor: Amount in minor units (signed integer)
                     For GBP: 1999 = £19.99
                     For JPY: 1999 = ¥1999 (no minor unit)
                     For BHD: 1999 = 1.999 BHD (3 decimal places)

    Example:
        # £19.99
        Money(currency="GBP", amount_minor=1999)

        # -$5.00 (refund)
        Money(currency="USD", amount_minor=-500)

        # ¥1000 (no minor units)
        Money(currency="JPY", amount_minor=1000)
    """

    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code",
    )
    amount_minor: int = Field(
        ...,
        description="Amount in minor currency units (pence, cents, etc.)",
    )

    model_config = ConfigDict(frozen=True)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Ensure currency code is uppercase."""
        return v.upper()

    @property
    def scale(self) -> int:
        """Get the decimal scale for this currency."""
        return get_currency_scale(self.currency)

    def to_decimal(self) -> Decimal:
        """
        Convert to Decimal for calculations.

        Returns:
            Decimal representation (e.g., Decimal("19.99") for 1999 GBP)
        """
        return from_money(self)

    def to_float(self) -> float:
        """
        Convert to float for display (NOT for calculations).

        Warning: Use to_decimal() for any arithmetic operations.

        Returns:
            Float representation (e.g., 19.99 for 1999 GBP)
        """
        return float(self.to_decimal())

    def __str__(self) -> str:
        """Human-readable string representation."""
        decimal_amount = self.to_decimal()
        return f"{self.currency} {decimal_amount:,.{self.scale}f}"

    def __repr__(self) -> str:
        return f"Money(currency={self.currency!r}, amount_minor={self.amount_minor})"


# =============================================================================
# Money with Optional Custom Scale
# =============================================================================


class MoneyWithScale(Money):
    """
    Money with explicit scale (for non-standard currency representations).

    Only use this when you need to override the ISO 4217 default scale.
    For standard currencies, use Money instead.

    Example:
        # Custom token with 8 decimal places
        MoneyWithScale(currency="BTC", amount_minor=100000000, scale_override=8)  # 1 BTC
    """

    scale_override: int | None = Field(
        default=None,
        ge=0,
        le=18,
        description="Override ISO 4217 scale (use sparingly)",
    )

    @property
    def scale(self) -> int:
        """Get the decimal scale, using override if set."""
        if self.scale_override is not None:
            return self.scale_override
        return get_currency_scale(self.currency)


# =============================================================================
# Conversion Functions
# =============================================================================


def to_money(amount: Decimal | float | int | str, currency: str) -> Money:
    """
    Convert a decimal/float/int amount to Money.

    This is the boundary function for converting business logic values
    (which may use Decimal) to the canonical Money representation for events.

    Args:
        amount: Amount in major units (e.g., 19.99 for £19.99)
        currency: ISO 4217 currency code

    Returns:
        Money object with amount in minor units

    Example:
        to_money(Decimal("19.99"), "GBP")  # Money(currency="GBP", amount_minor=1999)
        to_money(19.99, "GBP")             # Money(currency="GBP", amount_minor=1999)
        to_money(1000, "JPY")              # Money(currency="JPY", amount_minor=1000)
    """
    # Convert to Decimal for precise arithmetic
    if isinstance(amount, float):
        # Round to currency scale to avoid float precision issues
        scale = get_currency_scale(currency)
        amount = Decimal(str(round(amount, scale)))
    elif isinstance(amount, int):
        amount = Decimal(amount)
    elif isinstance(amount, str):
        amount = Decimal(amount)

    scale = get_currency_scale(currency)
    minor_units = int(amount * (10**scale))

    return Money(currency=currency.upper(), amount_minor=minor_units)


def from_money(money: Money) -> Decimal:
    """
    Convert Money to Decimal for calculations.

    This is the boundary function for converting canonical Money values
    back to Decimal for business logic (VAT calculations, etc.).

    Args:
        money: Money object

    Returns:
        Decimal amount in major units

    Example:
        from_money(Money(currency="GBP", amount_minor=1999))  # Decimal("19.99")
        from_money(Money(currency="JPY", amount_minor=1000))  # Decimal("1000")
    """
    scale = money.scale
    return Decimal(money.amount_minor) / Decimal(10**scale)


def money_from_dict(data: dict[str, Any]) -> Money:
    """
    Create Money from a dictionary (e.g., from JSON payload).

    Args:
        data: Dictionary with 'currency' and 'amount_minor' keys

    Returns:
        Money object

    Example:
        money_from_dict({"currency": "GBP", "amount_minor": 1999})
    """
    return Money(
        currency=data["currency"],
        amount_minor=data["amount_minor"],
    )


# =============================================================================
# Field Name Patterns for Lint Detection
# =============================================================================

# Field names that suggest monetary values
# Used by the linter to detect float/Decimal money fields in FACT streams
MONEY_FIELD_PATTERNS: frozenset[str] = frozenset(
    {
        "amount",
        "price",
        "cost",
        "total",
        "subtotal",
        "tax",
        "vat",
        "discount",
        "fee",
        "charge",
        "payment",
        "balance",
        "credit",
        "debit",
        "revenue",
        "profit",
        "margin",
        "salary",
        "wage",
        "bonus",
        "commission",
        "refund",
        "deposit",
        "withdrawal",
    }
)


def is_money_field_name(field_name: str) -> bool:
    """
    Check if a field name suggests it contains monetary values.

    Used by the linter to detect potential float/Decimal money fields.
    Excludes fields that contain non-monetary qualifiers like 'percentage',
    'pct', 'ratio', 'share', 'rate', 'factor', 'score', 'count', or 'grade'.

    Args:
        field_name: Field name to check

    Returns:
        True if the field name matches money-like patterns
    """
    name_lower = field_name.lower()

    # Exclude fields that are clearly not monetary despite containing
    # money-like substrings (e.g., "profit_share_percentage", "balance_score")
    non_monetary = (
        "percentage",
        "pct",
        "ratio",
        "share",
        "rate",
        "factor",
        "score",
        "count",
        "grade",
        "level",
    )
    if any(q in name_lower for q in non_monetary):
        return False

    # Direct match
    if name_lower in MONEY_FIELD_PATTERNS:
        return True

    # Suffix match (e.g., "order_amount", "total_price")
    for pattern in MONEY_FIELD_PATTERNS:
        if name_lower.endswith(f"_{pattern}") or name_lower.endswith(pattern):
            return True

    # Prefix match (e.g., "amount_due", "price_per_unit")
    for pattern in MONEY_FIELD_PATTERNS:
        if name_lower.startswith(f"{pattern}_") or name_lower.startswith(pattern):
            return True

    return False


__all__ = [
    # Constants
    "CURRENCY_SCALES",
    "DEFAULT_CURRENCY_SCALE",
    "MONEY_FIELD_PATTERNS",
    # Functions
    "get_currency_scale",
    "to_money",
    "from_money",
    "money_from_dict",
    "is_money_field_name",
    # Classes
    "Money",
    "MoneyWithScale",
]
