"""
Unit tests for the ledger DSL parser mixin.

Tests parsing of ledger and transaction blocks for TigerBeetle
double-entry accounting constructs.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    AccountFlag,
    AccountType,
    ArithmeticOperator,
    FieldReference,
    LiteralValue,
    TransactionExecution,
    TransactionPriority,
    TransferFlag,
)
from dazzle.core.ir.computed import ArithmeticExpr


def _parse(dsl: str):  # type: ignore[return]
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


# ---------------------------------------------------------------------------
# Ledger tests
# ---------------------------------------------------------------------------


class TestLedgerBasic:
    """Tests for ledger construct parsing — required and common fields."""

    def test_minimal_ledger(self) -> None:
        """Parse a ledger with only the required fields."""
        dsl = """
module test_app
app test "Test"

ledger Revenue "Revenue":
  account_code: 4000
  ledger_id: 2
  account_type: revenue
  currency: USD
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        assert len(fragment.ledgers) == 1
        ledger = fragment.ledgers[0]
        assert ledger.name == "Revenue"
        assert ledger.label == "Revenue"
        assert ledger.account_code == 4000
        assert ledger.ledger_id == 2
        assert ledger.account_type == AccountType.REVENUE
        assert ledger.currency == "USD"

    def test_ledger_with_intent(self) -> None:
        """Parse a ledger that includes an intent description."""
        dsl = """
module test_app
app test "Test"

ledger CustomerWallet "Customer Wallet":
  intent: "Track customer prepaid balances"
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        ledger = fragment.ledgers[0]
        assert ledger.name == "CustomerWallet"
        assert ledger.label == "Customer Wallet"
        assert ledger.intent == "Track customer prepaid balances"

    def test_ledger_currency_uppercased(self) -> None:
        """Currency is normalised to uppercase regardless of DSL casing."""
        dsl = """
module test_app
app test "Test"

ledger Cash "Cash":
  account_code: 1100
  ledger_id: 1
  account_type: asset
  currency: gbp
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        assert fragment.ledgers[0].currency == "GBP"

    def test_ledger_without_optional_fields(self) -> None:
        """Optional fields (flags, sync, metadata_mapping) default to empty/None."""
        dsl = """
module test_app
app test "Test"

ledger SimpleAccount "Simple Account":
  account_code: 2000
  ledger_id: 3
  account_type: liability
  currency: EUR
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        ledger = fragment.ledgers[0]
        assert ledger.flags == []
        assert ledger.sync is None
        assert ledger.metadata_mapping == {}


class TestLedgerAccountTypes:
    """Verify every AccountType value is parsed correctly."""

    def _ledger_with_type(self, account_type: str) -> str:
        return f"""
module test_app
app test "Test"

ledger Acct "Acct":
  account_code: 9999
  ledger_id: 1
  account_type: {account_type}
  currency: USD
  idempotency_key: event.id
"""

    def test_account_type_asset(self) -> None:
        fragment = _parse(self._ledger_with_type("asset"))
        assert fragment.ledgers[0].account_type == AccountType.ASSET

    def test_account_type_liability(self) -> None:
        fragment = _parse(self._ledger_with_type("liability"))
        assert fragment.ledgers[0].account_type == AccountType.LIABILITY

    def test_account_type_equity(self) -> None:
        fragment = _parse(self._ledger_with_type("equity"))
        assert fragment.ledgers[0].account_type == AccountType.EQUITY

    def test_account_type_revenue(self) -> None:
        fragment = _parse(self._ledger_with_type("revenue"))
        assert fragment.ledgers[0].account_type == AccountType.REVENUE

    def test_account_type_expense(self) -> None:
        fragment = _parse(self._ledger_with_type("expense"))
        assert fragment.ledgers[0].account_type == AccountType.EXPENSE


class TestLedgerFlags:
    """Tests for account flag parsing."""

    def test_single_flag_debits_must_not_exceed_credits(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger Wallet "Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        ledger = fragment.ledgers[0]
        assert AccountFlag.DEBITS_MUST_NOT_EXCEED_CREDITS in ledger.flags
        assert ledger.has_overdraft_protection is True

    def test_single_flag_credits_must_not_exceed_debits(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger RevenueAcct "Revenue Acct":
  account_code: 4000
  ledger_id: 2
  account_type: revenue
  currency: USD
  flags: credits_must_not_exceed_debits
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        assert AccountFlag.CREDITS_MUST_NOT_EXCEED_DEBITS in fragment.ledgers[0].flags

    def test_flag_history(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger AuditLedger "Audit Ledger":
  account_code: 9000
  ledger_id: 5
  account_type: asset
  currency: USD
  flags: history
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        assert AccountFlag.HISTORY in fragment.ledgers[0].flags


class TestLedgerSyncTo:
    """Tests for sync_to parsing."""

    def test_sync_to_default_trigger(self) -> None:
        """sync_to defaults to AFTER_TRANSFER trigger."""
        dsl = """
