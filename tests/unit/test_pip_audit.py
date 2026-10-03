"""Gate: the locked-tree pip-audit verdict, in one tested place.

Issue #1745 was a phantom "unpatched advisories" report filed by the weekly
``main-hygiene`` job against a dependency tree that is clean. It had two
causes, and both were bugs in deciding what pip-audit's output *means*:

1. no interpreter, so the bare ``pip-audit`` resolved to nothing and the
   absence of output was reported as a finding;
2. an advisory-ID pattern that matched **1 row in 124** against the PyPI
   service (which emits ``PYSEC-YYYY-N``, not ``GHSA``/``CVE``) — so a real
   CVE would have been discarded by the guard meant to stop the phantom.

The remediation moved that decision out of workflow shell and into
``scripts/pip_audit.py``. These tests are the gate that keeps it honest: they
run under ``-m gate`` (``make ci-fast``), so a regression here reds a ship
rather than the following Monday's badge.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "pip_audit.py"

# Row shapes taken from a real pip-audit --desc scan of a deliberately
# vulnerable requirement set (urllib3 1.24.2 / pillow 7.0.0 / jinja2 2.11.0).
REAL_HEADER = "Name   Version ID              Fix Versions Description"
REAL_RULE = "------ ------- --------------- ------------ -----------"
REAL_ROWS = (
    "urllib3 1.24.2  PYSEC-2019-132   1.24.3       An issue affects the urllib3 library.",
    "pillow  7.0.0   GHSA-4fx9-vc88-q2xc 8.0.0     Buffer overflow in a decoder.",
    "jinja2 2.11.0  PYSEC-2026-1471 3.1.6        Sandbox bypass; the fix for CVE-2024-22195.",
)
CLEAN_OUTPUT = "No known vulnerabilities found\n"


def _load():
    name = "dazzle_scripts_pip_audit"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pa = _load()


# --- the ID vocabulary -------------------------------------------------------
# GHSA segments are hex (`GHSA-4fx9-vc88-q2xc`), so a pattern that assumes
# digits after the prefix drops every GHSA row. That is the same class of bug
# that lost the PYSEC rows, so it is pinned here per scheme.


@pytest.mark.parametrize(
    "advisory_id",
    [
        "PYSEC-2019-132",
        "PYSEC-2021-66",
        "PYSEC-2026-1473",
        "MAL-2026-4750",
        "GHSA-4fx9-vc88-q2xc",
        "GHSA-h5c8-rqwp-cp95",
        "CVE-2021-44228",
        "CVE-2024-1234",
    ],
)
def test_advisory_id_accepts_every_scheme_pip_audit_emits(advisory_id: str) -> None:
    assert pa.ADVISORY_ID.match(advisory_id)


@pytest.mark.parametrize(
    "column",
    ["Name", "Version", "ID", "Fix", "Versions", "Description", "None", "2.11.3", "1.24.3"],
)
def test_advisory_id_rejects_the_other_columns_of_the_row(column: str) -> None:
    """Column 2 of a pip-audit row is sometimes a version, sometimes a header."""
    assert not pa.ADVISORY_ID.match(column)


# --- row parsing -------------------------------------------------------------


def test_parse_findings_reads_the_id_column_not_the_whole_line() -> None:
    """The description carries its own CVE mentions; they are not the row's ID."""
    findings = pa.parse_findings("\n".join([REAL_HEADER, REAL_RULE, *REAL_ROWS]))
    assert findings == [
        "jinja2 2.11.0 PYSEC-2026-1471",
        "pillow 7.0.0 GHSA-4fx9-vc88-q2xc",
        "urllib3 1.24.2 PYSEC-2019-132",
    ]


def test_parse_findings_keeps_only_three_columns() -> None:
    """Findings land in an issue body; advisory prose must not ride along."""
    for row in pa.parse_findings(REAL_ROWS[0]):
        assert len(row.split()) == 3


def test_parse_findings_dedupes_the_alias_rows_pip_audit_repeats() -> None:
    duplicated = "\n".join([REAL_ROWS[0], REAL_ROWS[0], REAL_ROWS[0]])
    assert pa.parse_findings(duplicated) == ["urllib3 1.24.2 PYSEC-2019-132"]


def test_parse_findings_of_a_clean_scan_is_empty() -> None:
    assert pa.parse_findings(CLEAN_OUTPUT) == []


def test_parse_findings_survives_colourised_output() -> None:
    """GitHub Actions log capture makes pip-audit think it is on a TTY."""
    colourised = "\x1b[1;31murllib3 1.24.2  PYSEC-2019-132   1.24.3  desc\x1b[0m"
    assert pa.parse_findings(colourised) == ["urllib3 1.24.2 PYSEC-2019-132"]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("ReadTimeout: HTTPSConnectionPool(host='pypi.org')", True),
        ("Connection reset by peer", True),
        ("pip-audit crashed: KeyError", False),
        ("No known vulnerabilities found", False),
    ],
)
def test_is_network_flake_separates_transport_from_real_failures(
    output: str, expected: bool
) -> None:
    assert pa.is_network_flake(output) is expected


