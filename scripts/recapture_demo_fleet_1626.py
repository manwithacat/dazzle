#!/usr/bin/env python3
"""Re-capture product-desk stills for #1626 Phase 6.

For each showcase app: serve (test mode) → demo reset-and-load → qa capture
--above-fold. Requires Postgres DBs named dazzle_<app> and Playwright chromium.

Usage:
  .venv/bin/python scripts/recapture_demo_fleet_1626.py
  .venv/bin/python scripts/recapture_demo_fleet_1626.py --apps simple_task,invoice_ops
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


def _db_url(app: str) -> str:
    return os.environ.get(
        f"DAZZLE_DB_{app.upper()}",
        f"postgresql://james@127.0.0.1:5432/dazzle_{app}",
    )


def _personas_for_app(project: Path) -> list[str]:
    """Stable persona ids with default_workspace (skip pure admin)."""
    try:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.core.ir.identity import spec_display_id

        appspec = load_project_appspec(project)
    except Exception:
        return []
    out: list[str] = []
    skip = {"admin", "platform_admin", "superuser"}
    for p in appspec.personas or []:
        pid = spec_display_id(p, default=None, prefer="id")
        if not pid or pid in skip:
            continue
        if not getattr(p, "default_workspace", None):
            continue
        out.append(str(pid))
    return out


def _wait_http(url: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.5)
    return False


def _run_app(app: str, *, skip_capture: bool = False) -> int:
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
    # Prefer project venv python
    py = str(REPO / ".venv" / "bin" / "python")
    if not Path(py).is_file():
        py = sys.executable

    serve_cmd = [
        py,
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
    print(f"\n=== {app} port={port} db={db} ===", flush=True)
    proc = subprocess.Popen(
        serve_cmd,
        cwd=str(project),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        if not _wait_http(base + "/docs", timeout=120) and not _wait_http(base, timeout=30):
            print(f"FAIL {app}: serve did not become ready", file=sys.stderr)
            # dump last log lines
            if proc.stdout:
                try:
                    # non-blocking-ish: kill then read
                    pass
                except Exception:
                    pass
            return 1

        # Give runtime.json a moment to write
        time.sleep(1.5)
        # --json + --skip-verify: seed HTTP success is the recapture gate;
        # live_desk residual (e.g. empty PaymentAttempt for auditor) must not
        # block still capture when Invoice/Task spines seeded (#1626).
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
                f"reset-and-load: fixtures={report.get('fixture_count')} "
                f"seed_ok={seed_ok} data_dir={report.get('data_dir')}",
                flush=True,
            )
            if report.get("error"):
                print(f"  error: {report.get('error')}", flush=True)
        except json.JSONDecodeError:
            print(reset.stdout[-1500:] if reset.stdout else "", flush=True)
        if not seed_ok:
            print(reset.stderr[-1500:] if reset.stderr else "", file=sys.stderr)
            print(f"WARN {app}: seed not clean — capture may be empty theater", file=sys.stderr)

        if skip_capture:
            return 0 if seed_ok else 1

        # Per-persona capture avoids 600s full-app timeouts on multi-desk apps.
        personas = _personas_for_app(project)
        if not personas:
            personas = [None]  # single full capture
        any_fail = False
        for persona in personas:
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
            label = persona or "(all)"
            if persona:
                cmd.extend(["--persona", persona])
            print(f"  capture persona={label}", flush=True)
            cap = subprocess.run(
                cmd,
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if cap.stdout:
                print(cap.stdout[-1200:], flush=True)
            if cap.returncode != 0:
                print(cap.stderr[-800:] if cap.stderr else "", file=sys.stderr)
                print(f"FAIL {app}: capture persona={label} exit {cap.returncode}", file=sys.stderr)
                any_fail = True
        if any_fail:
            return 1
        print(f"OK {app}: capture done", flush=True)
        return 0 if seed_ok else 1
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()


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
    args = parser.parse_args()
    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    results: dict[str, int] = {}
    for app in apps:
        try:
            results[app] = _run_app(app, skip_capture=args.skip_capture)
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
