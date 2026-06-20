"""Regression test for #1111 — Redis consumer loop backoff.

The consumer loop used to catch *every* ``Exception`` (including the
``redis.asyncio.TimeoutError`` raised when ``XREADGROUP BLOCK`` times
out on an idle stream — the normal happy path) and ``await asyncio.sleep(1)``
unconditionally. The combination of a too-tight ``socket_timeout``
(5s) racing against ``block_ms`` (5000ms) made this fire every cycle,
hammering Heroku Redis with one read + one log + one sleep per second.

Fix: socket_timeout = block_ms + 2s slack; TimeoutError is its own
branch with no sleep + debug logging; genuine transport errors get
exponential backoff (1s base, 30s cap, reset on success).

Tests below pin the contract by inspecting the source of
``_consumer_loop`` and the ``connect()`` socket-timeout expression.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REDIS_BUS = ROOT / "src" / "dazzle" / "http" / "events" / "redis_bus.py"


def test_socket_timeout_exceeds_block_ms() -> None:
    """connect() must set socket_timeout > block_ms so the blocking read
    can finish before redis-py's socket layer fires a spurious timeout."""
    text = REDIS_BUS.read_text()
    # The fix uses `block_s = self._config.block_ms / 1000.0` and sets
    # `socket_timeout: block_s + 2.0`. Asserting both shapes pins the
    # contract — any future edit that drops the dependency or shrinks
    # the slack below 0 will trip this gate.
    assert "block_s = self._config.block_ms / 1000.0" in text, (
        "connect() must derive socket_timeout from block_ms — otherwise "
        "an idle XREADGROUP race causes hammering (#1111)."
    )
    assert '"socket_timeout": block_s + 2.0' in text


def test_consumer_loop_handles_timeout_separately() -> None:
    """_consumer_loop must have a dedicated TimeoutError except clause
    (ruff may fold `(TimeoutError, asyncio.TimeoutError)` to just
    `TimeoutError` — they're aliases in Python 3.11+)."""
    text = REDIS_BUS.read_text()
    # The dedicated branch logs at debug, not error, and does not sleep.
    assert "Consumer XREADGROUP timeout (idle stream)" in text, (
        "_consumer_loop must catch TimeoutError separately from the "
        "broad Exception clause (#1111). Empty-stream timeouts are the "
        "happy path, not an error to back off from."
    )
    # And the catch clause itself must be present.
    assert "except TimeoutError as e:" in text


def test_consumer_loop_uses_exponential_backoff() -> None:
    """Transport errors get exponential backoff up to a cap."""
    text = REDIS_BUS.read_text()
    assert "_BACKOFF_BASE_S = 1.0" in text
    assert "_BACKOFF_MAX_S = 30.0" in text
    # The backoff doubles each loop and is capped at _BACKOFF_MAX_S.
    assert "min(backoff_s * 2, _BACKOFF_MAX_S)" in text


def test_consumer_loop_resets_backoff_on_success() -> None:
    """A successful read clears the backoff window."""
    text = REDIS_BUS.read_text()
    # Two reset sites: after a successful XREADGROUP (even if empty)
    # and after a TimeoutError (idle stream = healthy connection).
    assert text.count("backoff_s = _BACKOFF_BASE_S") >= 3
