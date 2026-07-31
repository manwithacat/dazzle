#!/usr/bin/env python3
"""Fail-fast health check for Grok / agent loops on this monorepo.

Catches the failure modes we hit on the #1626 recapture path:

* External volume TCC (``os.access(..., R_OK)`` false on ``/Volumes/...``)
* Broken git (cannot open ``.git/config``)
* Unusable venv (cannot open ``pyvenv.cfg`` / import dazzle)
* Typer "path is not readable" for example projects
* Optional Postgres connectivity for fleet recapture

Usage::

    python scripts/agent_workspace_health.py
    python scripts/agent_workspace_health.py --json
    python scripts/agent_workspace_health.py --require-postgres
    python scripts/agent_workspace_health.py --apps invoice_ops,ops_dashboard

Exit 0 = ready for git + dazzle serve + recapture.
Exit 1 = blocked (print remediation).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    id: str
    ok: bool
    detail: str
    remediation: str = ""


@dataclass
class Report:
    root: str
    ok: bool
    checks: list[Check] = field(default_factory=list)

    def add(self, c: Check) -> None:
        self.checks.append(c)
        if not c.ok:
            self.ok = False


def _can_open(path: Path) -> tuple[bool, str]:
    try:
        with path.open("rb") as f:
            f.read(32)
        return True, "open ok"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _check_path_readable(path: Path, *, id_: str, label: str) -> Check:
    exists = path.exists()
    r_ok = os.access(path, os.R_OK) if exists else False
    x_ok = os.access(path, os.X_OK) if exists and path.is_dir() else False
    if not exists:
        return Check(id_, False, f"{label} missing: {path}", "Clone or fix WORKSPACE path.")
    if path.is_dir() and not r_ok:
        return Check(
            id_,
            False,
            f"{label} not readable (R_OK=False X_OK={x_ok}): {path}",
            "macOS TCC: grant Ghostty (or host terminal) Removable Volumes + "
            "Full Disk Access; quit/relaunch terminal. "
            "Or move monorepo to ~/src/Dazzle. "
            "See scripts/macos_agent_volume_access.sh",
        )
    if path.is_file() and not r_ok:
        opened, detail = _can_open(path)
        if not opened:
            return Check(
                id_,
                False,
                f"{label} not openable: {path} ({detail})",
                "Same TCC / volume access as above.",
            )
    # Directory: try listdir (stricter than access on some builds)
    if path.is_dir():
        try:
            next(path.iterdir(), None)
        except OSError as exc:
            return Check(
                id_,
                False,
                f"{label} listdir failed: {exc}",
                "macOS TCC / volume permissions for the agent host app.",
            )
    return Check(id_, True, f"{label} ok ({path})")


def check_workspace(root: Path, apps: list[str], *, require_postgres: bool) -> Report:
    report = Report(root=str(root), ok=True)

    report.add(_check_path_readable(root, id_="root", label="repo root"))

    git_cfg = root / ".git" / "config"
    opened, detail = _can_open(git_cfg) if git_cfg.is_file() else (False, "missing")
    if not opened:
        report.add(
            Check(
                "git_config",
                False,
                f".git/config not openable ({detail})",
                "Volume TCC or broken clone. Fix FS access then `git status`.",
            )
        )
    else:
        try:
            head = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                text=True,
                timeout=10,
            ).strip()
            report.add(Check("git", True, f"git HEAD={head}"))
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            report.add(Check("git", False, f"git failed: {exc}", "Install git; fix .git access."))

    venv_py = root / ".venv" / "bin" / "python"
    venv_cfg = root / ".venv" / "pyvenv.cfg"
    if not venv_cfg.is_file():
        report.add(
            Check("venv", False, "no .venv/pyvenv.cfg", "Run `uv sync` / create .venv in repo.")
        )
    else:
        opened, detail = _can_open(venv_cfg)
        if not opened:
            report.add(
                Check(
                    "venv",
                    False,
                    f"pyvenv.cfg not openable ({detail})",
                    "Volume TCC — same as root. Grant host terminal Full Disk Access.",
                )
            )
        else:
            try:
                out = subprocess.check_output(
                    [str(venv_py), "-c", "import dazzle; print('dazzle', dazzle.__file__)"],
                    text=True,
                    timeout=30,
                    cwd=str(root),
                ).strip()
                report.add(Check("dazzle_import", True, out))
            except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
                report.add(
                    Check(
                        "dazzle_import",
                        False,
                        f"import dazzle failed: {exc}",
                        "uv sync; ensure agent uses repo .venv/bin/python.",
                    )
                )

    for app in apps:
        app_dir = root / "examples" / app
        report.add(
            _check_path_readable(
                app_dir,
                id_=f"app:{app}",
                label=f"example {app}",
            )
        )
        toml = app_dir / "dazzle.toml"
        if app_dir.is_dir() and not toml.is_file():
            report.add(Check(f"app_toml:{app}", False, f"missing {toml}", "Broken example tree."))

    if require_postgres:
        # Default recapture DSN pattern
        dsn = os.environ.get("DATABASE_URL", "postgresql://james@127.0.0.1:5432/postgres")
        host, port = "127.0.0.1", 5432
        try:
            u = urlparse(dsn)
            host = u.hostname or host
            port = u.port or port
        except Exception:
            pass
        try:
            with socket.create_connection((host, port), timeout=2.0):
                report.add(Check("postgres", True, f"tcp {host}:{port} open"))
        except OSError as exc:
            report.add(
                Check(
                    "postgres",
                    False,
                    f"cannot connect {host}:{port}: {exc}",
                    "Start Postgres; create dazzle_<app> DBs for recapture.",
                )
            )

    # Grok agent marker — informational
    if os.environ.get("GROK_AGENT"):
        report.add(
            Check(
                "grok_agent",
                True,
                "GROK_AGENT=1 (running inside Grok Build shell)",
            )
        )

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=REPO)
    ap.add_argument(
        "--apps",
        default="invoice_ops,ops_dashboard",
        help="Example apps to probe for readability (comma-separated)",
    )
    ap.add_argument(
        "--require-postgres",
        action="store_true",
        help="Require Postgres TCP open (fleet recapture)",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    report = check_workspace(args.root.resolve(), apps, require_postgres=args.require_postgres)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "root": report.root,
                    "checks": [asdict(c) for c in report.checks],
                },
                indent=2,
            )
        )
    else:
        print(f"agent_workspace_health root={report.root}")
        for c in report.checks:
            mark = "OK  " if c.ok else "FAIL"
            print(f"  {mark}  {c.id}: {c.detail}")
            if not c.ok and c.remediation:
                print(f"         → {c.remediation}")
        print("OVERALL", "PASS" if report.ok else "FAIL")
        if not report.ok:
            print(
                "\nRemediation summary: fix FAIL rows above before "
                "git pull / dazzle serve / recapture_demo_fleet_1626.",
                file=sys.stderr,
            )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
