"""
TigerBeetle ledger types for DAZZLE IR.

This module contains types for double-entry accounting ledgers and
transactions that integrate with TigerBeetle.

DSL Syntax Examples:

    ledger CustomerWallet "Customer Wallet":
      intent: "Track customer prepaid balances"
      account_code: 1001
      ledger_id: 1
      account_type: asset
      currency: GBP
      flags: debits_must_not_exceed_credits
      sync_to: Customer.balance_cache

    transaction RecordPayment "Record Subscription Payment":
      intent: "Charge customer for monthly subscription with VAT"
      execution: async
      priority: high

      transfer revenue_portion:
        debit: CustomerWallet
        credit: Revenue
        amount: payment.amount * 0.80
        code: 1
        flags: linked

      transfer vat_portion:
        debit: CustomerWallet
        credit: VATLiability
        amount: payment.amount * 0.20
        code: 2

      idempotency_key: payment.id

      validation:
        - payment.amount > 0
        - payment.status == "authorized"
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .computed import ArithmeticExpr, FieldReference, LiteralValue


class AccountType(str, Enum):
    """
    Standard accounting account types following double-entry bookkeeping.

    The normal balance direction determines whether increases
    are recorded as debits or credits:
    - Asset, Expense: Normal debit balance (increases via debit)
    - Liability, Equity, Revenue: Normal credit balance (increases via credit)
    """

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class AccountFlag(str, Enum):
    """
    TigerBeetle account flags controlling balance constraints.

    These map directly to TigerBeetle's AccountFlags.
    """

    # Balance constraints
    DEBITS_MUST_NOT_EXCEED_CREDITS = "debits_must_not_exceed_credits"
    CREDITS_MUST_NOT_EXCEED_DEBITS = "credits_must_not_exceed_debits"

    # Account state
    LINKED = "linked"  # Account is linked to another for atomic creation
    HISTORY = "history"  # Maintain full history (vs. balance-only)


class TransferFlag(str, Enum):
    """
    TigerBeetle transfer flags controlling transfer behavior.

    These map directly to TigerBeetle's TransferFlags.
    """

    LINKED = "linked"  # Part of a linked chain (all succeed or fail)
    PENDING = "pending"  # Two-phase transfer: pending state
    POST_PENDING = "post_pending"  # Complete a pending transfer
    VOID_PENDING = "void_pending"  # Cancel a pending transfer
    BALANCING = "balancing"  # Auto-calculate amount to balance accounts


class TransactionPriority(str, Enum):
    """
    Transaction queue priority for Celery routing.

    Maps to separate queues for GDPR compliance and clear data separation.
    """

    CRITICAL = "critical"  # Reversals, corrections → celery.ledger.critical
    HIGH = "high"  # Customer-initiated transfers → celery.ledger.high
    NORMAL = "normal"  # Standard operations → celery.ledger.normal
    LOW = "low"  # Batch operations, reports → celery.ledger.low


class TransactionExecution(str, Enum):
    """
    Transaction execution mode.

    Controls whether the transaction runs synchronously in the request
    or is queued for async processing via Celery.
    """

    SYNC = "sync"  # Execute immediately in request
    ASYNC = "async"  # Queue for background processing


class SyncTrigger(str, Enum):
    """
    Trigger for TigerBeetle → PostgreSQL cache synchronization.
    """

    AFTER_TRANSFER = "after_transfer"  # Sync after each transfer
    SCHEDULED = "scheduled"  # Sync on schedule (requires cron)
    ON_DEMAND = "on_demand"  # Manual sync only


# Amount expression types (reusing computed.py patterns)
AmountExpr = FieldReference | ArithmeticExpr | LiteralValue


class TransferSpec(BaseModel):
    """
    Single transfer within a multi-leg transaction.

    A transfer moves value from a debit account to a credit account.
    Multiple transfers can be linked to form atomic multi-leg transactions.

    Example DSL:
        transfer revenue_portion:
          debit: CustomerWallet
          credit: Revenue
          amount: payment.amount * 0.80
          code: 1
          flags: linked
    """

    name: str = Field(description="Transfer name within transaction")
    debit_ledger: str = Field(description="Source ledger name (account debited)")
    credit_ledger: str = Field(description="Destination ledger name (account credited)")
    amount: AmountExpr = Field(description="Amount expression (field ref or arithmetic)")
    code: int = Field(ge=1, le=65535, description="Transfer code for categorization")
    flags: list[TransferFlag] = Field(
        default_factory=list,
        description="Transfer flags (linked, pending, etc.)",
    )
    pending_id: str | None = Field(
        default=None,
        description="Reference to pending transfer (for post/void)",
    )
    user_data: dict[str, str] = Field(
        default_factory=dict,
        description="Custom user data (maps to TigerBeetle user_data fields)",
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.debit_ledger} → {self.credit_ledger}"

    @property
    def is_linked(self) -> bool:
        """Check if this transfer is part of a linked chain."""
        return TransferFlag.LINKED in self.flags

    @property
    def is_pending(self) -> bool:
        """Check if this is a two-phase pending transfer."""
        return TransferFlag.PENDING in self.flags


class ValidationRule(BaseModel):
    """
    Validation rule for transaction preconditions.

    Rules are evaluated before executing transfers. If any rule fails,
    the transaction is rejected without executing any transfers.

    Example:
        - payment.amount > 0
        - payment.status == "authorized"
    """

    expression: str = Field(description="Validation expression as string")
    message: str | None = Field(
        default=None,
        description="Error message if validation fails",
    )

    model_config = ConfigDict(frozen=True)


class TransactionSpec(BaseModel):
    """
    Multi-leg financial transaction specification.

    Transactions group multiple transfers that must succeed or fail atomically.
    TigerBeetle guarantees ACID semantics for linked transfer chains.

    Example DSL:
        transaction RecordPayment "Record Subscription Payment":
          intent: "Charge customer for monthly subscription with VAT"
          execution: async
          priority: high

          transfer revenue_portion:
            debit: CustomerWallet
            credit: Revenue
            amount: payment.amount * 0.80
            code: 1
            flags: linked

          transfer vat_portion:
            debit: CustomerWallet
            credit: VATLiability
            amount: payment.amount * 0.20
            code: 2

          idempotency_key: payment.id

          validation:
            - payment.amount > 0
    """

    name: str = Field(description="Transaction name (identifier)")
    label: str | None = Field(default=None, description="Human-readable label")
    intent: str | None = Field(default=None, description="Business intent description")
    transfers: list[TransferSpec] = Field(
        default_factory=list,
        description="Ordered list of transfers in this transaction",
    )
    idempotency_key: str = Field(
        description="Expression for generating idempotency key",
    )
    validation: list[ValidationRule] = Field(
        default_factory=list,
        description="Precondition validation rules",
    )
    execution: TransactionExecution = Field(
        default=TransactionExecution.SYNC,
        description="Execution mode (sync or async)",
    )
    priority: TransactionPriority = Field(
        default=TransactionPriority.NORMAL,
        description="Queue priority for async execution",
    )
    timeout_ms: int = Field(
        default=5000,
        ge=100,
        le=300000,
        description="Transaction timeout in milliseconds",
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"transaction {self.name} ({len(self.transfers)} transfers)"

    @property
    def is_multi_leg(self) -> bool:
        """Check if this is a multi-leg transaction."""
        return len(self.transfers) > 1

    @property
    def affected_ledgers(self) -> set[str]:
        """Get all ledger names affected by this transaction."""
        ledgers: set[str] = set()
        for transfer in self.transfers:
            ledgers.add(transfer.debit_ledger)
            ledgers.add(transfer.credit_ledger)
        return ledgers


class LedgerSyncSpec(BaseModel):
    """
    Specification for syncing TigerBeetle state to PostgreSQL.

    Sync operations update cache fields in PostgreSQL entities
    with balance data from TigerBeetle accounts.

    Example DSL:
        sync_to: Customer.balance_cache
        trigger: after_transfer
        # OR
        trigger: scheduled "*/5 * * * *"
    """

    target_entity: str = Field(description="Entity name to sync to")
    target_field: str = Field(description="Field name to update with balance")
    trigger: SyncTrigger = Field(
        default=SyncTrigger.AFTER_TRANSFER,
        description="When to trigger sync",
    )
    cron: str | None = Field(
        default=None,
        description="Cron expression for scheduled sync",
    )
    match_field: str = Field(
        default="id",
        description="Entity field to match against account user_data",
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"sync → {self.target_entity}.{self.target_field}"


class LedgerSpec(BaseModel):
    """
    TigerBeetle ledger account template specification.

    A ledger defines a template for creating TigerBeetle accounts.
    Each entity instance linked to this ledger gets its own account.

    Example DSL:
        ledger CustomerWallet "Customer Wallet":
          intent: "Track customer prepaid balances"
          account_code: 1001
          ledger_id: 1
          account_type: asset
          currency: GBP
          flags: debits_must_not_exceed_credits
          sync_to: Customer.balance_cache
          metadata_mapping:
            customer_id: ref Customer.id
            tenant_id: ref Tenant.id
    """

    name: str = Field(description="Ledger name (identifier)")
    label: str | None = Field(default=None, description="Human-readable label")
    intent: str | None = Field(default=None, description="Business intent description")
    account_code: int = Field(
        ge=1,
        le=65535,
        description="TigerBeetle account code for categorization",
    )
    ledger_id: int = Field(
        ge=1,
        le=65535,
        description="TigerBeetle ledger ID (namespace)",
    )
    account_type: AccountType = Field(description="Accounting type (asset, liability, etc.)")
    currency: str = Field(
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 currency code (e.g., GBP, USD, EUR)",
    )
    flags: list[AccountFlag] = Field(
        default_factory=list,
        description="Account flags (balance constraints, etc.)",
    )
    sync: LedgerSyncSpec | None = Field(
        default=None,
        description="PostgreSQL sync configuration",
    )
    metadata_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of metadata fields to entity references",
    )
    tenant_scoped: bool = Field(
        default=True,
        description="Whether accounts are tenant-isolated",
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"ledger {self.name} ({self.account_type.value}, {self.currency})"

    @property
    def has_overdraft_protection(self) -> bool:
        """Check if this ledger prevents overdrafts."""
        return AccountFlag.DEBITS_MUST_NOT_EXCEED_CREDITS in self.flags

    @property
    def normal_balance_is_debit(self) -> bool:
        """Check if normal balance is debit (assets, expenses)."""
        return self.account_type in (AccountType.ASSET, AccountType.EXPENSE)

    def validate_debit(self, amount: int) -> bool:
        """
        Validate if a debit is valid for this account type.

        For assets/expenses: debit increases balance (normal)
        For liabilities/equity/revenue: debit decreases balance
        """
        if amount <= 0:
            return False
        return True

    def validate_credit(self, amount: int) -> bool:
        """
        Validate if a credit is valid for this account type.

        For liabilities/equity/revenue: credit increases balance (normal)
        For assets/expenses: credit decreases balance
        """
        if amount <= 0:
            return False
        return True


class LedgerAccountRef(BaseModel):
    """
    Reference to a ledger account field on an entity.

    Used to link an entity field to a TigerBeetle ledger,
    indicating that each entity instance has an account.

    Example DSL:
        entity Customer:
          wallet_account: ledger_account CustomerWallet
    """

    ledger_name: str = Field(description="Name of the ledger this references")
    create_on_entity_create: bool = Field(
        default=True,
        description="Auto-create account when entity is created",
    )

    model_config = ConfigDict(frozen=True)


# Update forward references
TransferSpec.model_rebuild()
TransactionSpec.model_rebuild()
