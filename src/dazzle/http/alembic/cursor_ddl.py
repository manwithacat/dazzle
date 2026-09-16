"""Run a psycopg-cursor DDL helper inside an Alembic revision."""

from collections.abc import Callable
from typing import Any


def apply_ensure_on_alembic_cursor(ensure_fn: Callable[[Any], None]) -> None:
    """Open the Alembic bind's psycopg cursor, call *ensure_fn*, close it."""
    from alembic import op

    bind = op.get_bind()
    raw_conn: Any = bind.connection
    cur = raw_conn.cursor()
    try:
        ensure_fn(cur)
    finally:
        cur.close()
