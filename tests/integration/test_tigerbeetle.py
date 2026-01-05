"""
TigerBeetle integration tests.

These tests require a running TigerBeetle instance. They verify:
- Client connection and health
- Account creation
- Transfer operations
- Ledger balances

Run with: pytest tests/integration/test_tigerbeetle.py -v -m tigerbeetle

Requires:
- TigerBeetle running at localhost:3000 (or TIGERBEETLE_ADDRESSES env var)
- pip install dazzle[tigerbeetle]
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


# Skip all tests if TigerBeetle is not available
pytestmark = [
    pytest.mark.tigerbeetle,
    pytest.mark.integration,
]


def get_tb_addresses() -> list[str]:
    """Get TigerBeetle addresses from environment or use default."""
    addresses = os.environ.get("TIGERBEETLE_ADDRESSES", "127.0.0.1:3000")
    return [addr.strip() for addr in addresses.split(",")]


def get_tb_cluster_id() -> int:
    """Get TigerBeetle cluster ID from environment or use default."""
    return int(os.environ.get("TIGERBEETLE_CLUSTER_ID", "0"))


@pytest.fixture(scope="module")
def tb_client():
    """Create a TigerBeetle client for testing."""
    try:
        from tigerbeetle import client as tb
    except ImportError:
        pytest.skip("TigerBeetle client not installed (pip install tigerbeetle)")

    addresses = get_tb_addresses()
    cluster_id = get_tb_cluster_id()

    try:
        # replica_addresses is a comma-separated string, not a list
        addresses_str = ",".join(addresses)
        client = tb.Client(cluster_id, addresses_str)
        yield client
    except Exception as e:
        pytest.skip(f"Could not connect to TigerBeetle at {addresses}: {e}")
    finally:
        # Client cleanup handled by context manager if used
        pass


@pytest.fixture
def unique_id() -> int:
    """Generate a unique 128-bit ID for test accounts/transfers."""
    return uuid.uuid4().int & ((1 << 128) - 1)


class TestTigerBeetleConnection:
    """Test TigerBeetle connection and basic operations."""

    def test_client_connects(self, tb_client) -> None:
        """Client should connect successfully."""
        # If we got here, the client connected
        assert tb_client is not None

    def test_lookup_nonexistent_account(self, tb_client, unique_id: int) -> None:
        """Looking up a nonexistent account should return empty."""

        result = tb_client.lookup_accounts([unique_id])
        assert len(result) == 0


class TestTigerBeetleAccounts:
    """Test TigerBeetle account operations."""

    def test_create_account(self, tb_client, unique_id: int) -> None:
        """Should create an account successfully."""
        from tigerbeetle import client as tb

        account = tb.Account(
            id=unique_id,
            ledger=1,
            code=1000,
            flags=0,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
        )

        errors = tb_client.create_accounts([account])
        assert len(errors) == 0, f"Account creation failed: {errors}"

        # Verify account exists
        accounts = tb_client.lookup_accounts([unique_id])
        assert len(accounts) == 1
        assert accounts[0].id == unique_id
        assert accounts[0].ledger == 1
        assert accounts[0].code == 1000

    def test_create_account_linked_pair(self, tb_client) -> None:
        """Should create linked accounts atomically."""
        from tigerbeetle import client as tb

        id1 = uuid.uuid4().int & ((1 << 128) - 1)
        id2 = uuid.uuid4().int & ((1 << 128) - 1)

        account1 = tb.Account(
            id=id1,
            ledger=1,
            code=1001,  # Asset account
            flags=tb.AccountFlags.LINKED,  # Link to next
        )
        account2 = tb.Account(
            id=id2,
            ledger=1,
            code=2001,  # Liability account
            flags=0,
        )

        errors = tb_client.create_accounts([account1, account2])
        assert len(errors) == 0, f"Linked account creation failed: {errors}"

        # Both accounts should exist
        accounts = tb_client.lookup_accounts([id1, id2])
        assert len(accounts) == 2

    def test_duplicate_account_returns_exists(self, tb_client, unique_id: int) -> None:
        """Creating duplicate account should return EXISTS error."""
        from tigerbeetle import client as tb

        account = tb.Account(
            id=unique_id,
            ledger=1,
            code=1000,
        )

        # First creation succeeds
        errors = tb_client.create_accounts([account])
        assert len(errors) == 0

        # Second creation returns EXISTS
        errors = tb_client.create_accounts([account])
        assert len(errors) == 1
        assert errors[0].result == tb.CreateAccountResult.EXISTS


class TestTigerBeetleTransfers:
    """Test TigerBeetle transfer operations."""

    @pytest.fixture
    def account_pair(self, tb_client) -> tuple[int, int]:
        """Create a pair of accounts for transfer testing."""
        from tigerbeetle import client as tb

        debit_id = uuid.uuid4().int & ((1 << 128) - 1)
        credit_id = uuid.uuid4().int & ((1 << 128) - 1)

        accounts = [
            tb.Account(
                id=debit_id,
                ledger=1,
                code=1000,
                flags=tb.AccountFlags.CREDITS_MUST_NOT_EXCEED_DEBITS,
            ),
            tb.Account(
                id=credit_id,
                ledger=1,
                code=1000,
            ),
        ]

        # First fund the debit account by creating it with initial balance
        # (In TigerBeetle, we need to transfer from a "bank" account)
        bank_id = uuid.uuid4().int & ((1 << 128) - 1)
        accounts.insert(
            0,
            tb.Account(
                id=bank_id,
                ledger=1,
                code=9999,  # Bank/system account
            ),
        )

        errors = tb_client.create_accounts(accounts)
        assert len(errors) == 0, f"Account creation failed: {errors}"

        # Fund the debit account from bank
        transfer = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            debit_account_id=bank_id,
            credit_account_id=debit_id,
            ledger=1,
            code=1,
            amount=10000,
            flags=0,
        )
        errors = tb_client.create_transfers([transfer])
        assert len(errors) == 0, f"Funding transfer failed: {errors}"

        return debit_id, credit_id

    def test_create_transfer(self, tb_client, account_pair: tuple[int, int]) -> None:
        """Should create a transfer successfully."""
        from tigerbeetle import client as tb

        debit_id, credit_id = account_pair
        transfer_id = uuid.uuid4().int & ((1 << 128) - 1)

        transfer = tb.Transfer(
            id=transfer_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=1000,
            flags=0,
        )

        errors = tb_client.create_transfers([transfer])
        assert len(errors) == 0, f"Transfer creation failed: {errors}"

        # Verify transfer exists
        transfers = tb_client.lookup_transfers([transfer_id])
        assert len(transfers) == 1
        assert transfers[0].id == transfer_id
        assert transfers[0].amount == 1000

    def test_transfer_updates_balances(self, tb_client, account_pair: tuple[int, int]) -> None:
        """Transfer should update account balances."""
        from tigerbeetle import client as tb

        debit_id, credit_id = account_pair

        # Get initial balances
        accounts_before = tb_client.lookup_accounts([debit_id, credit_id])
        debit_before = next(a for a in accounts_before if a.id == debit_id)
        credit_before = next(a for a in accounts_before if a.id == credit_id)

        # Create transfer
        transfer = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=500,
            flags=0,
        )
        errors = tb_client.create_transfers([transfer])
        assert len(errors) == 0

        # Check balances changed
        accounts_after = tb_client.lookup_accounts([debit_id, credit_id])
        debit_after = next(a for a in accounts_after if a.id == debit_id)
        credit_after = next(a for a in accounts_after if a.id == credit_id)

        assert debit_after.debits_posted == debit_before.debits_posted + 500
        assert credit_after.credits_posted == credit_before.credits_posted + 500

    def test_transfer_exceeds_balance_fails(self, tb_client, account_pair: tuple[int, int]) -> None:
        """Transfer exceeding balance should fail (with CREDITS_MUST_NOT_EXCEED_DEBITS)."""
        from tigerbeetle import client as tb

        debit_id, credit_id = account_pair

        # Try to transfer more than available
        transfer = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=999999999,  # Way more than funded
            flags=0,
        )

        errors = tb_client.create_transfers([transfer])
        assert len(errors) == 1
        assert errors[0].result == tb.CreateTransferResult.EXCEEDS_CREDITS


class TestTigerBeetlePendingTransfers:
    """Test TigerBeetle two-phase commit (pending) transfers."""

    @pytest.fixture
    def funded_accounts(self, tb_client) -> tuple[int, int]:
        """Create funded accounts for pending transfer testing."""
        from tigerbeetle import client as tb

        bank_id = uuid.uuid4().int & ((1 << 128) - 1)
        debit_id = uuid.uuid4().int & ((1 << 128) - 1)
        credit_id = uuid.uuid4().int & ((1 << 128) - 1)

        accounts = [
            tb.Account(id=bank_id, ledger=1, code=9999),
            tb.Account(id=debit_id, ledger=1, code=1000),
            tb.Account(id=credit_id, ledger=1, code=1000),
        ]

        errors = tb_client.create_accounts(accounts)
        assert len(errors) == 0

        # Fund debit account
        transfer = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            debit_account_id=bank_id,
            credit_account_id=debit_id,
            ledger=1,
            code=1,
            amount=50000,
            flags=0,
        )
        errors = tb_client.create_transfers([transfer])
        assert len(errors) == 0

        return debit_id, credit_id

    def test_pending_transfer_and_post(self, tb_client, funded_accounts: tuple[int, int]) -> None:
        """Should create pending transfer and post it."""
        from tigerbeetle import client as tb

        debit_id, credit_id = funded_accounts
        pending_id = uuid.uuid4().int & ((1 << 128) - 1)

        # Create pending transfer
        pending = tb.Transfer(
            id=pending_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=2000,
            flags=tb.TransferFlags.PENDING,
            timeout=0,  # No timeout for test
        )
        errors = tb_client.create_transfers([pending])
        assert len(errors) == 0, f"Pending transfer failed: {errors}"

        # Check pending amounts
        accounts = tb_client.lookup_accounts([debit_id, credit_id])
        debit = next(a for a in accounts if a.id == debit_id)
        credit = next(a for a in accounts if a.id == credit_id)

        assert debit.debits_pending == 2000
        assert credit.credits_pending == 2000

        # Post the transfer
        post = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            pending_id=pending_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=2000,
            flags=tb.TransferFlags.POST_PENDING_TRANSFER,
        )
        errors = tb_client.create_transfers([post])
        assert len(errors) == 0, f"Post transfer failed: {errors}"

        # Verify pending cleared and posted
        accounts = tb_client.lookup_accounts([debit_id, credit_id])
        debit = next(a for a in accounts if a.id == debit_id)
        credit = next(a for a in accounts if a.id == credit_id)

        assert debit.debits_pending == 0
        assert credit.credits_pending == 0
        assert debit.debits_posted >= 2000
        assert credit.credits_posted >= 2000

    def test_pending_transfer_void(self, tb_client, funded_accounts: tuple[int, int]) -> None:
        """Should void a pending transfer."""
        from tigerbeetle import client as tb

        debit_id, credit_id = funded_accounts
        pending_id = uuid.uuid4().int & ((1 << 128) - 1)

        # Create pending transfer
        pending = tb.Transfer(
            id=pending_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=3000,
            flags=tb.TransferFlags.PENDING,
        )
        errors = tb_client.create_transfers([pending])
        assert len(errors) == 0

        # Void the transfer
        void = tb.Transfer(
            id=uuid.uuid4().int & ((1 << 128) - 1),
            pending_id=pending_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            ledger=1,
            code=1,
            amount=3000,
            flags=tb.TransferFlags.VOID_PENDING_TRANSFER,
        )
        errors = tb_client.create_transfers([void])
        assert len(errors) == 0, f"Void transfer failed: {errors}"

        # Verify pending cleared but not posted
        accounts = tb_client.lookup_accounts([debit_id, credit_id])
        debit = next(a for a in accounts if a.id == debit_id)
        credit = next(a for a in accounts if a.id == credit_id)

        assert debit.debits_pending == 0
        assert credit.credits_pending == 0


class TestTigerBeetleBatch:
    """Test TigerBeetle batch operations."""

    def test_batch_account_creation(self, tb_client) -> None:
        """Should create multiple accounts in a batch."""
        from tigerbeetle import client as tb

        accounts = [
            tb.Account(
                id=uuid.uuid4().int & ((1 << 128) - 1),
                ledger=1,
                code=1000 + i,
            )
            for i in range(10)
        ]

        errors = tb_client.create_accounts(accounts)
        assert len(errors) == 0, f"Batch account creation failed: {errors}"

        # Verify all exist
        ids = [a.id for a in accounts]
        found = tb_client.lookup_accounts(ids)
        assert len(found) == 10

    def test_batch_transfers(self, tb_client) -> None:
        """Should create multiple transfers in a batch."""
        from tigerbeetle import client as tb

        # Create source and destination accounts
        bank_id = uuid.uuid4().int & ((1 << 128) - 1)
        dest_ids = [uuid.uuid4().int & ((1 << 128) - 1) for _ in range(5)]

        accounts = [tb.Account(id=bank_id, ledger=1, code=9999)]
        accounts.extend([tb.Account(id=did, ledger=1, code=1000) for did in dest_ids])

        errors = tb_client.create_accounts(accounts)
        assert len(errors) == 0

        # Create batch transfers
        transfers = [
            tb.Transfer(
                id=uuid.uuid4().int & ((1 << 128) - 1),
                debit_account_id=bank_id,
                credit_account_id=dest_id,
                ledger=1,
                code=1,
                amount=100,
            )
            for dest_id in dest_ids
        ]

        errors = tb_client.create_transfers(transfers)
        assert len(errors) == 0, f"Batch transfers failed: {errors}"

        # Verify all transfers exist
        transfer_ids = [t.id for t in transfers]
        found = tb_client.lookup_transfers(transfer_ids)
        assert len(found) == 5
