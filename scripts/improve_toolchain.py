"""What can this host actually do? One probe, machine-readable, with remedies.

Cycle 2411 selected the forced campaign `example-apps agent_qa_smoke` and
immediately hit a wall: `dazzle qa smoke-dig` needs Playwright, which lives in
the `e2e` extra, and `make dev-install` does not install it. The strategy
playbook's FIX bar is a table of *findings* — it has no row for "the tool is
missing", so the agent improvising at that moment has no defined outcome. It
should have reported `BLOCKED` with the remedy, and nothing in the loop could
tell it to.

This probe is the missing precondition check. It is advisory by default
(reports, exit 0) and a gate with `--require` (exit non-zero, prints the
remedy). Step 0b runs it before lane selection, so a forced campaign cannot be
selected into a dead end.

Playwright is not the only such tool: `qa/capture.py`, `qa/component_vision.py`
and `qa/property_vision.py` import it too, and the runtime paths need Postgres.
So the capability list is data — `tests/unit/fixtures/toolchain_capabilities.json`
— and `test_toolchain_probe.py` asserts every probe-dependent playbook names a
capability here, so a strategy cannot grow a new tool dependency silently.

Usage:
    uv run python scripts/improve_toolchain.py --status
    uv run python scripts/improve_toolchain.py --require playwright
    uv run python scripts/improve_toolchain.py --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CAPS = REPO / "tests" / "unit" / "fixtures" / "toolchain_capabilities.json"


@dataclass
class Capability:
    """One thing the harness may need, and how to get it."""

    name: str
    summary: str
    remedy: str
    required_for: list[str] = field(default_factory=list)
    probe: str = "module"  # module | binary | env | url | any
    spec: str = ""

    def present(self) -> tuple[bool, str]:
        """(available, detail) — never raises: an absent tool is a fact, not an error."""
        try:
            if self.probe == "module":
                found = importlib.util.find_spec(self.spec or self.name) is not None
                if found and self.name == "playwright":
                    # The package alone is not enough: the browser binary is a
                    # separate download, and `playwright install chromium` is the
                    # step that is easy to miss.
                    found = _chromium_installed()
                    return found, "" if found else "package present, browser binary missing"
                return found, "" if found else f"{self.spec or self.name} not importable"
            if self.probe == "binary":
                path = shutil.which(self.spec or self.name)
                return path is not None, "" if path else f"{self.spec or self.name} not on PATH"
            if self.probe == "env":
                value = os.environ.get(self.spec or self.name.upper())
                if value:
                    return True, ""
                # A project-scoped DB is the common case: accept a default too.
                return False, f"{self.spec or self.name.upper()} unset"
            if self.probe == "url":
                return _url_reachable(self.spec), "" if _url_reachable(self.spec) else "unreachable"
        except Exception as exc:  # noqa: BLE001 — a probe must never break the loop
            return False, f"probe error: {type(exc).__name__}: {exc}"
        return False, "unknown probe"


def _chromium_installed() -> bool:
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or (Path.home() / "Library" / "Caches" / "ms-playwright")
    )
    if not cache.is_dir():
        # Linux CI layout.
        cache = Path.home() / ".cache" / "ms-playwright"
    return any(cache.glob("chromium*")) if cache.is_dir() else False


def _url_reachable(url: str, timeout: float = 1.5) -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout):  # noqa: S310 — loopback only
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def load_caps() -> list[Capability]:
    raw: list[dict[str, Any]] = json.loads(CAPS.read_text(encoding="utf-8"))
    return [Capability(**row) for row in raw]


def gh_authed() -> bool:
    if shutil.which("gh") is None:
        return False
    proc = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, timeout=30, check=False
    )
    return proc.returncode == 0


def report(caps: list[Capability] | None = None) -> list[dict[str, Any]]:
    caps = caps if caps is not None else load_caps()
    out: list[dict[str, Any]] = []
    for cap in caps:
        if cap.name == "gh-auth":
            ok, detail = gh_authed(), ""
        else:
            ok, detail = cap.present()
        out.append(
            {
                "name": cap.name,
                "ok": ok,
                "detail": detail,
                "remedy": cap.remedy,
                "required_for": cap.required_for,
                "summary": cap.summary,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--status", action="store_true", help="print availability for every capability")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    ap.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="CAP",
        help="exit non-zero unless CAP is available (repeatable)",
    )
    args = ap.parse_args(argv)

    rows = report()
    by_name = {r["name"]: r for r in rows}

    if args.require:
        missing = [n for n in args.require if not by_name.get(n, {}).get("ok")]
        for name in args.require:
            row = by_name.get(name)
            if row is None:
                print(f"FAIL unknown capability {name!r}", file=sys.stderr)
                return 2
            mark = "ok  " if row["ok"] else "MISS"
            print(f"[{mark}] {name}: {row['summary']}")
            if not row["ok"]:
                print(
                    f"        remedy: {row['remedy']}"
                    + (f" ({row['detail']})" if row["detail"] else "")
                )
        return 1 if missing else 0

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"toolchain: {sum(1 for r in rows if r['ok'])}/{len(rows)} capabilities available")
    for row in rows:
        mark = "ok  " if row["ok"] else "MISS"
        detail = f" — {row['detail']}" if row["detail"] else ""
        print(f"  [{mark}] {row['name']:<12} {row['summary']}{detail}")
        if not row["ok"]:
            print(f"         remedy: {row['remedy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
