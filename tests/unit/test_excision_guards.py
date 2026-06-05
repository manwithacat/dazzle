"""excise_tenant safety guards (RLS Phase E.1 review hardening)."""

from types import SimpleNamespace

import pytest

from dazzle.db.excision import ExcisionError, excise_tenant


def test_rejects_autocommit_connection() -> None:
    """An autocommit conn would defeat atomicity + make dry_run destructive."""
    conn = SimpleNamespace(autocommit=True)
    appspec = SimpleNamespace(domain=SimpleNamespace(entities=[]), tenancy=None)
    with pytest.raises(ExcisionError, match="non-autocommit"):
        excise_tenant(appspec, "t-1", conn=conn)
