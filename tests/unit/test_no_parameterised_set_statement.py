"""Regression guard for #1201.

A PostgreSQL ``SET`` statement cannot take a bound parameter — psycopg sends
``$1`` for ``%s`` and Postgres rejects it with a syntax error. A parameterised
``SET search_path`` therefore fails silently at runtime and leaves every tenant
schema unmigrated on each boot. The schema name must be composed as a quoted
identifier via ``psycopg.sql.Identifier`` instead.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"


def test_no_parameterised_set_search_path() -> None:
    offenders = [
        str(path.relative_to(_SRC.parents[1]))
        for path in _SRC.rglob("*.py")
        if "SET search_path TO %s" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "PostgreSQL SET cannot take a bound parameter — compose the schema "
        f"identifier via psycopg.sql.Identifier instead (#1201). Offenders: {offenders}"
    )
