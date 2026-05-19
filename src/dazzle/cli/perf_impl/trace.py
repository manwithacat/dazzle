"""``dazzle perf trace`` — boot a Dazzle app under tracing.

Plans a per-run SQLite path under ``.dazzle/perf/``, sets the env vars
that the runtime reads (``DAZZLE_PERF_ENABLED=1``,
``DAZZLE_PERF_DB``, ``DAZZLE_PERF_RUN_ID``), and shells out to a small
runner that:

1. Configures the global tracer in the *child* uvicorn process.
2. Boots ``dazzle serve --local`` on a free port.
3. Hits each ``--url`` (synchronously) once.
4. Sleeps for ``--duration`` seconds so additional traffic can land.
5. Shuts the server down cleanly.
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.run_id import make_run_id


def trace_command(
    urls: list[str] = typer.Option(
        [], "--url", help="URLs to hit during the trace run (repeatable)."
    ),
    duration: int = typer.Option(
        0,
        "--duration",
        help="Seconds to keep the server alive after URL hits. "
        "0 means exit immediately after the URL hits complete.",
    ),
    report: bool = typer.Option(
        False, "--report", help="Run `dazzle perf report` against the new run when done."
    ),
) -> None:
    """Boot the app under tracing and capture a single run."""
    if not urls and duration <= 0:
        typer.echo(
            "Provide at least one --url or a non-zero --duration. "
            "Run `dazzle perf trace --help` for usage."
        )
        raise typer.Exit(1)

    perf_dir = Path.cwd() / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    run_id = make_run_id()
    db_path = perf_dir / f"{run_id}.db"

    _execute_trace_run(
        run_id=run_id,
        db_path=db_path,
        urls=tuple(urls),
        duration=duration,
    )

    typer.echo(f"Trace saved: {db_path}")

    if report:
        from dazzle.cli.perf_impl.report import report_command

        report_command(run=run_id, fmt="md", top=10, baseline=None)


def _execute_trace_run(
    *,
    run_id: str,
    db_path: Path,
    urls: tuple[str, ...],
    duration: int,
) -> None:
    """Spawn uvicorn under tracing, drive the URLs, return on shutdown."""
    import http.client
    import os
    import subprocess
    import sys
    import time

    # Force the dev server onto known ports so the URL hits below can
    # reach it. ``dazzle serve`` auto-assigns ports when not specified,
    # which would otherwise leave us guessing where to send traffic.
    _TRACE_HOST = "127.0.0.1"
    _TRACE_PORT = 3000
    _API_PORT = 8000

    env = {
        **os.environ,
        "DAZZLE_PERF_ENABLED": "1",
        "DAZZLE_PERF_DB": str(db_path),
        "DAZZLE_PERF_RUN_ID": run_id,
    }

    # Boot `dazzle serve --local` in a subprocess. Local mode skips
    # Docker spin-up so the trace run starts in seconds.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dazzle.cli",
            "serve",
            "--local",
            "--port",
            str(_TRACE_PORT),
            "--api-port",
            str(_API_PORT),
        ],
        env=env,
    )

    def _wait_for_server(timeout: float = 20.0) -> bool:
        """Poll the dev server until it answers, or give up."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return False  # subprocess exited before becoming ready
            try:
                conn = http.client.HTTPConnection(_TRACE_HOST, _TRACE_PORT, timeout=1)
                conn.request("GET", "/")
                conn.getresponse().read()
                conn.close()
                return True
            except OSError:
                time.sleep(0.5)
        return False

    def _fetch_path(raw: str) -> None:
        """GET a single path from the local dev server."""
        if raw.startswith("http://") or raw.startswith("https://"):
            from urllib.parse import urlparse

            path = urlparse(raw).path or "/"
        else:
            path = raw if raw.startswith("/") else f"/{raw}"
        try:
            conn = http.client.HTTPConnection(_TRACE_HOST, _TRACE_PORT, timeout=10)
            conn.request("GET", path)
            conn.getresponse().read()
            conn.close()
        except OSError as exc:
            typer.echo(f"  path {path} failed: {exc}")

    try:
        if not _wait_for_server():
            typer.echo(
                "  warning: dev server didn't answer on "
                f"http://{_TRACE_HOST}:{_TRACE_PORT}/ within 20s — "
                "URL hits skipped. Boot-phase traces will still land."
            )
        else:
            # Server is up. Hit each URL once. Failures are non-fatal —
            # the trace captures the error span and the report surfaces it.
            for url in urls:
                _fetch_path(url)
        if duration > 0:
            typer.echo(f"Server up; collecting traces for {duration}s. Hit Ctrl-C to stop early.")
            time.sleep(duration)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
