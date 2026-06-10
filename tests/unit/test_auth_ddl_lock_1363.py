"""#1363: auth-store boot DDL must serialize across workers.

Postgres's `CREATE INDEX IF NOT EXISTS` existence-check and the pg_class
catalog insert are not atomic across sessions — concurrently cold-booting
uvicorn workers both passed the check and the loser crashed with
`UniqueViolation: pg_class_relname_nsp_index`. Both boot-DDL transactions
must take the advisory lock as their FIRST statement (xact-scoped, released
at commit), mirroring MEMBERSHIP_EVENTS_LOCK_KEY / CONNECTION_DOMAIN_LOCK_KEY.
"""

from unittest.mock import MagicMock

from dazzle.back.runtime.auth.store import AUTH_DDL_LOCK_KEY, AuthStore


def _store_with_recording_conn() -> tuple[AuthStore, MagicMock]:
    store = AuthStore.__new__(AuthStore)  # skip __init__ (which runs _init_db)
    store._database_url = "postgresql://unused"
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = []  # no LOWER(email) collisions
    store._get_connection = lambda: conn  # type: ignore[method-assign]
    return store, conn


def _first_execute(conn: MagicMock) -> tuple:
    calls = conn.cursor.return_value.execute.call_args_list
    assert calls, "no SQL executed"
    return calls[0]


def test_init_db_takes_advisory_lock_first() -> None:
    store, conn = _store_with_recording_conn()
    store._init_db()
    sql, params = _first_execute(conn).args
    assert "pg_advisory_xact_lock" in sql
    assert params == (AUTH_DDL_LOCK_KEY,)


def test_email_ci_uniqueness_takes_advisory_lock_first() -> None:
    store, conn = _store_with_recording_conn()
    store._ensure_email_ci_uniqueness()
    sql, params = _first_execute(conn).args
    assert "pg_advisory_xact_lock" in sql
    assert params == (AUTH_DDL_LOCK_KEY,)
    # The index DDL still runs after the lock.
    all_sql = " ".join(str(c.args[0]) for c in conn.cursor.return_value.execute.call_args_list)
    assert "users_email_lower_key" in all_sql
