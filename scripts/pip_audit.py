#!/usr/bin/env python3
"""The one locked-tree ``pip-audit`` invocation, with an explicit verdict.

Why this file exists
--------------------
The pip-audit invocation used to be written out three times — in
``.github/workflows/ci.yml`` (``security-tests``), in
``.github/workflows/main-hygiene.yml``, and in ``scripts/ci_local.sh`` — and
the three had already drifted into disagreeing about what "clean" means.
That drift shipped issue #1745: the weekly hygiene job filed "unpatched
advisories in the locked dependency tree" against a tree that is clean
(verified: ``pip-audit`` on the committed ``uv.lock`` returns ``No known
vulnerabilities found``).

Two independent defects produced that phantom, and both are structural
consequences of encoding the audit as shell inside a workflow:

1. **No interpreter.** The hygiene job installed uv directly and ran
   ``uv pip install pip-audit``, which fails with "No virtual environment
   found" on a bare runner. The bare ``pip-audit`` then resolved to nothing,
   the step exited non-zero, and the job reported *the absence of output* as
   a finding.
2. **The parser missed the advisory IDs pip-audit actually emits.** The
   pattern was ``(CVE|GHSA)-[0-9]+``. Against the PyPI service — this
   project's configuration — pip-audit reports overwhelmingly
   ``PYSEC-YYYY-N``. Measured on a real scan of a deliberately vulnerable
   requirement set: **1 of 124 advisory rows matched**. So a genuine CVE
   would have produced an empty finding set and been discarded by the very
   guard added to stop the phantom: the monitor would have gone silent
   precisely when it was needed.

The fix is to stop treating this as shell-in-a-blob. The verdict logic —
which is the part that is easy to get wrong — now lives in one tested
module, and every caller asks the same question of it.

The verdict
-----------
Exactly one of three, never inferred from an exit code by the caller:

``clean``
    pip-audit succeeded and parsed no advisory rows.
``findings``
    at least one advisory row parsed. This wins over any exit code,
    including 0: a disagreement between "pip-audit said OK" and "we parsed
    a CVE row" must never resolve to *under-reporting*.
``error``
    no verdict could be produced — pip-audit missing from the interpreter,
    the tool crashing, or PyPI unreachable after every retry. **Never
    reported as clean and never reported as findings.** A monitoring tool
    that cannot see has to say so (the bandit-silently-skipped-a-renamed-
    directory failure of 2026-06-20 is the precedent).

Exit codes
----------
``0`` clean · ``1`` findings · ``2`` error/usage.

Two modes, because a gate and a monitor want opposite things:

* **gate mode** (default; ``ci.yml``, ``ci_local.sh``) — findings are a
  failure.
* **--report-only** (``main-hygiene.yml``) — findings are an issue to file,
  not a failure; only ``error`` fails the step. This is what lets the
  hygiene job be honest about advisories without going red every Monday.

Usage
-----
::

    python scripts/pip_audit.py                                  # gate
    python scripts/pip_audit.py --report-only \\
        --findings-file /tmp/findings.txt \\
        --github-output "$GITHUB_OUTPUT"

Requires ``pip-audit`` importable by the running interpreter
(``uv pip install pip-audit``). It is run as ``-m pip_audit`` from
``sys.executable`` on purpose: the audited tree is then guaranteed to be
the tree this interpreter was built from, and no PATH shim can shadow it.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, Field

# Same invocation as ci.yml's security-tests job. Kept here so the flags and
# the single suppression cannot drift between callers again.
AUDIT_FLAGS: Final[tuple[str, ...]] = (
    "--strict",
    "--desc",
    "--no-deps",
    "--disable-pip",
)
# MAL-2026-4750 is suppressed (#1278): Amazon Inspector flagged fastapi
# 0.136.3 for declaring `fastar>=0.9.0` in its [standard] extra.
# `fastar` is a legitimate Rust-tar binding used by fastapi-cloud-cli to
# write zstd-compressed upload bundles — the name is `fast`+`tar`, not a
# typosquat. Remove this suppression if/when the advisory is retracted.
SUPPRESSED: Final[tuple[str, ...]] = ("MAL-2026-4750",)

# pip-audit queries live PyPI per package, so a transient failure must not be
# read as "advisories found" — nor red a clean tree. Same classifier as ci.yml
# (cimonitor 2026-08-09: run 31296179609 @ d1e0ff056 red Security Tests only).
NETWORK_FLAKE: Final[re.Pattern[str]] = re.compile(
    r"ReadTimeout|timed out|TimeoutError|ConnectionError|Connection reset"
    r"|Temporary failure|NameResolutionError|SSLError|RemoteDisconnected"
    r"|Max retries exceeded",
    re.IGNORECASE,
)

# An advisory ID exactly as pip-audit emits it, per scheme. Each branch is
# written out rather than collapsed to `[A-Z]+-\d+(-[\d-]+)?` because the
# schemes do not share a shape: GHSA segments are hex, not digits
# (`GHSA-4fx9-vc88-q2xc`), so a digits-after-the-prefix pattern silently drops
# every GHSA row — the same class of bug that lost 123 of 124 PYSEC rows in
# #1745. Measured against a real scan: 123 PYSEC rows, 3 GHSA rows, and zero
# CVE rows in the ID column (the CVEs in that output are *inside advisory
# descriptions*, which is precisely why this reads column 3 and not the line).
ADVISORY_ID: Final[re.Pattern[str]] = re.compile(
    r"^(?:"
    r"CVE-\d{4}-\d{4,}"
    r"|GHSA-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}"
    r"|(?:PYSEC|MAL|GHSA)-?\d{4}-\d+"
    r")$",
    re.IGNORECASE,
)
ANSI_ESCAPE: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*m")

Status = Literal["clean", "findings", "error"]

EXIT_CLEAN: Final[int] = 0
EXIT_FINDINGS: Final[int] = 1
EXIT_ERROR: Final[int] = 2


class Verdict(BaseModel):
    """What the audit was able to establish. Never inferred by the caller."""

    status: Status
    attempts: int
    exit_code: int
    transport_failure: bool = False
    detail: str = ""
    findings: list[str] = Field(default_factory=list)


class Attempt(BaseModel):
    """One pip-audit invocation's raw result."""

    returncode: int
    output: str


