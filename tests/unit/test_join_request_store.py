"""Unit test for JoinRequestRecord shape (TDD RED step, #1424)."""

from dazzle.http.runtime.auth.models import JoinRequestRecord


def test_join_request_defaults_pending():
    jr = JoinRequestRecord(id="r1", tenant_id="t1", identity_id="u1", email="x@a.com")
    assert jr.status == "pending"
    assert jr.decided_at is None and jr.decided_by is None