module test_app
app test "Test"

ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  sync_to: Customer.balance_cache
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        ledger = fragment.ledgers[0]
        assert ledger.sync is not None
        assert ledger.sync.target_entity == "Customer"
        assert ledger.sync.target_field == "balance_cache"

    def test_sync_to_multiple_path_segments(self) -> None:
        """Dotted sync target splits into entity + field correctly."""
        dsl = """
module test_app
app test "Test"

ledger EscrowAccount "Escrow":
  account_code: 1500
  ledger_id: 1
  account_type: asset
  currency: USD
  sync_to: Escrow.cached_balance
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        sync = fragment.ledgers[0].sync
        assert sync is not None
        assert sync.target_entity == "Escrow"
        assert sync.target_field == "cached_balance"


class TestLedgerMetadataMapping:
    """Tests for metadata_mapping block parsing."""

    def test_metadata_mapping_with_ref(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  metadata_mapping:
    customer_id: ref Customer.id
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        mapping = fragment.ledgers[0].metadata_mapping
        assert "customer_id" in mapping
        assert mapping["customer_id"] == "ref Customer.id"

    def test_metadata_mapping_multiple_entries(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger TenantWallet "Tenant Wallet":
  account_code: 1002
  ledger_id: 1
  account_type: asset
  currency: USD
  metadata_mapping:
    customer_id: ref Customer.id
    tenant_id: ref Tenant.id
  idempotency_key: event.id
"""
        fragment = _parse(dsl)

        mapping = fragment.ledgers[0].metadata_mapping
        assert mapping["customer_id"] == "ref Customer.id"
        assert mapping["tenant_id"] == "ref Tenant.id"


