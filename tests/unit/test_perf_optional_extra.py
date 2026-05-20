"""Regression guard for #1164 — the `perf` extra must be optional.

`dazzle.cli` imports `dazzle.perf` at module load (tracer init at CLI
entry, #1158). `opentelemetry` ships only in the optional `perf`
extra, so a plain `pip install dazzle-dsl` must still yield a working
CLI. These tests run a fresh interpreter with `opentelemetry` masked.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

# Installed first thing in the child interpreter: makes any
# `import opentelemetry...` raise, simulating an install without `[perf]`.
_MASK = """
import builtins
_real = builtins.__import__
def _blocked(name, *a, **k):
    if name.split('.')[0] == 'opentelemetry':
        raise ModuleNotFoundError("No module named 'opentelemetry'")
    return _real(name, *a, **k)
builtins.__import__ = _blocked
"""


def _run_without_otel(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _MASK + textwrap.dedent(body)],
        capture_output=True,
        text=True,
    )


def test_cli_imports_without_opentelemetry() -> None:
    result = _run_without_otel(
        """
        import dazzle.cli  # must not raise
        print('ok')
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_dazzle_span_is_noop_without_opentelemetry() -> None:
    result = _run_without_otel(
        """
        from dazzle.perf import dazzle_span
        with dazzle_span('phase.op', entity='Task') as span:
            assert span is None
        print('ok')
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_configure_tracer_raises_clear_error_without_opentelemetry() -> None:
    result = _run_without_otel(
        """
        from pathlib import Path
        from dazzle.perf import configure_tracer
        try:
            configure_tracer(run_id='r', db_path=Path('/tmp/unused.db'))
        except RuntimeError as exc:
            assert "perf" in str(exc) and "pip install" in str(exc), exc
            print('ok')
        else:
            raise AssertionError('configure_tracer should have raised')
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
