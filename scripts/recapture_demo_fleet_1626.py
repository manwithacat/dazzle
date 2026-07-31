#!/usr/bin/env python3
"""Re-capture product-desk stills for #1626.

For each showcase app **and each product persona**: serve → demo
reset-and-load → qa capture --above-fold, then kill the server.

**Why per-persona serve:** multi-persona capture against one long-lived serve
process often wedges (subsequent personas hang on "Server did not become ready"
or hit 300s subprocess timeouts). 31 Jul antagonist recapture proved
restart-per-persona is reliable.

**Hardening (agent-loop reliability):**

* Serve stdout/stderr go to a **log file**, never ``PIPE`` — unread PIPE
  buffers fill and deadlock the child (LISTEN but no HTTP).
* Readiness requires **consecutive** successful HTTP probes, not one hit.
* ``--preflight`` (default on) runs ``agent_workspace_health`` so volume TCC,
  venv, and Postgres failures fail fast with remediation.
* Ports are freed before/after each persona; serve process groups are killed.

Requires Postgres DBs named ``dazzle_<app>`` and Playwright chromium.

Usage::

  .venv/bin/python scripts/recapture_demo_fleet_1626.py
  .venv/bin/python scripts/recapture_demo_fleet_1626.py --apps simple_task,invoice_ops
  .venv/bin/python scripts/recapture_demo_fleet_1626.py --capture-timeout 900
  .venv/bin/python scripts/recapture_demo_fleet_1626.py --skip-capture  # seed only
  .venv/bin/python scripts/recapture_demo_fleet_1626.py --skip-preflight
  .venv/bin/python scripts/agent_workspace_health.py --require-postgres
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHOWCASE = [
    "simple_task",
    "support_tickets",
    "invoice_ops",
    "contact_manager",
    "ops_dashboard",
    "project_tracker",
    "design_studio",
    "hr_records",
    "fieldtest_hub",
]
# Fixed ports per app to avoid clobbering concurrent work
_BASE_PORT = 18100
_DEFAULT_CAPTURE_TIMEOUT = 600
_READY_CONSECUTIVE = 3
_READY_POLL_S = 0.5
_SERVE_LOG_TAIL = 40


def _db_url(app: str) -> str:
    return os.environ.get(
        f"DAZZLE_DB_{app.upper()}",
        f"postgresql://james@127.0.0.1:5432/dazzle_{app}",
    )


def _personas_for_app(project: Path) -> list[str | None]:
    """Stable persona ids with default_workspace (skip pure admin)."""
    try:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.core.ir.identity import spec_display_id

        appspec = load_project_appspec(project)
    except Exception:
        return [None]
    out: list[str | None] = []
    skip = {"admin", "platform_admin", "superuser"}
    for p in appspec.personas or []:
        pid = spec_display_id(p, default=None, prefer="id")
        if not pid or pid in skip:
            continue
        if not getattr(p, "default_workspace", None):
            continue
        out.append(str(pid))
    return out or [None]


def _http_ok(url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(resp.status) < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _wait_http(
    url: str,
    timeout: float = 90.0,
    *,
    consecutive: int = _READY_CONSECUTIVE,
    poll: float = _READY_POLL_S,
) -> bool:
    """True when *consecutive* probes succeed before *timeout*."""
    deadline = time.time() + timeout
    hits = 0
    while time.time() < deadline:
        if _http_ok(url):
            hits += 1
            if hits >= consecutive:
                return True
        else:
            hits = 0
        time.sleep(poll)
    return False


def _kill_proc(proc: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _free_port(port: int) -> None:
    # Prefer lsof; ignore failures (port already free / tool missing).
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return
    pids = [p.strip() for p in (out.stdout or "").split() if p.strip().isdigit()]
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            pass


def _py() -> str:
    candidate = REPO / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def _serve_log_path(project: Path, app: str, persona: str | None) -> Path:
    log_dir = project / ".dazzle" / "recapture-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = persona or "all"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    return log_dir / f"{app}-{safe}-{ts}.log"


def _tail_file(path: Path, n: int = _SERVE_LOG_TAIL) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"(could not read serve log {path}: {exc})"
    if not lines:
        return f"(serve log empty: {path})"
    body = "\n".join(lines[-n:])
    return f"--- serve log tail {path} ---\n{body}\n--- end ---"


def run_preflight(apps: list[str], *, require_postgres: bool = True) -> int:
    """Run agent_workspace_health; return its exit code (0 = ready)."""
    health = REPO / "scripts" / "agent_workspace_health.py"
    if not health.is_file():
        print(
            "WARN: agent_workspace_health.py missing — skipping FS/git preflight",
            file=sys.stderr,
        )
        return 0
    cmd = [_py(), str(health), "--apps", ",".join(apps)]
    if require_postgres:
        cmd.append("--require-postgres")
    print("preflight:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def _seed(project: Path, base: str, env: dict[str, str], py: str) -> bool:
    reset = subprocess.run(
        [
            py,
            "-m",
            "dazzle",
            "demo",
            "reset-and-load",
            "--project",
            str(project),
            "--base-url",
            base,
            "-y",
            "--json",
            "--skip-verify",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    seed_ok = reset.returncode == 0
    try:
        report = json.loads(reset.stdout or "{}")
        steps = report.get("steps") or []
        seed_step = next((s for s in steps if s.get("step") == "seed"), None)
        if seed_step is not None:
            seed_ok = bool(seed_step.get("ok"))
        print(
            f"  reset-and-load: fixtures={report.get('fixture_count')} "
            f"seed_ok={seed_ok} data_dir={report.get('data_dir')}",
            flush=True,
        )
        if report.get("error"):
            print(f"  error: {report.get('error')}", flush=True)
    except json.JSONDecodeError:
        if reset.stdout:
            print(reset.stdout[-1500:], flush=True)
    if not seed_ok and reset.stderr:
        print(reset.stderr[-1500:], file=sys.stderr)
    return seed_ok


def _capture_persona(
    *,
    app: str,
    project: Path,
    port: int,
    db: str,
    persona: str | None,
    env: dict[str, str],
    py: str,
    capture_timeout: int,
    skip_capture: bool,
) -> int:
    """Serve + seed + capture one persona; always tear down serve."""
    label = persona or "(all)"
    _free_port(port)
    time.sleep(0.2)

    log_path = _serve_log_path(project, app, persona)
    serve_cmd = [
        py,
        "-u",  # unbuffered — log lines appear promptly
        "-m",
        "dazzle",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--api-port",
        str(port),
        "--database-url",
        db,
    ]
    print(f"  serve persona={label} port={port} log={log_path}", flush=True)
    log_fh = log_path.open("wb")
    env = dict(env)
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            serve_cmd,
            cwd=str(project),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        base = f"http://127.0.0.1:{port}"
        docs = base + "/docs"
        ready = _wait_http(docs, timeout=120) or _wait_http(base, timeout=30)
        if not ready:
            print(f"FAIL {app}: serve not ready for persona={label}", file=sys.stderr)
            if proc.poll() is not None:
                print(
                    f"  serve exited early code={proc.returncode}",
                    file=sys.stderr,
                )
            print(_tail_file(log_path), file=sys.stderr)
            return 1
        # Brief settle after consecutive readiness (migrations / warm caches).
        time.sleep(0.5)
        seed_ok = _seed(project, base, env, py)
        if not seed_ok:
            print(
                f"WARN {app}: seed not clean for persona={label} — capture may be empty theater",
                file=sys.stderr,
            )
        if skip_capture:
            return 0 if seed_ok else 1

        cmd = [
            py,
            "-m",
            "dazzle",
            "qa",
            "capture",
            "--url",
            base,
            "--app",
            app,
            "--above-fold",
            "--viewport",
            "desktop",
        ]
        if persona:
            cmd.extend(["--persona", persona])
        print(f"  capture persona={label} timeout={capture_timeout}s", flush=True)
        try:
            cap = subprocess.run(
                cmd,
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=capture_timeout,
            )
        except subprocess.TimeoutExpired:
            print(
                f"FAIL {app}: capture persona={label} timed out after {capture_timeout}s",
                file=sys.stderr,
            )
            print(_tail_file(log_path), file=sys.stderr)
            return 1
        if cap.stdout:
            for line in cap.stdout.splitlines():
                if (
                    "screenshots" in line
                    or "Capturing" in line
                    or "Waiting" in line
                    or "failed" in line.lower()
                    or "FAIL" in line
                ):
                    print(f"    {line}", flush=True)
        if cap.returncode != 0:
            if cap.stderr:
                print(cap.stderr[-800:], file=sys.stderr)
            print(
                f"FAIL {app}: capture persona={label} exit {cap.returncode}",
                file=sys.stderr,
            )
            print(_tail_file(log_path), file=sys.stderr)
            return 1
        print(f"  OK persona={label}", flush=True)
        return 0 if seed_ok else 1
    finally:
        if proc is not None:
            _kill_proc(proc)
        try:
            log_fh.close()
        except OSError:
            pass
        _free_port(port)


def _run_app(
    app: str,
    *,
    skip_capture: bool = False,
    capture_timeout: int = _DEFAULT_CAPTURE_TIMEOUT,
) -> int:
    project = REPO / "examples" / app
    if not (project / "dazzle.toml").is_file():
        print(f"SKIP {app}: no dazzle.toml", file=sys.stderr)
        return 0

    idx = SHOWCASE.index(app) if app in SHOWCASE else 0
    port = _BASE_PORT + idx
    db = _db_url(app)
    env = os.environ.copy()
    env["DATABASE_URL"] = db
    env["DAZZLE_ENV"] = "development"
    env["DAZZLE_QA_MODE"] = "1"
    env.setdefault("PYTHONUNBUFFERED", "1")
    py = _py()

    print(f"\n=== {app} port={port} db={db} ===", flush=True)
    personas = _personas_for_app(project)
    any_fail = False
    for persona in personas:
        rc = _capture_persona(
            app=app,
            project=project,
            port=port,
            db=db,
            persona=persona,
            env=env,
            py=py,
            capture_timeout=capture_timeout,
            skip_capture=skip_capture,
        )
        if rc != 0:
            any_fail = True
    if any_fail:
        return 1
    print(f"OK {app}: capture done", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apps",
        default=",".join(SHOWCASE),
        help="Comma-separated app names (default: full showcase fleet)",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Only serve + reset-and-load (debug)",
    )
    parser.add_argument(
        "--capture-timeout",
        type=int,
        default=_DEFAULT_CAPTURE_TIMEOUT,
        help=f"Seconds per persona capture (default {_DEFAULT_CAPTURE_TIMEOUT})",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip agent_workspace_health (FS/git/venv/postgres)",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run preflight and exit (no serve/capture)",
    )
    args = parser.parse_args()
    apps = [a.strip() for a in args.apps.split(",") if a.strip()]

    if not args.skip_preflight or args.preflight_only:
        rc = run_preflight(apps, require_postgres=True)
        if rc != 0:
            print(
                "preflight FAILED — fix agent_workspace_health FAIL rows "
                "(see scripts/macos_agent_volume_access.sh for volume TCC).",
                file=sys.stderr,
            )
            return rc
        if args.preflight_only:
            print("preflight PASS", flush=True)
            return 0

    results: dict[str, int] = {}
    for app in apps:
        try:
            results[app] = _run_app(
                app,
                skip_capture=args.skip_capture,
                capture_timeout=args.capture_timeout,
            )
        except Exception as exc:
            print(f"FAIL {app}: {exc}", file=sys.stderr)
            results[app] = 1
    print("\n=== summary ===")
    print(json.dumps(results, indent=2))
    failed = [a for a, c in results.items() if c != 0]
    if failed:
        print(f"failed: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