class TestLedgerTenantScoped:
    """Tests for tenant_scoped field."""

    def test_tenant_scoped_true(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger TenantAccount "Tenant Account":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: USD
  tenant_scoped: true
  idempotency_key: event.id
"""
        fragment = _parse(dsl)
        assert fragment.ledgers[0].tenant_scoped is True

    def test_tenant_scoped_false(self) -> None:
        dsl = """
module test_app
app test "Test"

ledger GlobalAccount "Global Account":
  account_code: 5000
  ledger_id: 2
  account_type: equity
  currency: USD
  tenant_scoped: false
  idempotency_key: event.id
"""
        fragment = _parse(dsl)
        assert fragment.ledgers[0].tenant_scoped is False


# ---------------------------------------------------------------------------
# Transaction tests
# ---------------------------------------------------------------------------


class TestTransactionBasic:
    """Tests for transaction construct parsing — required and common fields."""

    def test_basic_transaction_single_transfer(self) -> None:
        """Parse a minimal transaction with a single transfer."""
        dsl = """
module test_app
app test "Test"

transaction RecordPayment "Record Payment":
  transfer revenue:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1

  idempotency_key: payment.id
"""
        fragment = _parse(dsl)

        assert len(fragment.transactions) == 1
        tx = fragment.transactions[0]
        assert tx.name == "RecordPayment"
        assert tx.label == "Record Payment"
        assert len(tx.transfers) == 1

        transfer = tx.transfers[0]
        assert transfer.name == "revenue"
        assert transfer.debit_ledger == "CustomerWallet"
        assert transfer.credit_ledger == "Revenue"
        assert transfer.code == 1
        # _parse_expression_string joins token values with spaces;
        # dotted paths are stored as "payment . id"
        assert "payment" in tx.idempotency_key
        assert "id" in tx.idempotency_key

    def test_transaction_with_intent(self) -> None:
        """Intent field is parsed and stored on the transaction."""
        dsl = """
module test_app
app test "Test"

transaction ChargeCustomer "Charge Customer":
  intent: "Charge customer for subscription"
  transfer main:
    debit: Wallet
    credit: Revenue
    amount: order.total
    code: 1

  idempotency_key: order.id
"""
        fragment = _parse(dsl)

        tx = fragment.transactions[0]
        assert tx.intent == "Charge customer for subscription"

    def test_transaction_multiple_transfers(self) -> None:
        """A transaction can contain multiple linked transfers."""
        dsl = """
module test_app
app test "Test"

transaction SplitPayment "Split Payment":
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
"""
        fragment = _parse(dsl)

        tx = fragment.transactions[0]
        assert len(tx.transfers) == 2
        assert tx.transfers[0].name == "revenue_portion"
        assert tx.transfers[1].name == "vat_portion"
        assert tx.is_multi_leg is True


class TestTransactionExecutionModes:
    """Verify both execution modes parse correctly."""

    def test_execution_sync_default(self) -> None:
        """Omitting the execution field defaults to SYNC mode."""
        dsl = """
module test_app
app test "Test"

transaction SyncTx "Sync Tx":
  transfer t:
    debit: A
    credit: B
    amount: 100
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)
        assert fragment.transactions[0].execution == TransactionExecution.SYNC

    def test_execution_async(self) -> None:
        dsl = """
module test_app
app test "Test"

transaction AsyncTx "Async Tx":
  execution: async
  transfer t:
    debit: A
    credit: B
    amount: 100
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)
        assert fragment.transactions[0].execution == TransactionExecution.ASYNC


class TestTransactionPriorities:
    """Verify all priority levels parse correctly."""

    def _tx_with_priority(self, priority: str) -> str:
        return f"""
module test_app
app test "Test"

transaction Tx "Tx":
  priority: {priority}
  transfer t:
    debit: A
    credit: B
    amount: 100
    code: 1
  idempotency_key: evt.id
"""

    def test_priority_critical(self) -> None:
        fragment = _parse(self._tx_with_priority("critical"))
        assert fragment.transactions[0].priority == TransactionPriority.CRITICAL

    def test_priority_high(self) -> None:
        fragment = _parse(self._tx_with_priority("high"))
        assert fragment.transactions[0].priority == TransactionPriority.HIGH

    def test_priority_normal(self) -> None:
        fragment = _parse(self._tx_with_priority("normal"))
        assert fragment.transactions[0].priority == TransactionPriority.NORMAL

    def test_priority_low(self) -> None:
        fragment = _parse(self._tx_with_priority("low"))
        assert fragment.transactions[0].priority == TransactionPriority.LOW


class TestTransactionTimeout:
    """Tests for the optional timeout field."""

    def test_custom_timeout(self) -> None:
        dsl = """
module test_app
app test "Test"

transaction SlowTx "Slow Tx":
  timeout: 10000
  transfer t:
    debit: A
    credit: B
    amount: 100
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)
        assert fragment.transactions[0].timeout_ms == 10000

    def test_default_timeout(self) -> None:
        """Timeout defaults to 5000 ms when not specified."""
        dsl = """
module test_app
app test "Test"

transaction QuickTx "Quick Tx":
  transfer t:
    debit: A
    credit: B
    amount: 100
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)
        assert fragment.transactions[0].timeout_ms == 5000


class TestAmountExpressions:
    """Tests for amount expression variants inside transfer blocks."""

    def test_amount_literal_integer(self) -> None:
        """Integer literal is parsed as LiteralValue with int value."""
        dsl = """
module test_app
app test "Test"

