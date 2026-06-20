"""Issue #1037 Phase 1.B (v0.67.30): regression tests for the
MagicLinkMailer Protocol + LogMailer default impl.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from dazzle.http.runtime.auth.mailer import (
    LogMailer,
    MagicLinkMailer,
    get_mailer,
)


def test_log_mailer_satisfies_protocol() -> None:
    """The runtime-checkable Protocol means `isinstance(LogMailer(),
    MagicLinkMailer)` should be True."""
    assert isinstance(LogMailer(), MagicLinkMailer)


def test_log_mailer_writes_to_info_log(caplog) -> None:
    """LogMailer's send_magic_link emits one INFO record with the
    email + URL on a single line for log-aggregator scraping."""
    mailer = LogMailer()
    with caplog.at_level(logging.INFO):
        mailer.send_magic_link(
            to_email="alice@example.com",
            link_url="https://example.com/auth/magic/abc",
        )
    text = "\n".join(record.message for record in caplog.records)
    assert "alice@example.com" in text
    assert "https://example.com/auth/magic/abc" in text


def test_get_mailer_returns_log_mailer_when_no_override() -> None:
    """Default fallback when `app.state.magic_link_mailer` is unset."""
    state = SimpleNamespace()
    mailer = get_mailer(state)
    assert isinstance(mailer, LogMailer)


def test_get_mailer_returns_registered_mailer_when_present() -> None:
    """Operator-registered mailer wins over the default."""

    class _StubMailer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def send_magic_link(self, *, to_email: str, link_url: str) -> None:
            self.calls.append((to_email, link_url))

    stub = _StubMailer()
    state = SimpleNamespace(magic_link_mailer=stub)
    mailer = get_mailer(state)
    assert mailer is stub


def test_protocol_runtime_check_rejects_arbitrary_object() -> None:
    """Non-MagicLinkMailer objects fail the isinstance check —
    catches misconfigured deployments at request time rather than
    silently swallowing a bad mailer."""

    class _Bogus:
        pass

    state = SimpleNamespace(magic_link_mailer=_Bogus())
    try:
        get_mailer(state)
    except AssertionError:
        return
    raise AssertionError("expected AssertionError for non-Protocol mailer")
