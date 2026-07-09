"""``dazzle perf trace`` — boot a Dazzle app under tracing.

Plans a per-run SQLite path under ``.dazzle/perf/``, sets the env vars
that the runtime reads (``DAZZLE_PERF_ENABLED=1``,
``DAZZLE_PERF_DB``, ``DAZZLE_PERF_RUN_ID``), and shells out to a small
runner that:

1. Configures the global tracer in the *child* uvicorn process.
2. Boots ``dazzle serve`` on a free port.
3. Hits each ``--url`` (synchronously) once.
4. Sleeps for ``--duration`` seconds so additional traffic can land.
5. Shuts the server down cleanly.
"""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from dazzle.perf.run_id import make_run_id

if TYPE_CHECKING:
    from dazzle.cli.inspect import InspectEntry


def _traceable_page_urls(entries: list[InspectEntry]) -> list[str]:
    """Pick the GET-able workspace + surface page routes worth tracing
    from a categorised route list.

    Drops parameterised detail routes (``/x/{id}`` — no real id to
    substitute) and anything that isn't a workspace or surface page.
    """
    urls: list[str] = []
    for entry in entries:
        parts = entry.detail.split()
        category = parts[0] if parts else ""
        if category not in ("workspace", "surface"):
            continue
        if "{" in entry.name:
            continue
        if "GET" not in parts[1:]:
            continue
        urls.append(entry.name)
    return sorted(set(urls))


def _derive_surface_urls() -> list[str]:
    """Boot the app in-process to enumerate its workspace + surface page
    routes for ``--all-surfaces``.

    Reuses the same route walk as ``dazzle inspect routes --runtime``.
    Needs a reachable database (the route table is only complete on a
    booted app); returns ``[]`` with a note when boot fails.
    """
    from dazzle.cli.inspect import (
        _boot_app,
        _load_appspec,
        _resolve_project_root,
        _walk_runtime_routes,
    )

    project_root = _resolve_project_root(None)
    app, message = _boot_app(project_root)
    if app is None:
        typer.echo(f"  --all-surfaces: could not enumerate routes — {message}")
        return []
    if message:  # ADR-0046 fallback note
        typer.echo(f"  --all-surfaces: {message}")

    # Categorisation degrades gracefully without the AppSpec — workspace
    # routes just land in the "surface" bucket — so an AppSpec load
    # failure here is non-fatal.
    workspace_names: frozenset[str] = frozenset()
    with suppress(Exception):
        appspec = _load_appspec(project_root)
        workspace_names = frozenset(ws.name for ws in (getattr(appspec, "workspaces", None) or []))

    entries = _walk_runtime_routes(app.routes, workspace_names)
    return _traceable_page_urls(entries)


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
    login: str | None = typer.Option(
        None,
        "--login",
        help="EMAIL:PASSWORD — authenticate before firing URL hits. "
        "Hits POST /auth/login/password and threads the session cookie "
        "through subsequent --url GETs.",
    ),
    cookie: list[str] = typer.Option(
        [],
        "--cookie",
        help="NAME=VALUE cookie to set on every --url hit (repeatable). "
        "Use when --login can't model your auth (OAuth/SSO).",
    ),
    all_surfaces: bool = typer.Option(
        False,
        "--all-surfaces",
        help="Auto-trace every workspace + surface page route the app "
        "declares, on top of any explicit --url. Enumerates routes by "
        "booting the app once; pair with --login for auth-gated pages.",
    ),
) -> None:
    """Boot the app under tracing and capture a single run."""
    if login is not None and ":" not in login:
        typer.echo("Error: --login value must be in EMAIL:PASSWORD format (colon-separated).")
        raise typer.Exit(1)

    for c in cookie:
        if "=" not in c:
            typer.echo(f"Error: --cookie value {c!r} must be in NAME=VALUE format.")
            raise typer.Exit(1)

    # --all-surfaces enumerates page routes by booting the app once, then
    # folds them into the URL set the trace run drives.
    all_urls = list(urls)
    if all_surfaces:
        derived = _derive_surface_urls()
        if derived:
            typer.echo(f"  --all-surfaces: added {len(derived)} page route(s) to the trace.")
            all_urls.extend(derived)
        else:
            typer.echo("  --all-surfaces: no page routes discovered to trace.")

    if not all_urls and duration <= 0:
        typer.echo(
            "Provide at least one --url, --all-surfaces, or a non-zero "
            "--duration. Run `dazzle perf trace --help` for usage."
        )
        raise typer.Exit(1)

    perf_dir = Path.cwd() / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    run_id = make_run_id()
    db_path = perf_dir / f"{run_id}.db"

    _execute_trace_run(
        run_id=run_id,
        db_path=db_path,
        urls=tuple(all_urls),
        duration=duration,
        login=login,
        cookies=tuple(cookie),
    )

    typer.echo(f"Trace saved: {db_path}")

    if report:
        from dazzle.cli.perf_impl.report import report_command

        report_command(run=run_id, fmt="md", top=10, baseline=None)