# --- the verdict -------------------------------------------------------------


def _stub_audit(monkeypatch: pytest.MonkeyPatch, results: list[Any]) -> list[int]:
    """Feed `audit()` a scripted sequence of pip-audit outcomes."""
    calls: list[int] = []

    def fake_run(reqs: Path) -> pa.Attempt:
        calls.append(1)
        result = results[min(len(calls) - 1, len(results) - 1)]
        return pa.Attempt(returncode=result[0], output=result[1])

    monkeypatch.setattr(pa, "run_pip_audit", fake_run)
    return calls


def test_audit_reports_findings_not_clean_when_a_row_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never under-report: a parsed advisory outranks pip-audits own exit code."""
    _stub_audit(monkeypatch, [(0, "\n".join([REAL_HEADER, *REAL_ROWS]))])
    verdict = pa.audit(Path("/tmp/reqs.txt"), attempts=3, sleep=lambda _s: None)
    assert verdict.status == "findings"
    assert len(verdict.findings) == 3


def test_audit_reports_clean_on_an_empty_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_audit(monkeypatch, [(0, CLEAN_OUTPUT)])
    verdict = pa.audit(Path("/tmp/reqs.txt"), attempts=3, sleep=lambda _s: None)
    assert verdict.status == "clean"
    assert verdict.findings == []
    assert verdict.exit_code == pa.EXIT_CLEAN


def test_audit_retries_a_transport_failure_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_audit(
        monkeypatch, [(1, "ReadTimeout: pypi.org"), (1, "Connection reset"), (0, CLEAN_OUTPUT)]
    )
    verdict = pa.audit(Path("/tmp/reqs.txt"), attempts=3, sleep=lambda _s: None)
    assert verdict.status == "clean"
    assert verdict.attempts == 3
    assert len(calls) == 3


def test_audit_gives_up_as_error_when_pypi_stays_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable PyPI must not become an advisory finding, nor a clean bill."""
    calls = _stub_audit(monkeypatch, [(1, "ReadTimeout: pypi.org")])
    verdict = pa.audit(Path("/tmp/reqs.txt"), attempts=3, sleep=lambda _s: None)
    assert verdict.status == "error"
    assert verdict.transport_failure is True
    assert verdict.attempts == 3
    assert len(calls) == 3


def test_audit_does_not_retry_a_tool_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying a crash only delays the report."""
    calls = _stub_audit(monkeypatch, [(2, "pip-audit crashed: KeyError('version')")])
    verdict = pa.audit(Path("/tmp/reqs.txt"), attempts=3, sleep=lambda _s: None)
    assert verdict.status == "error"
    assert verdict.transport_failure is False
    assert len(calls) == 1


# --- the two modes -----------------------------------------------------------


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Stub the freeze + subprocess edges so main() runs its real logic."""
    monkeypatch.setattr(pa, "freeze_requirements", lambda dest: dest.write_text("x==1\n"))
    state: dict[str, Any] = {"attempt": (0, CLEAN_OUTPUT)}

    def fake_run(reqs: Path) -> pa.Attempt:
        rc, out = state["attempt"]
        return pa.Attempt(returncode=rc, output=out)

    monkeypatch.setattr(pa, "run_pip_audit", fake_run)

    def run(*extra: str) -> tuple[int, Path, Path]:
        findings = tmp_path / "findings.txt"
        gh_out = tmp_path / "gh_output"
        gh_out.write_text("")
        code = pa.main(
            [
                "--findings-file",
                str(findings),
                "--github-output",
                str(gh_out),
                *extra,
            ]
        )
        return code, findings, gh_out

    state["run"] = run
    return state


def test_gate_mode_treats_findings_as_a_failure(wired: dict[str, Any]) -> None:
    wired["attempt"] = (1, "\n".join([REAL_HEADER, *REAL_ROWS]))
    code, findings, gh_out = wired["run"]()
    assert code == pa.EXIT_FINDINGS
    assert findings.read_text().splitlines() == [
        "jinja2 2.11.0 PYSEC-2026-1471",
        "pillow 7.0.0 GHSA-4fx9-vc88-q2xc",
        "urllib3 1.24.2 PYSEC-2019-132",
    ]
    assert "clean=false" in gh_out.read_text()