def strip_ansi(text: str) -> str:
    """Drop colour escapes so ``^``-anchored matching works.

    pip-audit colourises when it thinks it is on a TTY; GitHub Actions log
    capture makes it think it is, so the escapes really do arrive.
    """
    return ANSI_ESCAPE.sub("", text)


def parse_findings(output: str) -> list[str]:
    """Extract ``name version ID`` triples from pip-audit output.

    Column-extract rather than match the whole line: with ``--desc`` a row is
    ``name version ID fixVersions description…`` and the description carries
    its own CVE mentions, so a whole-line pattern both misses rows (padding is
    not fixed-width) and drags prose into whatever consumes the findings.

    Only the first three fields are kept, so a caller rendering them into an
    issue body cannot accidentally inline advisory text. Deduplicated because
    pip-audit emits the same PYSEC row once per alias.
    """
    triples: set[tuple[str, str, str]] = set()
    for raw in strip_ansi(output).splitlines():
        fields = raw.split()
        if len(fields) < 3:
            continue
        name, version, advisory_id = fields[0], fields[1], fields[2]
        # The header row is `Name Version ID …`; the rule row is dashes.
        if not version[0].isdigit():
            continue
        if not ADVISORY_ID.match(advisory_id):
            continue
        triples.add((name, version, advisory_id))
    return sorted(f"{n} {v} {i}" for n, v, i in triples)


def is_network_flake(output: str) -> bool:
    """True when pip-audit failed for transport reasons, not advisories."""
    return bool(NETWORK_FLAKE.search(strip_ansi(output)))


def _uv_bin() -> str:
    """Locate uv the way ``scripts/ci_local.sh`` does."""
    explicit = os.environ.get("UV")
    if explicit:
        return explicit
    local = Path.home() / ".local" / "bin" / "uv"
    if local.is_file():
        return str(local)
    return "uv"


