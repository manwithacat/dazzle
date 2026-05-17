"""#1131 (regression of #841): EventBusProcessAdapter scheduler must
resolve ParamRef on `cron` and `interval_seconds` before storing them.

Without this, the scheduler loop calls ``str.split`` / arithmetic on a
raw ``ParamRef`` and dies with:

    AttributeError: 'ParamRef' object has no attribute 'split'

The original #841 fix patched ``SLAManager._tier_seconds`` only. The
EventBus adapter was introduced after that fix landed and copied the
pre-fix pattern of storing ``ScheduleSpec.cron`` verbatim, reviving
the exact same shape on v0.71.23 (CyFuture nightly logs).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from dazzle.core.ir.params import ParamRef
from dazzle.core.ir.process import ScheduleSpec
from dazzle.core.process.eventbus_adapter import (
    EventBusProcessAdapter,
    _resolve_param_ref,
)

# ---------------------------------------------------------------------------
# _resolve_param_ref — pure helper
# ---------------------------------------------------------------------------


def test_resolve_param_ref_unwraps_to_default() -> None:
    ref = ParamRef(param_type="str", key="timer.cron", default="*/5 * * * *")
    assert _resolve_param_ref(ref) == "*/5 * * * *"


def test_resolve_param_ref_returns_literal_unchanged() -> None:
    assert _resolve_param_ref("0 8 * * *") == "0 8 * * *"
    assert _resolve_param_ref(60) == 60
    assert _resolve_param_ref(None) is None


# ---------------------------------------------------------------------------
# register_schedule / sync_schedules_from_appspec
# ---------------------------------------------------------------------------


import pytest  # noqa: E402  (kept here so the helper tests above don't need it)


@pytest.mark.asyncio
async def test_register_schedule_resolves_paramref_on_cron() -> None:
    """A ScheduleSpec whose ``cron`` is a ParamRef must end up in the
    runtime dict as the resolved literal — the scheduler loop calls
    ``str.split`` on it and would crash otherwise."""
    store = MagicMock()
    adapter = EventBusProcessAdapter(store=store)

    spec = ScheduleSpec(
        name="nightly",
        cron=ParamRef(param_type="str", key="nightly.cron", default="0 3 * * *"),
    )
    await adapter.register_schedule(spec)

    stored = adapter._schedules["nightly"]
    assert stored["cron"] == "0 3 * * *"
    assert isinstance(stored["cron"], str), (
        "ParamRef must be resolved before storage — scheduler loop "
        "calls str.split on this value (#1131)"
    )


def test_sync_schedules_from_appspec_resolves_paramref_on_cron() -> None:
    """The AppSpec-sync path is the more common entry point in real apps;
    it must apply the same resolution as register_schedule."""
    store = MagicMock()
    adapter = EventBusProcessAdapter(store=store)

    spec = ScheduleSpec(
        name="hourly",
        cron=ParamRef(param_type="str", key="hourly.cron", default="0 * * * *"),
    )
    appspec = MagicMock(schedules=[spec])

    count = adapter.sync_schedules_from_appspec(appspec)
    assert count == 1
    assert adapter._schedules["hourly"]["cron"] == "0 * * * *"


@pytest.mark.asyncio
async def test_scheduler_loop_does_not_crash_on_resolved_cron(caplog) -> None:
    """Regression check: with the resolver in place, ``_cron_matches``
    receives a real str and the loop runs to completion instead of
    raising ``AttributeError: 'ParamRef' object has no attribute 'split'``."""
    store = MagicMock()
    adapter = EventBusProcessAdapter(store=store)

    spec = ScheduleSpec(
        name="every_minute",
        cron=ParamRef(param_type="str", key="cron", default="* * * * *"),
    )
    await adapter.register_schedule(spec)

    # Drive _cron_matches against a real datetime — if the ParamRef leaked
    # through, this raises AttributeError; the helper short-circuits the
    # split() before we ever get here.
    from datetime import UTC, datetime

    with caplog.at_level(logging.WARNING):
        assert adapter._cron_matches(adapter._schedules["every_minute"]["cron"], datetime.now(UTC))

    # No "Scheduler loop error" lines emitted from this path.
    assert "Scheduler loop error" not in caplog.text


def test_scheduler_loop_error_logs_traceback() -> None:
    """#1131 ask #1: the bare ``logger.warning("Scheduler loop error: %s", e)``
    hid call-site context. ``exc_info=True`` keyword must be present so
    consumers can pinpoint the failing schedule."""
    import inspect

    from dazzle.core.process import eventbus_adapter

    src = inspect.getsource(eventbus_adapter.EventBusProcessAdapter._scheduler_loop)
    assert "exc_info=True" in src, (
        "Scheduler loop must log with exc_info=True (#1131 ask #1) — "
        "bare messages cost hours of consumer log triage when the next "
        "regression of this class lands."
    )
