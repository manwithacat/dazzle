"""Postgres-backed stores whose schema DDL runs on first use.

Shared by :class:`dazzle.http.runtime.auth.store.AuthStore` and
:class:`dazzle.http.runtime.token_store.TokenStore`: construction is pure (no
I/O) so the store can be built without a live database; the table DDL in the
subclass's ``_init_db`` is deferred to the first connection, or to an explicit
``ensure_initialized()`` at server boot to keep eager-DDL / fail-fast behaviour.
"""

from __future__ import annotations

import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row

from dazzle.core.db_url import normalise_postgres_scheme


class LazyPgStore:
    """Base for a store with lazily-initialised Postgres schema."""

    def __init__(self, database_url: str) -> None:
        # Normalize Heroku's postgres:// to postgresql://
        self._database_url = normalise_postgres_scheme(database_url)
        self._initialized = False
        self._init_lock = threading.Lock()

    def _init_db(self) -> None:
        """Create the store's tables. Runs once, under the init lock."""
        raise NotImplementedError

    def ensure_initialized(self) -> None:
        """Run first-use schema initialization (idempotent, thread-safe).

        Concurrency (review #1504 follow-up): double-checked locking makes the
        flag flip atomic, and ``_initialized`` is set only AFTER ``_init_db``
        completes — so a concurrent caller either waits on the lock or sees the
        store fully initialized, never a half-built schema. ``_init_db`` uses
        ``_connect_raw`` (not ``_get_connection``) so it never re-enters this
        method under the lock. On failure the flag stays False → retryable.
        """
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._init_db()
            self._initialized = True

    def _connect_raw(self) -> psycopg.Connection[dict[str, Any]]:
        """A connection that does NOT trigger lazy init — used only by _init_db."""
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _get_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Get a PostgreSQL database connection (lazily initializing schema)."""
        self.ensure_initialized()
        return self._connect_raw()
