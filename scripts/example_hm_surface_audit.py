#!/usr/bin/env python3
"""Fleet HM-surface audit for example apps.

Rebuilds each ``examples/*/`` app via ``dazzle build-ui`` into a fresh
output tree and scores the HTML for pre-HM residuals:

* Alpine directives (``x-data``, ``x-show``, ``x-model``, …)
* Dead Tailwind utility leftovers (``opacity-25`` / ``opacity-75`` spinner class)

Live emit is the source of truth — **never** trust a local ``dnr-ui/``
snapshot. Those dirs are gitignored and often predate the HM migration;
agents that grep them report false "example non-HM" findings.

Usage (from monorepo root)::

    # rebuild all examples into .dazzle/example-hm-audit/ and score
    python scripts/example_hm_surface_audit.py

    # scan an existing tree (e.g. /tmp/hm-ui-* fleet from a prior rebuild)
    python scripts/example_hm_surface_audit.py --scan-root /tmp --scan-prefix hm-ui-

    # one app, JSON for improve ingestion
    python scripts/example_hm_surface_audit.py --app simple_task --json

    # one-line status for improve driver logs
    python scripts/example_hm_surface_audit.py --status

Exit codes:
  0 — every scanned app is HM_OK (alpine=0 and tw_residual=0)
  1 — at least one app has residuals or failed to build
  2 — usage / environment error (no examples found, etc.)

Consumed by:
  - ``improve/lanes/example-apps.md`` (Tier-0 HM surface gate)
  - agents deciding whether an "Alpine residual" is live or stale preview
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
DEFAULT_OUT = REPO / ".dazzle" / "example-hm-audit"

# Alpine / legacy client-framework markers that must not appear in HM emit.
_ALPINE_RE = re.compile(
    r"""
    \bx-data\b
    |\bx-show\b
    |\bx-if\b
    |\bx-model\b
    |\bx-text\b
    |\bx-html\b
    |\bx-bind\b
    |\bx-on:
    |\bx-ref\b
    |\bx-init\b
    |\bx-cloak\b
    |\bx-effect\b
    |\bAlpine\.
    """,
    re.VERBOSE,
)

# Pre-HM Tailwind leftovers that survived in spinner SVGs before HMC-002.
# Match as class tokens, not free text (avoids false hits in prose/comments).
_TW_RESIDUAL_RE = re.compile(
    r"""
    \bclass\s*=\s*["'][^"']*\bopacity-(?:25|75)\b
    |\bclass\s*=\s*["'][^"']*\bbg-gray-\d+\b
    |\bclass\s*=\s*["'][^"']*\btext-gray-\d+\b
    """,
    re.VERBOSE,
)

# Positive signal that the page is on the HM/dz substrate.
_DZ_SIGNAL_RE = re.compile(r"\b(?:dz-|data-dz-|data-dazzle-)")


@dataclass
class AppAudit:
    app: str
    status: str  # HM_OK | FAIL | BUILD_ERROR | SKIP
    html_files: int = 0
    alpine_hits: int = 0
    tw_residual_hits: int = 0
    dz_hits: int = 0
    out_dir: str = ""
    samples: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "HM_OK"


def discover_apps(examples_dir: Path = EXAMPLES) -> list[Path]:
    """Return example project roots that carry a dazzle.toml, sorted."""
    if not examples_dir.is_dir():
        return []
    apps: list[Path] = []
    for child in sorted(examples_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if (child / "dazzle.toml").is_file():
            apps.append(child)
    return apps


def scan_html_dir(html_dir: Path) -> tuple[int, int, int, int, list[str]]:
    """Scan ``*.html`` under html_dir. Returns counts + sample residual lines."""
    alpine = tw = dz = 0
    files = 0
    samples: list[str] = []
    if not html_dir.is_dir():
        return 0, 0, 0, 0, []
    for path in sorted(html_dir.rglob("*.html")):
        files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            samples.append(f"{path.name}: read error: {exc}")
            continue
        a = len(_ALPINE_RE.findall(text))
        t = len(_TW_RESIDUAL_RE.findall(text))
        d = len(_DZ_SIGNAL_RE.findall(text))
        alpine += a
        tw += t
        dz += d
        if (a or t) and len(samples) < 8:
            kind = []
            if a:
                kind.append(f"alpine={a}")
            if t:
                kind.append(f"tw={t}")
            samples.append(f"{path.name}: {', '.join(kind)}")
    return files, alpine, tw, dz, samples


def build_app(app_dir: Path, out_dir: Path) -> None:
    """Generate fresh preview HTML for one example via BuildService."""
    # Local import — keeps --scan-only usable without full package when needed.
    from dazzle.cli.services.build_service import BuildService

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = app_dir / "dazzle.toml"
    svc = BuildService(manifest)
    appspec = svc.load_appspec()
    errors, _warnings = svc.lint(appspec)
    if errors:
        raise RuntimeError("lint errors block build-ui: " + "; ".join(errors[:5]))
    files = svc.generate_preview_files(appspec, str(out_dir))
    if not files:
        raise RuntimeError("build-ui produced zero HTML files")


def audit_app(
    app_dir: Path,
    *,
    out_root: Path,
    rebuild: bool,
    scan_only_dir: Path | None = None,
) -> AppAudit:
    name = app_dir.name
    if scan_only_dir is not None:
        html_dir = scan_only_dir
        out_path = str(html_dir)
    else:
        html_dir = out_root / name
        out_path = str(html_dir)
        if rebuild:
            try:
                build_app(app_dir, html_dir)
            except Exception as exc:  # noqa: BLE001 — surface any build failure
                return AppAudit(
                    app=name,
                    status="BUILD_ERROR",
                    out_dir=out_path,
                    error=f"{type(exc).__name__}: {exc}",
                    samples=[traceback.format_exc(limit=3).strip()],
                )

    files, alpine, tw, dz, samples = scan_html_dir(html_dir)
    if files == 0:
        return AppAudit(
            app=name,
            status="FAIL",
            html_files=0,
            out_dir=out_path,
            error="no HTML files found — rebuild or check path",
        )
    if alpine or tw:
        return AppAudit(
            app=name,
            status="FAIL",
            html_files=files,
            alpine_hits=alpine,
            tw_residual_hits=tw,
            dz_hits=dz,
            out_dir=out_path,
            samples=samples,
        )
    return AppAudit(
        app=name,
        status="HM_OK",
        html_files=files,
        alpine_hits=0,
        tw_residual_hits=0,
        dz_hits=dz,
        out_dir=out_path,
    )


def format_table(results: list[AppAudit]) -> str:
    headers = ("app", "status", "html", "alpine", "tw", "dz")
    rows = [
        (
            r.app,
            r.status,
            str(r.html_files),
            str(r.alpine_hits),
            str(r.tw_residual_hits),
            str(r.dz_hits),
        )
        for r in results
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt(headers), fmt(tuple("-" * w for w in widths))]
    lines.extend(fmt(row) for row in rows)
    ok = sum(1 for r in results if r.ok)
    lines.append("")
    lines.append(f"{ok}/{len(results)} HM_OK")
    for r in results:
        if r.status != "HM_OK":
            lines.append(f"  ! {r.app}: {r.status} {r.error or ''}".rstrip())
            for s in r.samples[:4]:
                lines.append(f"      {s}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit example apps for HM-pure build-ui surfaces."
    )
    parser.add_argument(
        "--app",
        action="append",
        dest="apps",
        help="Limit to one or more example names (repeatable).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Rebuild output root (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Scan existing --out/<app> trees without regenerating.",
    )
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=None,
        help="Scan existing dirs under this root instead of rebuilding "
        "(pairs with --scan-prefix). Example: --scan-root /tmp --scan-prefix hm-ui-",
    )
    parser.add_argument(
        "--scan-prefix",
        default="hm-ui-",
        help="Directory name prefix under --scan-root (default: hm-ui-).",
    )
    parser.add_argument("--json", action="store_true", help="JSON report to stdout.")
    parser.add_argument(
        "--status",
        action="store_true",
        help="One-line status for improve logs (implies rebuild unless --no-rebuild).",
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Also write the JSON report to this path.",
    )
    args = parser.parse_args(argv)

    apps = discover_apps()
    if args.apps:
        wanted = set(args.apps)
        apps = [a for a in apps if a.name in wanted]
        missing = wanted - {a.name for a in apps}
        if missing:
            print(f"unknown example app(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    if not apps:
        print("no example apps found", file=sys.stderr)
        return 2

    results: list[AppAudit] = []
    if args.scan_root is not None:
        for app_dir in apps:
            scan_dir = args.scan_root / f"{args.scan_prefix}{app_dir.name}"
            if not scan_dir.is_dir():
                results.append(
                    AppAudit(
                        app=app_dir.name,
                        status="FAIL",
                        error=f"missing scan dir {scan_dir}",
                    )
                )
                continue
            results.append(
                audit_app(
                    app_dir,
                    out_root=args.out,
                    rebuild=False,
                    scan_only_dir=scan_dir,
                )
            )
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        rebuild = not args.no_rebuild
        for app_dir in apps:
            results.append(audit_app(app_dir, out_root=args.out, rebuild=rebuild))

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "scan" if args.scan_root else ("rebuild" if not args.no_rebuild else "no-rebuild"),
        "ok": all(r.ok for r in results),
        "hm_ok": sum(1 for r in results if r.ok),
        "total": len(results),
        "apps": [asdict(r) for r in results],
    }

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    elif args.status:
        ok_n = report["hm_ok"]
        total = report["total"]
        flag = "HM_OK" if report["ok"] else "FAIL"
        fails = [r.app for r in results if not r.ok]
        extra = f" fails={','.join(fails)}" if fails else ""
        print(f"example_hm_surface: {flag} {ok_n}/{total}{extra}")
    else:
        print(format_table(results))
        print(f"\nout: {args.out if args.scan_root is None else args.scan_root}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