def _parse_set_cookie_value(set_cookie_header: str, name: str) -> str | None:
    """Extract a named cookie value from a Set-Cookie header.

    Tolerates multi-cookie headers separated by ``, `` (comma-space) —
    Set-Cookie is allowed to repeat, but Python's http.client may
    concatenate them with ``, `` per RFC 7230.
    """
    if not set_cookie_header:
        return None
    # http.client doesn't natively split multiple Set-Cookies; the
    # value comes back as a comma-separated string. Split on `, ` only
    # when followed by a name= pattern so commas inside dates (Expires)
    # don't trip us.
    pieces = re.split(r",\s+(?=[a-zA-Z][\w-]*=)", set_cookie_header)
    for piece in pieces:
        # First segment is the cookie itself; rest are attrs (HttpOnly, etc.)
        first = piece.split(";", 1)[0]
        if "=" not in first:
            continue
        k, _, v = first.partition("=")
        if k.strip() == name:
            return v.strip()
    return None


def _execute_trace_run(
    *,
    run_id: str,
    db_path: Path,
    urls: tuple[str, ...],
    duration: int,
    login: str | None = None,
    cookies: tuple[str, ...] = (),
) -> None:
    """Spawn uvicorn under tracing, drive the URLs, return on shutdown."""
    import http.client
    import os
    import subprocess
    import sys
    import time
    import urllib.parse

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

    # Boot `dazzle serve` in a subprocess against the caller-provided
    # DATABASE_URL / REDIS_URL (see env above) so the trace run starts fast.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dazzle.cli",
            "serve",
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

    # Build the session cookies dict from --login and/or --cookie.
    cookies_dict: dict[str, str] = {}

    def _do_login(email: str, password: str) -> None:
        """POST to /auth/login/password and capture the session cookie."""
        body = urllib.parse.urlencode({"email": email, "password": password})
        try:
            conn = http.client.HTTPConnection(_TRACE_HOST, _TRACE_PORT, timeout=10)
            conn.request(
                "POST",
                "/auth/login/password",
                body=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response = conn.getresponse()
            # 303 redirect on success; we don't follow — we just need the cookie.
            set_cookie = response.getheader("Set-Cookie") or ""
            conn.close()
        except OSError as exc:
            typer.echo(f"  --login failed: connection error — {exc}")
            return
        session_value = _parse_set_cookie_value(set_cookie, "dazzle_session")
        if session_value is None:
            typer.echo("  --login failed: no dazzle_session cookie returned")
        else:
            cookies_dict["dazzle_session"] = session_value

    def _fetch_path(raw: str) -> None:
        """GET a single path from the local dev server."""
        if raw.startswith("http://") or raw.startswith("https://"):
            from urllib.parse import urlparse

            path = urlparse(raw).path or "/"
        else:
            path = raw if raw.startswith("/") else f"/{raw}"
        headers: dict[str, str] = {}
        if cookies_dict:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
        try:
            conn = http.client.HTTPConnection(_TRACE_HOST, _TRACE_PORT, timeout=10)
            conn.request("GET", path, headers=headers)
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
            # Resolve auth cookies before hitting URLs.
            if login is not None:
                # --login wins; warn if --cookie also supplied.
                if cookies:
                    typer.echo(
                        "  warning: --login and --cookie both supplied; "
                        "--login wins. Explicit cookies ignored."
                    )
                email, _, password = login.partition(":")
                _do_login(email, password)
            elif cookies:
                for entry in cookies:
                    k, _, v = entry.partition("=")
                    cookies_dict[k.strip()] = v.strip()

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

    # The traced server is SIGTERM'd, never cleanly shut down, so the
    # exporter's own `ended_at` write (in SQLiteSpanExporter.shutdown())
    # never fires. Stamp it from the runner instead — robust to how the
    # child exits.
    _stamp_run_ended(db_path, run_id)


def _stamp_run_ended(db_path: Path, run_id: str) -> None:
    """Record run-completion time on the ``runs`` row.

    Without this the row's ``ended_at`` stays NULL and every
    ``perf report`` header reads ``Ended: (running)``.
    """
    import sqlite3
    from datetime import UTC, datetime

    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE runs SET ended_at = ? WHERE run_id = ? AND ended_at IS NULL",
            (datetime.now(UTC).isoformat(), run_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        typer.echo(f"  warning: could not stamp run end time — {exc}")
