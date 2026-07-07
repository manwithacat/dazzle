# tests/unit/test_byte_audit_coalescing.py
import pytest

from dazzle.http.runtime.byte_serving import AccessDecision, ByteAudit


class _Logger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def log_decision(self, **kw: object) -> None:
        self.rows.append(kw)


def _d(rec: str = "r1") -> AccessDecision:
    return AccessDecision(
        user_id="u1",
        entity="Doc",
        record_id=rec,
        field="file",
        matched_policy="scope:list",
        verb="read",
    )


@pytest.mark.asyncio
async def test_first_access_writes_second_within_window_does_not() -> None:
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: 1000.0)
    await audit.record(_d(), served="200", coalesce=True)
    await audit.record(_d(), served="206", coalesce=True)
    assert len(log.rows) == 1


@pytest.mark.asyncio
async def test_denied_always_writes() -> None:
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: 1000.0)
    await audit.record(_d(), served="200", coalesce=True)
    await audit.record(_d(), served="416", coalesce=False)
    assert len(log.rows) == 2


@pytest.mark.asyncio
async def test_new_window_writes_again() -> None:
    ticks = iter([1000.0, 1000.0, 2000.0])
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: next(ticks))
    await audit.record(_d(), served="200", coalesce=True)  # t=1000 write
    await audit.record(_d(), served="206", coalesce=True)  # t=1000 coalesced
    await audit.record(_d(), served="206", coalesce=True)  # t=2000 new window → write
    assert len(log.rows) == 2


@pytest.mark.asyncio
async def test_first_access_row_content() -> None:
    """The written row carries the correct entity_name/entity_id/user_id/decision."""
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: 1000.0)
    await audit.record(_d("doc-42"), served="200", coalesce=True)
    assert len(log.rows) == 1
    row = log.rows[0]
    assert row["entity_name"] == "Doc"
    assert row["entity_id"] == "doc-42"
    assert row["user_id"] == "u1"
    assert row["decision"] == "allow"
    assert row["operation"] == "document_access"
    assert row["matched_policy"] == "scope:list"
    assert row["policy_effect"] == "allow"
