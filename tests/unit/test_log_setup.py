"""Unit tests for `ensure_dazzle_logging_configured` (#1122).

The helper must:

1. Attach a StreamHandler to `dazzle` logger when nothing is
   configured (the common "bare uvicorn / Heroku" case).
2. NOT touch logging when the root logger has handlers (project
   already called `logging.basicConfig` or similar).
3. NOT touch logging when the `dazzle` logger already has handlers
   (e.g. a prior call to this helper, or the project attached its
   own dazzle-specific handler).
4. Be idempotent — calling twice doesn't duplicate handlers.
5. Resolve the level from arg → env var → INFO default, in that order.
6. Set `propagate = False` on the dazzle logger to avoid double-emit
   when the project later adds a root handler.
"""

from __future__ import annotations

import logging

import pytest

from dazzle.log_setup import ensure_dazzle_logging_configured


@pytest.fixture
def _clean_loggers():
    """Snapshot+restore the root and `dazzle` logger state around each
    test so the order of tests doesn't matter and tests don't leak
    handlers across the suite.

    Yields a `clear()` callback the test must call right before
    invoking the helper — pytest's `_pytest.logging` plugin
    re-attaches a LogCaptureHandler to the root between this fixture's
    setup phase and the test body, so a one-shot clear at fixture
    setup time gets clobbered. The callback re-clears at the right
    moment."""
    root = logging.getLogger()
    dazzle_log = logging.getLogger("dazzle")
    saved_root_handlers = list(root.handlers)
    saved_dazzle_handlers = list(dazzle_log.handlers)
    saved_dazzle_level = dazzle_log.level
    saved_dazzle_propagate = dazzle_log.propagate

    def clear() -> None:
        root.handlers = []
        dazzle_log.handlers = []
        dazzle_log.propagate = True  # reset to default before test

    clear()
    yield clear
    root.handlers = saved_root_handlers
    dazzle_log.handlers = saved_dazzle_handlers
    dazzle_log.level = saved_dazzle_level
    dazzle_log.propagate = saved_dazzle_propagate


def test_attaches_handler_when_nothing_configured(_clean_loggers) -> None:
    """The common bare-uvicorn boot case — no handlers anywhere → we
    attach one to `dazzle` so framework tags reach stderr."""
    _clean_loggers()
    assert ensure_dazzle_logging_configured() is True
    dazzle_log = logging.getLogger("dazzle")
    assert len(dazzle_log.handlers) == 1
    assert isinstance(dazzle_log.handlers[0], logging.StreamHandler)


def test_noop_when_root_has_handlers(_clean_loggers) -> None:
    """If the project already called `logging.basicConfig` or
    otherwise attached a root handler, we don't touch logging — they
    own the config."""
    _clean_loggers()
    root = logging.getLogger()
    root.addHandler(logging.StreamHandler())
    assert ensure_dazzle_logging_configured() is False
    dazzle_log = logging.getLogger("dazzle")
    assert dazzle_log.handlers == []


def test_noop_when_dazzle_already_has_handlers(_clean_loggers) -> None:
    """If a prior call already configured the dazzle logger (or the
    project attached its own dazzle-specific handler), don't double-up."""
    _clean_loggers()
    dazzle_log = logging.getLogger("dazzle")
    dazzle_log.addHandler(logging.StreamHandler())
    assert ensure_dazzle_logging_configured() is False
    assert len(dazzle_log.handlers) == 1


def test_idempotent_across_repeated_calls(_clean_loggers) -> None:
    """Acceptance criterion from the issue: calling twice doesn't
    duplicate handlers."""
    _clean_loggers()
    assert ensure_dazzle_logging_configured() is True
    # Second call is a no-op because the first attached a handler.
    assert ensure_dazzle_logging_configured() is False
    assert len(logging.getLogger("dazzle").handlers) == 1


def test_default_level_is_info(_clean_loggers) -> None:
    _clean_loggers()
    ensure_dazzle_logging_configured()
    assert logging.getLogger("dazzle").level == logging.INFO


def test_explicit_level_overrides_default(_clean_loggers) -> None:
    _clean_loggers()
    ensure_dazzle_logging_configured(level="DEBUG")
    assert logging.getLogger("dazzle").level == logging.DEBUG


def test_env_var_overrides_default(_clean_loggers, monkeypatch) -> None:
    _clean_loggers()
    monkeypatch.setenv("DAZZLE_LOG_LEVEL", "WARNING")
    ensure_dazzle_logging_configured()
    assert logging.getLogger("dazzle").level == logging.WARNING


def test_explicit_level_beats_env_var(_clean_loggers, monkeypatch) -> None:
    """Explicit arg wins over env var — entry points can override
    the operator-controlled env default if they need to."""
    _clean_loggers()
    monkeypatch.setenv("DAZZLE_LOG_LEVEL", "WARNING")
    ensure_dazzle_logging_configured(level="ERROR")
    assert logging.getLogger("dazzle").level == logging.ERROR


def test_invalid_env_var_falls_back_to_info(_clean_loggers, monkeypatch) -> None:
    """A garbled DAZZLE_LOG_LEVEL must not crash framework boot —
    fall through to INFO and let the operator notice the wrong
    setting via log output."""
    _clean_loggers()
    monkeypatch.setenv("DAZZLE_LOG_LEVEL", "VERBOSE_PLZ")
    ensure_dazzle_logging_configured()
    assert logging.getLogger("dazzle").level == logging.INFO


def test_dazzle_logger_does_not_propagate(_clean_loggers) -> None:
    """When the project later adds a root handler, we should NOT
    re-emit framework tags through it — the dazzle logger has its
    own handler. propagate=False prevents the double-emit."""
    _clean_loggers()
    ensure_dazzle_logging_configured()
    assert logging.getLogger("dazzle").propagate is False


def test_emitted_records_reach_the_attached_handler(_clean_loggers, capsys) -> None:
    """End-to-end smoke: a logger.info() call on a `dazzle.*` child
    logger reaches stderr after the helper runs. The whole point of
    the helper is that this works on a bare-uvicorn boot."""
    _clean_loggers()
    ensure_dazzle_logging_configured()
    child = logging.getLogger("dazzle.http.runtime.page_routes")
    child.info("onboarding.inject:rendered surface=x guide=g step=s")
    captured = capsys.readouterr()
    assert "onboarding.inject:rendered" in captured.err
