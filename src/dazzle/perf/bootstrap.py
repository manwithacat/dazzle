"""Process-start hook for the perf tracer.

Wires the SQLite exporter when ``DAZZLE_PERF_ENABLED`` is set in the
environment. Called at CLI entry so framework-boot spans (DSL parse,
route generation) are captured — by the time ``_create_app`` ran
previously, those phases had already executed against the no-op tracer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def maybe_configure_tracer() -> None:
    """Configure the OTel tracer if ``DAZZLE_PERF_ENABLED=1``.

    No-op when the env var is unset. Idempotent — repeated calls are
    harmless because OTel's set_tracer_provider tolerates re-assignment
    (warning logged, no exception).
    """
    if os.environ.get("DAZZLE_PERF_ENABLED") != "1":
        return
    db_str = os.environ.get("DAZZLE_PERF_DB")
    run_id = os.environ.get("DAZZLE_PERF_RUN_ID")
    if not db_str or not run_id:
        return
    from dazzle.perf.tracer import configure_tracer

    configure_tracer(
        run_id=run_id,
        db_path=Path(db_str),
        batch=True,
        command_line=" ".join(sys.argv),
    )