transaction FixedFee "Fixed Fee":
  transfer fee:
    debit: CustomerWallet
    credit: Fees
    amount: 100
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)

        amount = fragment.transactions[0].transfers[0].amount
        assert isinstance(amount, LiteralValue)
        assert amount.value == 100

    def test_amount_literal_float(self) -> None:
        """Float literal is parsed as LiteralValue with float value."""
        dsl = """
module test_app
app test "Test"

transaction FloatFee "Float Fee":
  transfer fee:
    debit: CustomerWallet
    credit: Fees
    amount: 9.99
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)

        amount = fragment.transactions[0].transfers[0].amount
        assert isinstance(amount, LiteralValue)
        assert amount.value == 9.99

    def test_amount_field_reference(self) -> None:
        """Dotted path is parsed as FieldReference with correct path segments."""
        dsl = """
module test_app
app test "Test"

transaction PaymentTx "Payment Tx":
  transfer main:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1
  idempotency_key: payment.id
"""
        fragment = _parse(dsl)

        amount = fragment.transactions[0].transfers[0].amount
        assert isinstance(amount, FieldReference)
        assert amount.path == ["payment", "amount"]

    def test_amount_arithmetic_multiply(self) -> None:
        """Arithmetic expression (multiplication) is parsed into ArithmeticExpr."""
        dsl = """
module test_app
app test "Test"

transaction SplitTx "Split Tx":
  transfer revenue:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount * 0.80
    code: 1
  idempotency_key: payment.id
"""
        fragment = _parse(dsl)

        amount = fragment.transactions[0].transfers[0].amount
        assert isinstance(amount, ArithmeticExpr)
        assert amount.operator == ArithmeticOperator.MULTIPLY

        assert isinstance(amount.left, FieldReference)
        assert amount.left.path == ["payment", "amount"]

        assert isinstance(amount.right, LiteralValue)
        assert amount.right.value == 0.80

    def test_amount_arithmetic_divide(self) -> None:
        """Division operator produces ArithmeticExpr with DIVIDE operator."""
        dsl = """
module test_app
app test "Test"

transaction HalfTx "Half Tx":
  transfer half:
    debit: Source
    credit: Dest
    amount: order.total / 2
    code: 1
  idempotency_key: order.id
"""
        fragment = _parse(dsl)

        amount = fragment.transactions[0].transfers[0].amount
        assert isinstance(amount, ArithmeticExpr)
        assert amount.operator == ArithmeticOperator.DIVIDE


class TestTransferFlags:
    """Tests for transfer flag parsing."""

    def test_transfer_flag_linked(self) -> None:
        dsl = """
module test_app
app test "Test"

transaction LinkedTx "Linked Tx":
  transfer t1:
    debit: A
    credit: B
    amount: 100
    code: 1
    flags: linked
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)

        transfer = fragment.transactions[0].transfers[0]
        assert TransferFlag.LINKED in transfer.flags
        assert transfer.is_linked is True

    def test_transfer_flag_pending(self) -> None:
        dsl = """
module test_app
app test "Test"

transaction PendingTx "Pending Tx":
  transfer reservation:
    debit: CustomerWallet
    credit: EscrowAccount
    amount: order.total
    code: 1
    flags: pending
  idempotency_key: order.id
"""
        fragment = _parse(dsl)

        transfer = fragment.transactions[0].transfers[0]
        assert TransferFlag.PENDING in transfer.flags
        assert transfer.is_pending is True

    def test_transfer_flag_balancing(self) -> None:
        dsl = """
module test_app
app test "Test"

transaction BalancingTx "Balancing Tx":
  transfer balance:
    debit: A
    credit: B
    amount: 0
    code: 1
    flags: balancing
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)

        transfer = fragment.transactions[0].transfers[0]
        assert TransferFlag.BALANCING in transfer.flags


class TestTransactionValidation:
    """Tests for validation rule parsing."""

    def test_validation_rules_parsed(self) -> None:
        """All validation rule expressions are captured as strings."""
        dsl = """
module test_app
app test "Test"