def freeze_requirements(dest: Path) -> str:
    """Write the resolved tree to ``dest``; return its contents.

    ``--exclude-editable`` drops the editable ``dazzle-dsl`` install, which
    pip-audit cannot resolve against PyPI. ``--no-deps --disable-pip`` on the
    frozen file then sidesteps that entirely while still auditing every
    transitive dep.
    """
    proc = subprocess.run(
        [_uv_bin(), "pip", "freeze", "--exclude-editable"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"could not freeze the resolved tree (uv pip freeze rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    dest.write_text(proc.stdout, encoding="utf-8")
    return proc.stdout


def run_pip_audit(reqs: Path) -> Attempt:
    """Invoke pip-audit in *this* interpreter against ``reqs``."""
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        *AUDIT_FLAGS,
        *(arg for vid in SUPPRESSED for arg in ("--ignore-vuln", vid)),
        "-r",
        str(reqs),
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError as exc:  # interpreter vanished mid-run
        return Attempt(returncode=EXIT_ERROR, output=f"could not execute pip-audit: {exc}")
    return Attempt(returncode=proc.returncode, output=(proc.stdout or "") + (proc.stderr or ""))


def audit(reqs: Path, attempts: int, sleep: Callable[[float], None] = time.sleep) -> Verdict:
    """Run pip-audit with transport-failure retries and decide the verdict.

    Retries only on transport failures. A crash or a real advisory set is
    never retried: retrying a crash just delays the report, and retrying a
    finding triple-counts nothing useful.
    """
    last = Attempt(returncode=EXIT_ERROR, output="pip-audit was never run")
    attempt = 0
    for attempt in range(1, max(1, attempts) + 1):
        last = run_pip_audit(reqs)
        findings = parse_findings(last.output)
        if findings:
            # Findings outrank every other signal, including rc=0. If we
            # parsed an advisory row, that is the report.
            return Verdict(
                status="findings",
                attempts=attempt,
                exit_code=last.returncode,
                findings=findings,
                detail=f"{len(findings)} advisory row(s) parsed from pip-audit output",
            )
        if last.returncode == EXIT_CLEAN:
            return Verdict(
                status="clean",
                attempts=attempt,
                exit_code=last.returncode,
                detail="pip-audit reported no known vulnerabilities",
            )
        if not is_network_flake(last.output):
            # Non-zero, no advisory rows, not transport: the tool failed.
            break
        if attempt < attempts:
            sleep(attempt * 15)

    return Verdict(
        status="error",
        attempts=attempt,
        exit_code=last.returncode,
        transport_failure=is_network_flake(last.output),
        detail=(
            "pip-audit could not be run to a verdict: "
            + (
                "PyPI unreachable after every retry"
                if is_network_flake(last.output)
                else "the tool exited non-zero without reporting an advisory"
            )
        ),
    )


def _report_only_exit(verdict: Verdict) -> int:
    """Report mode: findings are filed as an issue; only ``error`` fails."""
    return EXIT_ERROR if verdict.status == "error" else EXIT_CLEAN


def _write_findings(path: Path, verdict: Verdict) -> None:
    """Always write the file — a stale list is how phantoms get filed."""
    path.write_text("".join(f"{row}\n" for row in verdict.findings), encoding="utf-8")


def _write_github_output(path: Path, verdict: Verdict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"clean={'true' if verdict.status == 'clean' else 'false'}\n")
        fh.write(f"audit_status={verdict.status}\n")
        fh.write(f"audit_detail={verdict.detail}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="max pip-audit attempts; only transport failures are retried (default 3)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="monitor mode: findings exit 0 (file an issue), only 'error' exits non-zero",
    )
    parser.add_argument("--findings-file", type=Path, help="write `name version ID` rows here")
    parser.add_argument("--verdict-file", type=Path, help="write the full verdict as JSON here")
    parser.add_argument(
        "--github-output",
        type=Path,
        help="append clean=/audit_status=/audit_detail= to this $GITHUB_OUTPUT file",
    )
    args = parser.parse_args(argv)

    if args.attempts < 1:
        parser.error("--attempts must be >= 1")

    def emit(verdict: Verdict) -> None:
        """Write every requested artefact, in one place.

        A stale findings file is exactly how a phantom gets filed: a reader
        that finds an old list has no way to tell it from this run's.
        """
        if args.findings_file:
            _write_findings(args.findings_file, verdict)
        if args.verdict_file:
            args.verdict_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
        if args.github_output:
            _write_github_output(args.github_output, verdict)

    try:
        import pip_audit  # noqa: F401
    except ImportError:
        verdict = Verdict(
            status="error",
            attempts=0,
            exit_code=EXIT_ERROR,
            detail=(
                "pip-audit is not importable by this interpreter "
                f"({sys.executable}) — install it with `uv pip install pip-audit`. "
                "This run cannot say anything about advisories."
            ),
        )
        print(f"error: {verdict.detail}", file=sys.stderr)
        emit(verdict)
        return EXIT_ERROR

    reqs = Path("/tmp/pip-audit-reqs.txt")
    try:
        freeze_requirements(reqs)
    except RuntimeError as exc:
        verdict = Verdict(status="error", attempts=0, exit_code=EXIT_ERROR, detail=str(exc))
        print(f"error: {verdict.detail}", file=sys.stderr)
        emit(verdict)
        return EXIT_ERROR

    verdict = audit(reqs, attempts=args.attempts)
    emit(verdict)

    if verdict.status == "clean":
        print(f"pip-audit clean ({verdict.attempts} attempt(s)): {verdict.detail}")
        return EXIT_CLEAN

    if verdict.status == "findings":
        print(f"pip-audit: {len(verdict.findings)} advisory row(s)", file=sys.stderr)
        for row in verdict.findings:
            print(f"  {row}", file=sys.stderr)
        return _report_only_exit(verdict) if args.report_only else EXIT_FINDINGS

    print(f"error: {verdict.detail}", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
