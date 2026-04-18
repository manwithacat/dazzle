"""Server fixture for INTERACTION_WALK.

Spawns ``python -m dazzle serve --local`` against a chosen example-app
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

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dazzle.qa.server import AppConnection

# Defaults — tunable via env in CI if cold starts are consistently
# slower than local dev. Not exposed as args to keep the fixture
# signature narrow; callers with unusual needs can construct
# ``AppConnection`` themselves.
_RUNTIME_POLL_TIMEOUT_SECONDS = 45.0
_RUNTIME_POLL_INTERVAL_SECONDS = 0.3


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


@contextmanager
def launch_interaction_server(
    project_root: Path,
    *,
    timeout: float = _RUNTIME_POLL_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> Iterator[AppConnection]:
    """Start ``dazzle serve --local`` in ``project_root`` and yield a
    live :class:`AppConnection`. Tears down on context exit.

    Requires ``DATABASE_URL`` and ``REDIS_URL`` in the environment (or
    passed via ``extra_env``) because ``--local`` skips the Docker
    bring-up. For CI wiring, those come from the workflow's Postgres
    + Redis service containers — see the design doc, step 6.

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

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    # start_new_session=True puts the server in its own process group,
    # so SIGTERM reaches uvicorn + any child workers at teardown. Same
    # pattern as ModeRunner.
    proc = subprocess.Popen(
        [sys.executable, "-m", "dazzle", "serve", "--local"],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        _wait_for_runtime_file(project_root, timeout=timeout)
        conn = AppConnection.from_runtime_file(project_root)
        # Promote the external connection to an owned one so teardown
        # terminates the subprocess via AppConnection.stop().
        conn.process = proc
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
        # Clean up runtime.json so the next run can't see stale data.
        if runtime_path.exists():
            try:
                runtime_path.unlink()
            except OSError:
                pass