def test_report_only_mode_files_findings_without_failing_the_job(wired: dict[str, Any]) -> None:
    """main-hygiene reports an issue rather than going red every Monday."""
    wired["attempt"] = (1, "\n".join([REAL_HEADER, *REAL_ROWS]))
    code, findings, gh_out = wired["run"]("--report-only")
    assert code == pa.EXIT_CLEAN
    assert len(findings.read_text().splitlines()) == 3
    assert "clean=false" in gh_out.read_text()


def test_a_broken_audit_fails_the_step_in_both_modes(wired: dict[str, Any]) -> None:
    """The #1745 lesson: no verdict must never read as clean."""
    wired["attempt"] = (1, "pip-audit crashed before producing a verdict")
    for extra in ([], ["--report-only"]):
        code, findings, gh_out = wired["run"](*extra)
        assert code == pa.EXIT_ERROR
        assert findings.read_text() == ""
        assert "clean=false" in gh_out.read_text()
        assert "audit_status=error" in gh_out.read_text()


def test_error_verdict_truncates_a_stale_findings_file(wired: dict[str, Any]) -> None:
    """A reader cannot tell a previous run's list from this run's."""
    wired["attempt"] = (1, "\n".join([REAL_HEADER, *REAL_ROWS]))
    _, findings, _ = wired["run"]()
    assert findings.read_text()
    wired["attempt"] = (1, "pip-audit crashed before producing a verdict")
    _, findings, _ = wired["run"]()
    assert findings.read_text() == ""


def test_missing_pip_audit_is_an_error_not_a_clean_bill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exact #1745 failure: no interpreter, and it reported 'advisories'."""
    monkeypatch.setitem(sys.modules, "pip_audit", None)
    monkeypatch.setattr(pa, "freeze_requirements", lambda dest: dest.write_text("x==1\n"))
    gh_out = tmp_path / "gh_output"
    gh_out.write_text("")
    code = pa.main(
        [
            "--findings-file",
            str(tmp_path / "findings.txt"),
            "--github-output",
            str(gh_out),
        ]
    )
    assert code == pa.EXIT_ERROR
    assert (tmp_path / "findings.txt").read_text() == ""
    assert "clean=false" in gh_out.read_text()


def test_freeze_excludes_the_editable_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pip-audit cannot resolve an editable dazzle-dsl against PyPI (#1200)."""
    seen: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = "urllib3==1.24.2\n"
        stderr = ""

    monkeypatch.setenv("UV", "/usr/bin/false-uv")
    monkeypatch.setattr(
        pa.subprocess,
        "run",
        lambda cmd, **kw: (seen.append(cmd), _Proc())[1],
    )
    pa.freeze_requirements(tmp_path / "reqs.txt")
    assert seen == [["/usr/bin/false-uv", "pip", "freeze", "--exclude-editable"]]
    assert (tmp_path / "reqs.txt").read_text() == "urllib3==1.24.2\n"


# --- wiring: one implementation, three callers --------------------------------
# The consolidation is only durable if re-inlining the shell fails CI. These are
# the assertions that keep #1745's shape from coming back.


def _strip_comments(text: str) -> str:
    """Blank out shell/YAML/Makefile comment lines, preserving line numbering.

    A comment *describing* a removed invocation is documentation. Only live
    lines can drift.
    """
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        kept.append("" if stripped.startswith("#") else line)
    return "\n".join(kept)


# The audit binary within FLAG_WINDOW characters of an audit flag, in either
# order, so a wrapped invocation (`pip-audit \\` then the flags on the next
# line) is caught as well as a single-line one.
FLAG_WINDOW = 120
_AUDIT_FLAG = r"(?:--strict|--ignore-vuln|--disable-pip|--no-deps)"
_INVOCATION = re.compile(
    rf"pip[-_]audit(?=[^\n]{{0,{FLAG_WINDOW}}}{_AUDIT_FLAG})"
    rf"|{_AUDIT_FLAG}(?=[^\n]{{0,{FLAG_WINDOW}}}pip[-_]audit)",
    re.IGNORECASE,
)


def _invocation_sites() -> list[tuple[Path, int, str]]:
    """Every live line outside the script that spells the audit out by hand.

    Keyed on the audit *binary* plus an audit flag rather than on either alone,
    because `--strict` also belongs to `mkdocs build`, `dazzle validate`, and
    `--no-deps` to the release workflow's compiler flags.
    """
    candidates = [
        *(REPO / ".github" / "workflows").glob("*.yml"),
        *(REPO / "scripts").glob("*.sh"),
        REPO / "Makefile",
    ]
    hits: list[tuple[Path, int, str]] = []
    for path in candidates:
        if not path.is_file() or path.name == SCRIPT.name:
            continue
        for lineno, line in enumerate(
            _strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1
        ):
            if _INVOCATION.search(line):
                hits.append((path, lineno, line.strip()))
    return hits


def test_no_caller_reimplements_the_audit_flags() -> None:
    hits = _invocation_sites()
    assert hits == [], "pip-audit invoked by hand outside scripts/pip_audit.py: " + "; ".join(
        f"{path.name}:{lineno}: {text}" for path, lineno, text in hits
    )


def test_the_single_suppression_is_declared_in_exactly_one_place() -> None:
    """Two copies of an --ignore-vuln list is one copy too many."""
    carriers = [
        path
        for path in [
            SCRIPT,
            *(REPO / ".github" / "workflows").glob("*.yml"),
            *(REPO / "scripts").glob("*.sh"),
        ]
        if "MAL-2026-4750" in path.read_text(encoding="utf-8")
    ]
    assert carriers == [SCRIPT]


@pytest.mark.parametrize(
    "relative",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/main-hygiene.yml",
        "scripts/ci_local.sh",
    ],
)
def test_each_caller_goes_through_the_shared_script(relative: str) -> None:
    assert "scripts/pip_audit.py" in (REPO / relative).read_text(encoding="utf-8")


