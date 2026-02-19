"""Unit tests for OTPStore and RecoveryCodeStore.

These stores use PostgreSQL. We mock the database layer by replacing
_get_connection() with an in-memory cursor simulator so no real DB is needed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from dazzle_back.runtime.otp_store import OTPStore
from dazzle_back.runtime.recovery_codes import (
    RecoveryCodeStore,
    generate_recovery_codes,
)
from dazzle_back.runtime.recovery_codes import (
    _hash_code as recovery_hash_code,
)

# ---------------------------------------------------------------------------
# In-memory database simulator
# ---------------------------------------------------------------------------


class InMemoryDB:
    """Minimal in-memory table simulator for dict_row-style psycopg cursors."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self._next_id: dict[str, int] = {}

    def _ensure_table(self, name: str) -> list[dict]:
        if name not in self.tables:
            self.tables[name] = []
            self._next_id[name] = 1
        return self.tables[name]

    def insert(self, table: str, row: dict) -> int:
        rows = self._ensure_table(table)
        row_id = self._next_id[table]
        self._next_id[table] += 1
        row["id"] = row_id
        rows.append(dict(row))
        return row_id

    def select(self, table: str, predicate=None, order_desc_key=None, limit=None):
        rows = self._ensure_table(table)
        result = [dict(r) for r in rows if (predicate is None or predicate(r))]
        if order_desc_key:
            result.sort(key=lambda r: r.get(order_desc_key, ""), reverse=True)
        if limit:
            result = result[:limit]
        return result

    def update(self, table: str, predicate, updates: dict) -> int:
        rows = self._ensure_table(table)
        count = 0
        for r in rows:
            if predicate(r):
                r.update(updates)
                count += 1
        return count

    def delete(self, table: str, predicate) -> int:
        rows = self._ensure_table(table)
        before = len(rows)
        self.tables[table] = [r for r in rows if not predicate(r)]
        return before - len(self.tables[table])


class MockCursor:
    """Cursor that interprets simplified SQL against an InMemoryDB."""

    def __init__(self, db: InMemoryDB) -> None:
        self.db = db
        self.rowcount = 0
        self._result: list[dict] | None = None
        self._result_index = 0

    # -- helpers to parse the SQL just enough --------------------------------

    @staticmethod
    def _extract_table(sql: str) -> str:
        """Pull the table name out of common SQL patterns."""
        for pattern in [
            r"INSERT\s+INTO\s+(\S+)",
            r"UPDATE\s+(\S+)\s+SET",
            r"DELETE\s+FROM\s+(\S+)",
            r"FROM\s+(\S+)",
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\S+)",
            r"CREATE\s+INDEX",
        ]:
            m = re.search(pattern, sql, re.IGNORECASE)
            if m and "INDEX" not in pattern:
                return m.group(1)
        return "__unknown__"

    def execute(self, sql: str, params=()) -> None:  # noqa: C901
        sql_upper = sql.strip().upper()

        # DDL (CREATE TABLE / CREATE INDEX) -- just ignore
        if sql_upper.startswith("CREATE"):
            self.rowcount = 0
            return

        table = self._extract_table(sql)

        if sql_upper.startswith("INSERT"):
            # Parse column names from INSERT INTO table (col1, col2, ...) VALUES (...)
            col_match = re.search(r"\(([^)]+)\)\s*VALUES", sql, re.IGNORECASE)
            if col_match:
                cols = [c.strip() for c in col_match.group(1).split(",")]
                row = dict(zip(cols, params, strict=False))
                # Set defaults
                row.setdefault("used", False)
                row.setdefault("attempts", 0)
                self.db.insert(table, row)
                self.rowcount = 1

        elif sql_upper.startswith("UPDATE"):
            # We handle specific known patterns used by OTPStore and RecoveryCodeStore
            if "SET used = TRUE, used_at" in sql:
                # UPDATE table SET used = TRUE, used_at = %s WHERE id = %s
                used_at, record_id = params
                self.rowcount = self.db.update(
                    table, lambda r: r["id"] == record_id, {"used": True, "used_at": used_at}
                )
            elif "SET used = TRUE" in sql and "WHERE id" in sql:
                # UPDATE table SET used = TRUE WHERE id = %s
                (record_id,) = params
                self.rowcount = self.db.update(
                    table, lambda r: r["id"] == record_id, {"used": True}
                )
            elif "SET used = TRUE" in sql and "user_id" in sql:
                # UPDATE table SET used = TRUE WHERE user_id = %s AND method = %s AND used = FALSE
                uid, method = params
                self.rowcount = self.db.update(
                    table,
                    lambda r: r["user_id"] == uid and r["method"] == method and not r["used"],
                    {"used": True},
                )
            elif "SET attempts = attempts + 1" in sql:
                # UPDATE table SET attempts = attempts + 1 WHERE id = %s
                (record_id,) = params
                for r in self.db._ensure_table(table):
                    if r["id"] == record_id:
                        r["attempts"] = r.get("attempts", 0) + 1
                        self.rowcount = 1
                        return
                self.rowcount = 0
            else:
                self.rowcount = 0

        elif sql_upper.startswith("DELETE"):
            if "user_id" in sql:
                (uid,) = params
                self.rowcount = self.db.delete(table, lambda r: r["user_id"] == uid)
            elif "expires_at" in sql:
                (cutoff,) = params
                self.rowcount = self.db.delete(table, lambda r: r["expires_at"] < cutoff)
            else:
                self.rowcount = 0

        elif sql_upper.startswith("SELECT"):
            if "COUNT(*)" in sql_upper:
                (uid,) = params
                rows = self.db.select(
                    table,
                    lambda r: r["user_id"] == uid and not r["used"],
                )
                self._result = [{"count": len(rows)}]
                self.rowcount = 1
            elif "ORDER BY" in sql_upper:
                # OTP verify: SELECT * ... WHERE user_id=%s AND method=%s AND used=FALSE
                # AND expires_at > %s ORDER BY created_at DESC LIMIT 1
                uid, method, cutoff = params
                rows = self.db.select(
                    table,
                    lambda r: (
                        r["user_id"] == uid
                        and r["method"] == method
                        and not r["used"]
                        and r["expires_at"] > cutoff
                    ),
                    order_desc_key="created_at",
                    limit=1,
                )
                self._result = rows
                self.rowcount = len(rows)
            else:
                # RecoveryCodeStore verify: SELECT id, code_hash ... WHERE user_id=%s AND used=FALSE
                (uid,) = params
                rows = self.db.select(
                    table,
                    lambda r: r["user_id"] == uid and not r["used"],
                )
                self._result = rows
                self.rowcount = len(rows)
        else:
            self.rowcount = 0

    def fetchone(self) -> dict | None:
        if self._result and self._result_index < len(self._result):
            row = self._result[self._result_index]
            self._result_index += 1
            return row
        return None

    def fetchall(self) -> list[dict]:
        if self._result is None:
            return []
        remaining = self._result[self._result_index :]
        self._result_index = len(self._result)
        return remaining


