"""Server fixture for INTERACTION_WALK.

Spawns ``python -m dazzle serve`` against a chosen example-app
directory, waits for it to write ``.dazzle/runtime.json``, and yields
the :class:`dazzle.qa.server.AppConnection`. Tears down cleanly on
session end.

This is the sync, interaction-test flavour of
:class:`dazzle.e2e.runner.ModeRunner`. We deliberately **don't** reuse
``ModeRunner`` because:

- ``ModeRunner`` is async; interaction tests use Playwright's sync API.
- ``ModeRunner`` applies DB policy, takes a lock file, wires atexit
  handlers. Great for fitness runs; overkill for a read-heavy browser
  harness where the test is one session-scoped server.

Both still point at the same ``AppConnection`` type and the same
``.dazzle/runtime.json`` discovery protocol — when ``dazzle serve``
changes how it exposes its URLs, both fixtures get it for free.

See ``docs/proposals/interaction-walk-harness.md`` (step 3) for the
design rationale.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from dazzle.qa.server import AppConnection

logger = logging.getLogger(__name__)

# Defaults — tunable via env in CI if cold starts are consistently
# slower than local dev. Not exposed as args to keep the fixture
# signature narrow; callers with unusual needs can construct
# ``AppConnection`` themselves.
_RUNTIME_POLL_TIMEOUT_SECONDS = 45.0
_RUNTIME_POLL_INTERVAL_SECONDS = 0.3
# The server writes runtime.json slightly BEFORE its uvicorn worker
# is actually accepting TCP connections. Playwright's page.goto()
# immediately hits ERR_CONNECTION_REFUSED if we don't wait. Poll the
# UI root until it answers 200 before yielding.
_HEALTH_POLL_TIMEOUT_SECONDS = 30.0
_HEALTH_POLL_INTERVAL_SECONDS = 0.3


class InteractionServerError(RuntimeError):
    """Raised when the server fixture can't get to a live URL pair.

    Distinct exception type so pytest fixtures can ``xfail`` on
    setup failures without conflating them with interaction-assertion
    failures (exit code 2 vs 1 in the CLI; see design doc).
    """


def _wait_for_runtime_file(project_root: Path, timeout: float) -> Path:
    """Block until ``project_root/.dazzle/runtime.json`` exists.

    Returns the path. Raises :class:`InteractionServerError` on timeout.
    """
    runtime_path = project_root / ".dazzle" / "runtime.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runtime_path.exists():
            return runtime_path
        time.sleep(_RUNTIME_POLL_INTERVAL_SECONDS)
    raise InteractionServerError(
        f"dazzle serve did not write {runtime_path} within {timeout:.0f}s. "
        f"Check the subprocess's stderr for crash/import errors."
    )


def _wait_for_server_ready(site_url: str, timeout: float) -> None:
    """Poll ``site_url`` until it accepts HTTP connections, or timeout.

    The server writes ``runtime.json`` slightly before uvicorn is
    actually bound to the port — Playwright's ``page.goto`` hits
    ``ERR_CONNECTION_REFUSED`` in that window. Poll here until the
    root URL answers (any 2xx/3xx/4xx counts as "listening") so the
    caller can safely navigate.

    Raises :class:`InteractionServerError` if nothing listens after
    ``timeout`` seconds.
    """
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover — httpx is in core deps
        raise InteractionServerError(
            "httpx not installed — required for server readiness polling"
        ) from exc

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    last_5xx_status: int | None = None
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(site_url, follow_redirects=False)
                # Any response (including 3xx redirect or 4xx auth
                # gate) means the server is bound and accepting
                # connections. That's all we need to avoid the
                # ``ERR_CONNECTION_REFUSED`` race.
                if resp.status_code < 500:
                    return
                # Bound, but the root page itself is erroring. Record it
                # so the timeout message points at the APP, not the port.
                last_5xx_status = resp.status_code
        except Exception as exc:  # ConnectError, ConnectTimeout, etc.
            last_error = exc
        time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
    # Two genuinely different failures, two messages (#1423): a persistent
    # 5xx means uvicorn IS bound but GET / raises — don't say "never bound"
    # and send the next debugger hunting a port/infra ghost. The real
    # traceback is in the managed-server log.
    if last_5xx_status is not None:
        raise InteractionServerError(
            f"Server at {site_url} is bound but GET / returned "
            f"{last_5xx_status} for {timeout:.0f}s — the app boots but its "
            f"root page raises. This is an APP error, not a bind failure: "
            f"read the traceback in .dazzle/managed-server-logs/."
        )
    raise InteractionServerError(
        f"Server at {site_url} did not accept connections within "
        f"{timeout:.0f}s (last error: {last_error!r}). The runtime.json "
        f"was written but uvicorn never bound to the port."
    )


@contextmanager
def launch_interaction_server(
    project_root: Path,
    *,
    timeout: float = _RUNTIME_POLL_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> Iterator[AppConnection]:
    """Start ``dazzle serve`` in ``project_root`` and yield a
    live :class:`AppConnection`. Tears down on context exit.

    Requires ``DATABASE_URL`` and ``REDIS_URL`` in the environment (or
    passed via ``extra_env``) — ``dazzle serve`` runs against a
    caller-provided Postgres + Redis. For CI wiring, those come from the
    workflow's Postgres + Redis service containers — see the design doc, step 6.

    Args:
        project_root: Directory containing ``dazzle.toml``.
        timeout: Maximum seconds to wait for runtime.json.
        extra_env: Optional extra env vars merged into the subprocess
            environment (DATABASE_URL, REDIS_URL, etc.).

    Yields:
        A connected :class:`AppConnection`. ``process`` is set — do
        not call ``conn.stop()`` yourself; the context manager handles
        teardown.

    Raises:
        InteractionServerError: On startup timeout or missing
            runtime.json.
    """
    if not (project_root / "dazzle.toml").is_file():
        raise InteractionServerError(
            f"{project_root} has no dazzle.toml — not a valid project root."
        )

    # Clear stale runtime.json so we don't mistake a prior run's URL
    # pair for this one.
    runtime_path = project_root / ".dazzle" / "runtime.json"
    if runtime_path.exists():
        runtime_path.unlink()

    # Defensive PG-session cleanup before launch (#1072 Bug A — same
    # class as the ModeRunner fix in v0.67.153). Terminates any
    # `idle in transaction` sessions left over from a prior subprocess
    # that died holding locks, so this subprocess's CREATE INDEX /
    # migration queries don't block on phantom transactions. Best-
    # effort; failures swallowed.
    with suppress(Exception):
        from dazzle.cli.dotenv import apply_project_infra_urls, load_project_dotenv
        from dazzle.e2e._pg_cleanup import terminate_stale_sessions

        load_project_dotenv(project_root)
        # Managed servers must use the project under test's DB even when the
        # host shell still holds another example's DATABASE_URL (multi-app
        # agent hosts / residual exports after invoice_ops work).
        apply_project_infra_urls(project_root)
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url:
            terminate_stale_sessions(db_url)

    # Ensure parent process has project infra before env.copy() for the child.
    from dazzle.cli.dotenv import (
        apply_project_infra_urls,
        load_project_dotenv,
        project_infra_env,
    )

    load_project_dotenv(project_root)
    apply_project_infra_urls(project_root)

    env = os.environ.copy()
    # #1397: the managed verify/test server is inherently single-process. A host
    # with WEB_CONCURRENCY set (e.g. Heroku = 3) would otherwise make uvicorn
    # pick that worker count via the app-object path and REFUSE to bind
    # (multi-worker needs an import string, not an app object) — the server never
    # comes up and the interaction times out. Force single-process here.
    env["WEB_CONCURRENCY"] = "1"
    if extra_env:
        env.update(extra_env)
    # Project .env infra always wins for managed serve (even over extra_env).
    env.update(project_infra_env(project_root))

    # start_new_session=True puts the server in its own process group,
    # so SIGTERM reaches uvicorn + any child workers at teardown. Same
    # pattern as ModeRunner.
    # #1072 Bug A root cause (cycle 134): the previous `stdout=PIPE,
    # stderr=PIPE` setup caused a pipe-buffer deadlock — when the
    # subprocess emits enough output (e.g. repeated psycopg tracebacks
    # from a schema mismatch), the ~64KB OS pipe buffer fills, the
    # subprocess blocks on its next write, and uvicorn's worker hangs
    # → request handlers stop responding → contract verifier times out.
    # Mirror ModeRunner's pattern: write to a log file (unbounded sink)
    # so the subprocess can never block on output. The log is captured
    # in the project's `.dazzle/managed-server-logs/` for debugging
    # post-run failures.
    log_dir = project_root / ".dazzle" / "managed-server-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import UTC
    from datetime import datetime as _dt

    _ts = _dt.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    _log_path = log_dir / f"managed-{_ts}.log"
    _log_fh = _log_path.open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "dazzle", "serve"],
        cwd=project_root,
        env=env,
        stdout=_log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    prior_test_secret = os.environ.get("DAZZLE_TEST_SECRET")
    try:
        _wait_for_runtime_file(project_root, timeout=timeout)
        conn = AppConnection.from_runtime_file(project_root)
        # Promote the external connection to an owned one so teardown
        # terminates the subprocess via AppConnection.stop().
        conn.process = proc
        # Wait for the TCP port to actually accept connections —
        # runtime.json is written slightly before uvicorn binds.
        _wait_for_server_ready(conn.site_url, timeout=_HEALTH_POLL_TIMEOUT_SECONDS)
        # The subprocess may have generated its own DAZZLE_TEST_SECRET
        # (see serve.py:311-317) and written it to runtime.json. Clients
        # that run in *this* parent process — HtmxClient, SessionManager,
        # anything driving the managed server — read the secret via
        # os.environ, so we need to propagate the subprocess's secret
        # into our own env. Without this the parent sends no X-Test-
        # Secret header and every /__test__/authenticate call fails 401,
        # which is what broke the contracts-gate CI job on managed runs
        # where DAZZLE_TEST_SECRET isn't pre-exported.
        from dazzle.cli.runtime_impl.ports import read_runtime_test_secret

        subprocess_secret = read_runtime_test_secret(project_root)
        if subprocess_secret:
            os.environ["DAZZLE_TEST_SECRET"] = subprocess_secret
        yield conn
    finally:
        # AppConnection.stop() handles terminate + wait + kill with
        # the right timeouts. If we never got a connection (failed
        # before yielding), terminate the subprocess directly.
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        # Close the log file handle (#1072 — buffer-deadlock fix).
        try:
            _log_fh.close()
        except OSError:
            pass
        # Restore DAZZLE_TEST_SECRET so we don't leak the subprocess's
        # value into whatever the parent does next.
        if prior_test_secret is None:
            os.environ.pop("DAZZLE_TEST_SECRET", None)
        else:
            os.environ["DAZZLE_TEST_SECRET"] = prior_test_secret
        # Clean up runtime.json so the next run can't see stale data.
        if runtime_path.exists():
            try:
                runtime_path.unlink()
            except OSError:
                pass

        # Defensive PG-session cleanup on exit (#1072 Bug A) — even after
        # SIGTERM, the subprocess's SQLAlchemy session pool may not have
        # finalised. Sweep on the way out so the next run starts clean.
        with suppress(Exception):
            from dazzle.e2e._pg_cleanup import terminate_stale_sessions

            db_url = os.environ.get("DATABASE_URL", "")
            if db_url:
                terminate_stale_sessions(db_url)