transaction SecureTx "Secure Tx":
  transfer main:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1

  idempotency_key: payment.id

  validation:
    - payment.amount > 0
    - payment.status == "authorized"
"""
        fragment = _parse(dsl)

        tx = fragment.transactions[0]
        assert len(tx.validation) == 2
        exprs = [rule.expression for rule in tx.validation]
        # _parse_expression_string joins token values with spaces, so dotted
        # paths arrive as "payment . amount > 0" — use substring checks.
        assert any("payment" in e and "amount" in e and "0" in e for e in exprs)
        assert any("payment" in e and "status" in e for e in exprs)

    def test_no_validation_rules(self) -> None:
        """Transaction without a validation block has an empty list."""
        dsl = """
module test_app
app test "Test"

transaction SimpleTx "Simple Tx":
  transfer t:
    debit: A
    credit: B
    amount: 50
    code: 1
  idempotency_key: evt.id
"""
        fragment = _parse(dsl)
        assert fragment.transactions[0].validation == []


class TestFullLedgerSpec:
    """Integration-style test parsing a complete ledger + transaction pair."""

    def test_full_spec_roundtrip(self) -> None:
        """Parse a comprehensive ledger+transaction spec and verify all fields."""
        dsl = """
module test_app
app test "Test"

ledger CustomerWallet "Customer Wallet":
  intent: "Track customer prepaid balances"
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache
  tenant_scoped: true
  metadata_mapping:
    customer_id: ref Customer.id

ledger Revenue "Revenue":
  account_code: 4001
  ledger_id: 2
  account_type: revenue
  currency: GBP

transaction RecordPayment "Record Payment":
  intent: "Charge customer for subscription with VAT"
  execution: async
  priority: high
  timeout: 10000

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
        fragment = _parse(dsl)

        # Ledgers
        assert len(fragment.ledgers) == 2
        wallet = fragment.ledgers[0]
        assert wallet.name == "CustomerWallet"
        assert wallet.account_type == AccountType.ASSET
        assert wallet.currency == "GBP"
        assert AccountFlag.DEBITS_MUST_NOT_EXCEED_CREDITS in wallet.flags
        assert wallet.sync is not None
        assert wallet.sync.target_entity == "Customer"
        assert wallet.sync.target_field == "balance_cache"
        assert wallet.tenant_scoped is True
        assert wallet.metadata_mapping["customer_id"] == "ref Customer.id"

        revenue = fragment.ledgers[1]
        assert revenue.name == "Revenue"
        assert revenue.account_type == AccountType.REVENUE

        # Transaction
        assert len(fragment.transactions) == 1
        tx = fragment.transactions[0]
        assert tx.name == "RecordPayment"
        assert tx.label == "Record Payment"
        assert tx.intent == "Charge customer for subscription with VAT"
        assert tx.execution == TransactionExecution.ASYNC
        assert tx.priority == TransactionPriority.HIGH
        assert tx.timeout_ms == 10000
        # _parse_expression_string joins tokens with spaces, so "payment.id"
        # is stored as "payment . id".
        assert "payment" in tx.idempotency_key
        assert "id" in tx.idempotency_key
        assert len(tx.validation) == 2

        # First transfer (arithmetic amount + linked flag)
        t1 = tx.transfers[0]
        assert t1.name == "revenue_portion"
        assert t1.debit_ledger == "CustomerWallet"
        assert t1.credit_ledger == "Revenue"
        assert t1.code == 1
        assert TransferFlag.LINKED in t1.flags
        assert isinstance(t1.amount, ArithmeticExpr)
        assert t1.amount.operator == ArithmeticOperator.MULTIPLY

        # Second transfer (arithmetic amount, no flags)
        t2 = tx.transfers[1]
        assert t2.name == "vat_portion"
        assert t2.credit_ledger == "VATLiability"
        assert t2.code == 2
        assert t2.flags == []
        assert isinstance(t2.amount, ArithmeticExpr)

        # Affected ledgers helper
        affected = tx.affected_ledgers
        assert "CustomerWallet" in affected
        assert "Revenue" in affected
        assert "VATLiability" in affected
