"""Tests for #1192 slice 2 — OTLP push export.

``configure_tracer`` reads ``DAZZLE_OTEL_ENDPOINT`` from the environment.
When set, it attaches a ``BatchSpanProcessor(OTLPSpanExporter(...))``
onto the tracer provider **in addition to** the local SQLite span
processor — push and local-on-disk run in parallel. When unset, the
function executes the same code path as before the slice landed.

These tests pin three branches:

  * **No env var** — the provider has exactly the local SQLite
    processor; no OTLP exporter is attached.
  * **Env var set + optional extra installed** — an
    ``OTLPSpanExporter`` is attached alongside the SQLite one. The
    local exporter is not replaced.
  * **Env var set + optional extra missing** — boot continues, a single
    WARNING-level log names the ``observability`` extra, and the local
    SQLite processor is still wired.

Companion regression guard: the ``observability`` extra must remain
optional. ``dazzle.cli`` boot under a plain install (no ``[perf]``)
already exercises that — see ``test_perf_optional_extra.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from dazzle.perf.exporter import SQLiteSpanExporter
from dazzle.perf.tracer import configure_tracer, reset_tracer

# Skip the whole module when ``opentelemetry`` (the ``perf`` extra) is
# not installed; ``configure_tracer`` would raise ``RuntimeError`` and
# every test would be uninformative. ``test_perf_optional_extra.py``
# covers the "no opentelemetry at all" case in its own subprocess.
pytest.importorskip("opentelemetry.sdk.trace")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _processors(provider: Any) -> tuple[Any, ...]:
    """Return the configured span processors on ``provider``.

    OTel doesn't expose a public accessor; reaching into
    ``_active_span_processor._span_processors`` is the same path the
    SDK's own tests use. Acceptable in test code.
    """
    return tuple(provider._active_span_processor._span_processors)


def _exporters(provider: Any) -> tuple[Any, ...]:
    """Return the exporter instance wrapped by each processor."""
    return tuple(p.span_exporter for p in _processors(provider))


@pytest.fixture(autouse=True)
def _reset_tracer_after_test() -> None:
    """Tracer state is module-global; reset between tests."""
    yield
    reset_tracer()


# ---------------------------------------------------------------------------
# 1. No env var — unchanged behaviour
# ---------------------------------------------------------------------------


def test_no_env_var_leaves_only_sqlite_exporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``DAZZLE_OTEL_ENDPOINT`` is unset, the provider must have
    exactly one processor wrapping the SQLite exporter. No OTLP code
    path runs.
    """
    monkeypatch.delenv("DAZZLE_OTEL_ENDPOINT", raising=False)
    provider = configure_tracer(
        run_id="r-noenv",
        db_path=tmp_path / "run.db",
        batch=False,
    )
    exporters = _exporters(provider)
    assert len(exporters) == 1, exporters
    assert isinstance(exporters[0], SQLiteSpanExporter)


# ---------------------------------------------------------------------------
# 2. Env var set + extra installed — OTLP attached alongside SQLite
# ---------------------------------------------------------------------------


def test_env_var_attaches_otlp_alongside_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the env var set and the ``observability`` extra installed,
    the OTLP exporter is attached *in addition to* the SQLite exporter.
    """
    pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    monkeypatch.setenv("DAZZLE_OTEL_ENDPOINT", "https://otel.example.com/v1/traces")
    provider = configure_tracer(
        run_id="r-otlp",
        db_path=tmp_path / "run.db",
        batch=False,
    )
    exporters = _exporters(provider)
    assert len(exporters) == 2, exporters
    # The local SQLite exporter is preserved — additive, not replacement.
    assert any(isinstance(e, SQLiteSpanExporter) for e in exporters)
    # And the OTLP exporter is now attached too.
    assert any(isinstance(e, OTLPSpanExporter) for e in exporters)


def test_otlp_exporter_uses_endpoint_verbatim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint string must be passed through unchanged to the
    exporter — operators provide the full URL, and the framework does
    not strip or transform it.
    """
    pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    url = "https://collector.internal.example/v1/traces"
    monkeypatch.setenv("DAZZLE_OTEL_ENDPOINT", url)
    provider = configure_tracer(
        run_id="r-url",
        db_path=tmp_path / "run.db",
        batch=False,
    )
    otlp = next(e for e in _exporters(provider) if isinstance(e, OTLPSpanExporter))
    # The OTel exporter stores the resolved endpoint on a private
    # attribute; check whichever names are present without coupling
    # to a single SDK minor.
    stored = getattr(otlp, "_endpoint", None) or getattr(otlp, "endpoint", None)
    assert stored == url, stored


# ---------------------------------------------------------------------------
# 3. Env var set + extra missing — graceful WARNING, no crash
# ---------------------------------------------------------------------------


def test_missing_extra_logs_warning_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the optional ``observability`` extra is not importable, boot
    must continue. A single WARNING is logged naming the extra, and the
    local SQLite exporter remains wired.
    """
    # Mask the OTLP exporter module so the import inside
    # ``_maybe_attach_otlp_processor`` raises ``ModuleNotFoundError``.
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        None,
    )
    monkeypatch.setenv("DAZZLE_OTEL_ENDPOINT", "https://otel.example.com/v1/traces")

    with caplog.at_level(logging.WARNING, logger="dazzle.perf.tracer"):
        provider = configure_tracer(
            run_id="r-missing",
            db_path=tmp_path / "run.db",
            batch=False,
        )

    # Local exporter still wired — no crash, no replacement.
    exporters = _exporters(provider)
    assert len(exporters) == 1, exporters
    assert isinstance(exporters[0], SQLiteSpanExporter)

    # Exactly one WARNING, naming the extra.
    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING and r.name == "dazzle.perf.tracer"
    ]
    assert len(warnings) == 1, warnings
    msg = warnings[0].getMessage()
    assert "observability" in msg
    assert "pip install" in msg
    assert "DAZZLE_OTEL_ENDPOINT" in msg