def test_the_monitor_reports_while_the_gate_still_gates() -> None:
    """main-hygiene must not red every Monday; security-tests must keep failing."""
    import yaml

    hygiene = yaml.safe_load((REPO / ".github" / "workflows" / "main-hygiene.yml").read_text())
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text())

    def run_of(doc: dict, job: str, name_prefix: str) -> str:
        steps = doc["jobs"][job]["steps"]
        return next(s["run"] for s in steps if str(s.get("name", "")).startswith(name_prefix))

    assert "--report-only" in run_of(hygiene, "hygiene", "Audit main")
    assert "--report-only" not in run_of(ci, "security-tests", "Run pip-audit")


# --- wiring: a delegated subcommand must exist -------------------------------
# `make security` delegated to `bash scripts/ci_local.sh security`, and
# ci_local.sh had no such case arm — it answered "unknown command: security" and
# exited 1. The function (`cmd_security`) was implemented and reachable only from
# inside tier1. The consolidation gate above could not see it: it checks that
# nobody re-spells the audit flags, not that the caller names a target that
# exists. Same class as #1750 — a name that resolves to nothing, so the caller's
# intent silently became an error nobody read.


_CI_LOCAL = REPO / "scripts" / "ci_local.sh"


def _dispatched_subcommands() -> set[str]:
    """Every alternative a `case` arm in ci_local.sh's dispatcher accepts.

    Matches the arm pattern rather than the command it calls, so an arm whose
    body is an if/else (`push-gate|push_gate`) counts as dispatched. Matching
    only `... ) cmd_*` reported that arm as missing — the walk mistaking an
    unusual body for an absent one, which is the failure this gate exists to
    prevent.
    """
    text = _CI_LOCAL.read_text(encoding="utf-8")
    dispatcher = text[text.index("main() {") :]
    dispatched: set[str] = set()
    for match in re.finditer(r"^\s{4}([A-Za-z0-9_|-]+)\)[ \t\n]", dispatcher, re.MULTILINE):
        dispatched.update(part for part in match.group(1).split("|"))
    return dispatched


def _delegated_subcommands() -> dict[str, str]:
    """{subcommand: make target} for every `ci_local.sh <cmd>` the Makefile runs."""
    makefile = _strip_comments((REPO / "Makefile").read_text(encoding="utf-8"))
    delegated: dict[str, str] = {}
    current = ""
    for line in makefile.splitlines():
        target = re.match(r"^([A-Za-z0-9_.-]+):", line)
        if target:
            current = target.group(1)
        call = re.search(r"bash\s+scripts/ci_local\.sh\s+([A-Za-z0-9_-]+)", line)
        if call:
            delegated.setdefault(call.group(1), current)
    return delegated


def test_every_delegated_subcommand_exists() -> None:
    """A gate that delegates to a name nothing dispatches is not a gate."""
    dispatched = _dispatched_subcommands()
    delegated = _delegated_subcommands()
    assert delegated, "no ci_local.sh delegations found — has the Makefile moved?"
    missing = {
        f"make {target} -> ci_local.sh {cmd}": sorted(dispatched)
        for cmd, target in delegated.items()
        if cmd not in dispatched
    }
    assert not missing, "delegated subcommands with no case arm: " + "; ".join(missing)


def test_the_security_gate_is_routable_and_hard_fails() -> None:
    """`make security` is the documented local entry point for the audit. It must
    reach `cmd_security`, and that command must run the shared implementation
    rather than its own copy."""
    assert "security" in _dispatched_subcommands()
    body = _CI_LOCAL.read_text(encoding="utf-8")
    assert "python scripts/pip_audit.py" in body, "cmd_security must call the one implementation"
