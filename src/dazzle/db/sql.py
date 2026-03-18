# src/dazzle/db/sql.py
"""SQL helpers for db operations.

Re-exports quote_identifier from the runtime and provides query builders.
All SQL in this package goes through these helpers for safety.
"""

from __future__ import annotations


def quote_id(name: str) -> str:
    """Quote a SQL identifier (table or column name).

    Dazzle uses PascalCase entity names as table names, quoted with double-quotes.
    Re-implements the logic from dazzle_back.runtime.query_builder.quote_identifier
    to avoid importing the runtime package (which has heavier dependencies).
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'
