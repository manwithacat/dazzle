"""Verify ``instrument_app`` is called on the FastAPI app when the
``DAZZLE_PERF_ENABLED`` env var is set, and not otherwise.

After #1158 the tracer bootstrap lives in ``dazzle.perf.bootstrap``
so it can be called at CLI entry (before DSL parse).  The server-side
``_maybe_configure_tracer`` now delegates there; these tests cover both
the bootstrap module directly and the ``_maybe_instrument_for_perf``
helper that still lives in server.py.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi import FastAPI


def test_instrumentation_skipped_when_env_unset() -> None:
    from dazzle.http.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    with patch.dict(os.environ, {}, clear=True):
        _maybe_instrument_for_perf(app)
    # Calling with the env off is harmless and emits nothing.


def test_instrumentation_runs_when_env_set() -> None:
    from dazzle.http.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    called: list[FastAPI] = []

    def fake_instrument(received_app: FastAPI) -> None:
        called.append(received_app)

    with patch.dict(os.environ, {"DAZZLE_PERF_ENABLED": "1"}):
        # #1438: instrument_app is now imported at server module-top, so patch it
        # in the consumer's namespace (where _maybe_instrument_for_perf binds it),
        # not at the source module.
        with patch("dazzle.http.runtime.server.instrument_app", side_effect=fake_instrument):
            _maybe_instrument_for_perf(app)
    assert called == [app]


def test_tracer_initialised_when_perf_db_env_set(tmp_path) -> None:
    """Bootstrap module configures tracer when all env vars are present."""
    from dazzle.perf.bootstrap import maybe_configure_tracer

    db = tmp_path / "run.db"
    env = {
        "DAZZLE_PERF_ENABLED": "1",
        "DAZZLE_PERF_DB": str(db),
        "DAZZLE_PERF_RUN_ID": "r1",
    }
    called: dict[str, object] = {}

    def fake_configure(**kwargs):
        called.update(kwargs)

    with (
        patch.dict(os.environ, env),
        patch("dazzle.perf.tracer.configure_tracer", side_effect=fake_configure),
    ):
        maybe_configure_tracer()

    assert called["run_id"] == "r1"
    assert called["db_path"] == db
    # batch=False → SimpleSpanProcessor: spans persist synchronously, so
    # a short trace run can't lose them when the server is terminated
    # before BatchSpanProcessor's flush timer fires.
    assert called["batch"] is False


def test_tracer_skipped_when_env_unset() -> None:
    """Bootstrap module is a no-op when DAZZLE_PERF_ENABLED is absent."""
    from dazzle.perf.bootstrap import maybe_configure_tracer

    called = False

    def fake_configure(**kwargs):
        nonlocal called
        called = True

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("dazzle.perf.tracer.configure_tracer", side_effect=fake_configure),
    ):
        maybe_configure_tracer()

    assert not called


def test_server_maybe_configure_tracer_delegates_to_bootstrap() -> None:
    """server._maybe_configure_tracer delegates to perf.bootstrap."""
    from dazzle.http.runtime.server import _maybe_configure_tracer

    called: list[bool] = []

    def fake_bootstrap() -> None:
        called.append(True)

    # #1438: maybe_configure_tracer is now imported at server module-top — patch
    # it in the consumer's namespace, not at the source module.
    with patch("dazzle.http.runtime.server.maybe_configure_tracer", side_effect=fake_bootstrap):
        _maybe_configure_tracer()

    assert called, "_maybe_configure_tracer did not delegate to bootstrap"