class MockConnection:
    """Mock connection wrapping an InMemoryDB."""

    def __init__(self, db: InMemoryDB) -> None:
        self.db = db
        self._cursor = MockCursor(db)

    def cursor(self) -> MockCursor:
        # Reset result state for each new cursor() call usage
        self._cursor._result = None
        self._cursor._result_index = 0
        return self._cursor

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> InMemoryDB:
    return InMemoryDB()


@pytest.fixture()
def otp_store(db: InMemoryDB) -> OTPStore:
    store = OTPStore("postgresql://localhost/test")
    conn = MockConnection(db)
    store._get_connection = lambda: conn  # type: ignore[assignment]
    return store


@pytest.fixture()
def recovery_store(db: InMemoryDB) -> RecoveryCodeStore:
    store = RecoveryCodeStore("postgresql://localhost/test")
    conn = MockConnection(db)
    store._get_connection = lambda: conn  # type: ignore[assignment]
    return store


@pytest.fixture()
def user_id() -> UUID:
    return uuid4()


# ===========================================================================
# OTPStore tests
# ===========================================================================


class TestOTPStoreCreateOtp:
    """Tests for OTPStore.create_otp()."""

    def test_returns_six_digit_code(self, otp_store: OTPStore, user_id: UUID) -> None:
        code = otp_store.create_otp(user_id)
        assert len(code) == 6
        assert code.isdigit()

    def test_custom_length(self, otp_store: OTPStore, user_id: UUID) -> None:
        code = otp_store.create_otp(user_id, length=8)
        assert len(code) == 8
        assert code.isdigit()

    def test_invalidates_previous_otps_for_same_user_and_method(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """Creating a new OTP marks previous unused OTPs as used."""
        otp_store.create_otp(user_id, method="email_otp")
        otp_store.create_otp(user_id, method="email_otp")

        rows = db.tables[OTPStore.TABLE]
        # First row should now be marked used (invalidated by the second create)
        assert rows[0]["used"] is True
        # Second row is the fresh one
        assert rows[1]["used"] is False

    def test_different_methods_not_invalidated(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """OTPs for different methods are independent."""
        otp_store.create_otp(user_id, method="email_otp")
        otp_store.create_otp(user_id, method="totp_setup")

        rows = db.tables[OTPStore.TABLE]
        # Both should be unused -- different methods
        assert rows[0]["used"] is False
        assert rows[1]["used"] is False


class TestOTPStoreVerifyOtp:
    """Tests for OTPStore.verify_otp()."""

    def test_valid_code_returns_true(self, otp_store: OTPStore, user_id: UUID) -> None:
        code = otp_store.create_otp(user_id)
        assert otp_store.verify_otp(user_id, code) is True

    def test_wrong_code_returns_false(self, otp_store: OTPStore, user_id: UUID) -> None:
        otp_store.create_otp(user_id)
        assert otp_store.verify_otp(user_id, "000000") is False

    def test_expired_code_returns_false(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """An OTP whose expires_at is in the past should not verify."""
        code = otp_store.create_otp(user_id, ttl=300)

        # Manually backdate the expires_at so it appears expired
        for row in db.tables[OTPStore.TABLE]:
            row["expires_at"] = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

        assert otp_store.verify_otp(user_id, code) is False

    def test_max_attempts_exceeded_returns_false(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """After max_attempts wrong tries, verification fails even with correct code."""
        code = otp_store.create_otp(user_id, max_attempts=3)

        # Use up all attempts with wrong codes
        otp_store.verify_otp(user_id, "111111")
        otp_store.verify_otp(user_id, "222222")
        otp_store.verify_otp(user_id, "333333")

        # Now even the correct code should fail (attempts >= max_attempts marks it used)
        assert otp_store.verify_otp(user_id, code) is False

    def test_code_marked_used_after_successful_verify(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """A successfully verified code is marked used and cannot be reused."""
        code = otp_store.create_otp(user_id)
        assert otp_store.verify_otp(user_id, code) is True
        # Second attempt with same code should fail (already used)
        assert otp_store.verify_otp(user_id, code) is False

    def test_wrong_user_returns_false(self, otp_store: OTPStore, user_id: UUID) -> None:
        code = otp_store.create_otp(user_id)
        other_user = uuid4()
        assert otp_store.verify_otp(other_user, code) is False


class TestOTPStoreCleanup:
    """Tests for OTPStore.cleanup_expired()."""

    def test_removes_expired_records(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        otp_store.create_otp(user_id)

        # Backdate so it's expired
        for row in db.tables[OTPStore.TABLE]:
            row["expires_at"] = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

        deleted = otp_store.cleanup_expired()
        assert deleted == 1
        assert len(db.tables[OTPStore.TABLE]) == 0

    def test_keeps_non_expired_records(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        otp_store.create_otp(user_id, ttl=3600)

        deleted = otp_store.cleanup_expired()
        assert deleted == 0
        assert len(db.tables[OTPStore.TABLE]) == 1

    def test_mixed_expired_and_fresh(
        self, otp_store: OTPStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """Only expired records are removed; fresh ones stay."""
        otp_store.create_otp(user_id, method="email_otp")
        otp_store.create_otp(user_id, method="totp_setup")

        # Expire only the first one
        rows = db.tables[OTPStore.TABLE]
        # The first was invalidated (used=True) by second create_otp for same method.
        # Actually they are different methods, so both are alive. Expire the first.
        rows[0]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

        deleted = otp_store.cleanup_expired()
        assert deleted == 1
        assert len(db.tables[OTPStore.TABLE]) == 1


# ===========================================================================
# RecoveryCodeStore tests
# ===========================================================================


class TestGenerateRecoveryCodes:
    """Tests for the standalone generate_recovery_codes() function."""

    def test_generates_correct_count(self) -> None:
        codes = generate_recovery_codes(count=8)
        assert len(codes) == 8

    def test_custom_count(self) -> None:
        codes = generate_recovery_codes(count=12)
        assert len(codes) == 12

    def test_format_xxxx_xxxx(self) -> None:
        """Each code matches the XXXX-XXXX pattern."""
        codes = generate_recovery_codes(count=10)
        pattern = re.compile(r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        for code in codes:
            assert pattern.match(code), f"Code {code!r} does not match XXXX-XXXX"

    def test_excludes_ambiguous_characters(self) -> None:
        """Codes should not contain I, O, 0, or 1."""
        codes = generate_recovery_codes(count=50)  # generate many for coverage
        for code in codes:
            raw = code.replace("-", "")
            assert "I" not in raw
            assert "O" not in raw
            assert "0" not in raw
            assert "1" not in raw

    def test_codes_are_unique(self) -> None:
        codes = generate_recovery_codes(count=20)
        assert len(set(codes)) == len(codes)


class TestRecoveryCodeStoreStoreCodes:
    """Tests for RecoveryCodeStore.store_codes()."""

    def test_replaces_existing_codes(
        self, recovery_store: RecoveryCodeStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        """Storing new codes deletes the old ones first."""
        codes1 = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes1)
        assert len(db.tables[RecoveryCodeStore.TABLE]) == 4

        codes2 = generate_recovery_codes(count=6)
        recovery_store.store_codes(user_id, codes2)
        # Old 4 deleted, new 6 inserted
        assert len(db.tables[RecoveryCodeStore.TABLE]) == 6

    def test_stores_hashed_not_plaintext(
        self, recovery_store: RecoveryCodeStore, db: InMemoryDB, user_id: UUID
    ) -> None:
        codes = ["ABCD-EFGH"]
        recovery_store.store_codes(user_id, codes)
        row = db.tables[RecoveryCodeStore.TABLE][0]
        # Should be a SHA-256 hex digest, not the plaintext
        assert row["code_hash"] != "ABCD-EFGH"
        assert len(row["code_hash"]) == 64  # SHA-256 hex length


class TestRecoveryCodeStoreVerifyCode:
    """Tests for RecoveryCodeStore.verify_code()."""

    def test_valid_code_returns_true(
        self, recovery_store: RecoveryCodeStore, user_id: UUID
    ) -> None:
        codes = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes)
        assert recovery_store.verify_code(user_id, codes[0]) is True

    def test_invalid_code_returns_false(
        self, recovery_store: RecoveryCodeStore, user_id: UUID
    ) -> None:
        codes = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes)
        assert recovery_store.verify_code(user_id, "ZZZZ-ZZZZ") is False

    def test_already_used_code_returns_false(
        self, recovery_store: RecoveryCodeStore, user_id: UUID
    ) -> None:
        codes = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes)
        assert recovery_store.verify_code(user_id, codes[1]) is True
        # Second use should fail
        assert recovery_store.verify_code(user_id, codes[1]) is False

    def test_case_insensitive(self, recovery_store: RecoveryCodeStore, user_id: UUID) -> None:
        """Codes are case-insensitive: lowercase input matches uppercase stored code."""
        codes = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes)
        lowercase_code = codes[2].lower()
        assert recovery_store.verify_code(user_id, lowercase_code) is True

    def test_wrong_user_returns_false(
        self, recovery_store: RecoveryCodeStore, user_id: UUID
    ) -> None:
        codes = generate_recovery_codes(count=4)
        recovery_store.store_codes(user_id, codes)
        other_user = uuid4()
        assert recovery_store.verify_code(other_user, codes[0]) is False


class TestRecoveryCodeStoreRemainingCount:
    """Tests for RecoveryCodeStore.remaining_count()."""

    def test_returns_correct_count(self, recovery_store: RecoveryCodeStore, user_id: UUID) -> None:
        codes = generate_recovery_codes(count=8)
        recovery_store.store_codes(user_id, codes)
        assert recovery_store.remaining_count(user_id) == 8

    def test_decrements_after_use(self, recovery_store: RecoveryCodeStore, user_id: UUID) -> None:
        codes = generate_recovery_codes(count=8)
        recovery_store.store_codes(user_id, codes)
        recovery_store.verify_code(user_id, codes[0])
        assert recovery_store.remaining_count(user_id) == 7

    def test_zero_for_unknown_user(self, recovery_store: RecoveryCodeStore) -> None:
        assert recovery_store.remaining_count(uuid4()) == 0

    def test_zero_after_all_used(self, recovery_store: RecoveryCodeStore, user_id: UUID) -> None:
        codes = generate_recovery_codes(count=3)
        recovery_store.store_codes(user_id, codes)
        for code in codes:
            recovery_store.verify_code(user_id, code)
        assert recovery_store.remaining_count(user_id) == 0


class TestRecoveryCodeHashNormalization:
    """Tests for the _hash_code normalization in recovery_codes module."""

    def test_dash_stripped(self) -> None:
        """ABCDEFGH and ABCD-EFGH produce the same hash."""
        assert recovery_hash_code("ABCD-EFGH") == recovery_hash_code("ABCDEFGH")

    def test_case_insensitive_hash(self) -> None:
        """Uppercase and lowercase produce the same hash."""
        assert recovery_hash_code("ABCD-EFGH") == recovery_hash_code("abcd-efgh")

    def test_mixed_case_and_dashes(self) -> None:
        assert recovery_hash_code("AbCd-EfGh") == recovery_hash_code("ABCDEFGH")


class TestOTPStoreUrlNormalization:
    """Tests for database URL normalization."""

    def test_postgres_prefix_converted(self) -> None:
        store = OTPStore("postgres://host/db")
        assert store._database_url == "postgresql://host/db"

    def test_postgresql_prefix_unchanged(self) -> None:
        store = OTPStore("postgresql://host/db")
        assert store._database_url == "postgresql://host/db"


class TestRecoveryCodeStoreUrlNormalization:
    """Tests for database URL normalization."""

    def test_postgres_prefix_converted(self) -> None:
        store = RecoveryCodeStore("postgres://host/db")
        assert store._database_url == "postgresql://host/db"

    def test_postgresql_prefix_unchanged(self) -> None:
        store = RecoveryCodeStore("postgresql://host/db")
        assert store._database_url == "postgresql://host/db"
