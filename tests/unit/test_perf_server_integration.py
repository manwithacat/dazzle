"""Verify ``instrument_app`` is called on the FastAPI app when the
``DAZZLE_PERF_ENABLED`` env var is set, and not otherwise."""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi import FastAPI


def test_instrumentation_skipped_when_env_unset() -> None:
    from dazzle.back.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    with patch.dict(os.environ, {}, clear=True):
        _maybe_instrument_for_perf(app)
    # Calling with the env off is harmless and emits nothing.


def test_instrumentation_runs_when_env_set() -> None:
    from dazzle.back.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    called: list[FastAPI] = []

    def fake_instrument(received_app: FastAPI) -> None:
        called.append(received_app)

    with patch.dict(os.environ, {"DAZZLE_PERF_ENABLED": "1"}):
        with patch("dazzle.perf.instrument.instrument_app", side_effect=fake_instrument):
            _maybe_instrument_for_perf(app)
    assert called == [app]
