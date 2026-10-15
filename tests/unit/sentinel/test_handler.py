"""Tests for the sentinel MCP tool and the scan/suppress handlers the CLI calls.

``findings``, ``status``, ``history`` and ``fuzz_summary`` are the operations the
``sentinel`` tool registers, so they are driven through ``handle_sentinel``.
``scan`` and ``suppress`` are not on the tool; ``dazzle sentinel scan|suppress``
calls their handlers directly, so these tests do too.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from dazzle.mcp.server.handlers.sentinel import scan_handler, suppress_handler
from dazzle.mcp.server.handlers_consolidated import handle_sentinel
from dazzle.mcp.server.tools_consolidated import get_consolidated_tools
from dazzle.sentinel.agents import get_all_agents
from dazzle.sentinel.models import (
    AgentId,
    AgentResult,
    Finding,
    ScanResult,
    ScanSummary,
    Severity,
)
from dazzle.sentinel.store import FindingStore

from .conftest import make_appspec, make_entity, pk_field, str_field


def _finding(
    heuristic_id: str = "DI-01", severity: Severity = Severity.HIGH, agent: AgentId = AgentId.DI
) -> Finding:
    return Finding(
        agent=agent,
        heuristic_id=heuristic_id,
        category="test",
        subcategory="test",
        severity=severity,
        title=f"Finding {heuristic_id}",
        description="test finding",
        entity_name="Task",
    )


def _scan_result(findings: list[Finding] | None = None) -> ScanResult:
    f = findings or [_finding()]
    return ScanResult(
        findings=f,
        summary=ScanSummary(total_findings=len(f)),
        agent_results=[AgentResult(agent=AgentId.DI, findings=f, heuristics_run=1)],
    )


def _call(project: Path, operation: str, **args: Any) -> Any:
    raw = handle_sentinel({"operation": operation, "_resolved_project_path": project, **args})
    return raw if operation == "fuzz_summary" and not raw.startswith("{") else json.loads(raw)


# ---------------------------------------------------------------------------
# scan (CLI)
# ---------------------------------------------------------------------------

_BASE_KEYS = {"status", "scan_id", "summary", "duration_ms"}


@pytest.mark.parametrize(
    ("detail", "keys"),
    [
        pytest.param("metrics", _BASE_KEYS, id="metrics-summary-only"),
        pytest.param("issues", _BASE_KEYS | {"findings"}, id="issues-default"),
        pytest.param("full", _BASE_KEYS | {"findings", "agent_results"}, id="full-adds-agents"),
    ],
)
def test_scan_detail_levels(tmp_path: Path, detail: str, keys: set[str]) -> None:
    entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
    with patch(
        "dazzle.mcp.server.handlers.sentinel.load_project_appspec",
        return_value=make_appspec([entity]),
    ):
        # PA shells out to ruff/semgrep over the project; it has its own tests.
        result = json.loads(scan_handler(tmp_path, {"detail": detail, "agents": ["AA", "BL"]}))
    assert set(result) == keys
    assert result["status"] == "ok"
    # The scan is persisted under the id it reports.
    assert FindingStore(tmp_path).load_scan(result["scan_id"]) is not None
    # AA-02 (no access spec) fires on the bare Task alongside a LOW BL-07, which
    # the default issues level drops (medium and above only).
    assert result["summary"]["total_findings"] == 2
    if "findings" in result:
        ids = [f["heuristic_id"] for f in result["findings"]]
        assert ids == (["AA-02", "BL-07"] if detail == "full" else ["AA-02"])
    if "agent_results" in result:
        assert [r["agent"] for r in result["agent_results"]] == ["AA", "BL"]


def test_scan_load_failure_is_error(tmp_path: Path) -> None:
    with patch(
        "dazzle.mcp.server.handlers.sentinel.load_project_appspec",
        side_effect=Exception("parse error"),
    ):
        assert json.loads(scan_handler(tmp_path, {})) == {"error": "parse error"}


# ---------------------------------------------------------------------------
# findings (tool)
# ---------------------------------------------------------------------------

_SEEDED = [
    _finding("DI-01", Severity.HIGH),
    _finding("DI-02", Severity.LOW),
    _finding("AA-01", Severity.HIGH, AgentId.AA),
]


@pytest.mark.parametrize(
    ("seed", "args", "expected_ids"),
    [
        pytest.param(False, {}, [], id="no-scans-empty"),
        pytest.param(True, {}, ["DI-01", "DI-02", "AA-01"], id="latest-scan"),
        pytest.param(True, {"agent": "DI"}, ["DI-01", "DI-02"], id="filter-agent"),
        pytest.param(True, {"severity": "high"}, ["DI-01", "AA-01"], id="filter-severity"),
        pytest.param(True, {"severity": "high", "agent": "DI"}, ["DI-01"], id="filters-combine"),
        pytest.param(True, {"scan_id": "SEEDED"}, ["DI-01", "DI-02", "AA-01"], id="by-scan-id"),
    ],
)
def test_findings_filters(
    tmp_path: Path, seed: bool, args: dict[str, Any], expected_ids: list[str]
) -> None:
    if seed:
        scan = _scan_result(_SEEDED)
        FindingStore(tmp_path).save_scan(scan)
        args = {k: (scan.scan_id if v == "SEEDED" else v) for k, v in args.items()}
    result = _call(tmp_path, "findings", **args)
    assert [f["heuristic_id"] for f in result["findings"]] == expected_ids
    assert result["count"] == len(expected_ids)
    # The filters actually applied are echoed so a payload can be audited.
    assert result["filters"] == {
        "scan_id": args.get("scan_id"),
        "agent": args.get("agent"),
        "severity": args.get("severity"),
    }


@pytest.mark.parametrize(
    ("args", "error_has"),
    [
        # #1753: the schema advertised `severity_threshold` while the handler read
        # `severity`, so a caller following the schema got every finding back
        # unfiltered. The wrong key is an error naming the live one.
        pytest.param({"severity_threshold": "high"}, "severity=", id="severity-threshold-key-1753"),
        # An unknown severity used to rank to 4, i.e. "everything".
        pytest.param({"severity": "severe"}, "Unknown severity 'severe'", id="unknown-severity"),
        pytest.param({"scan_id": "nonexistent"}, "'nonexistent' not found", id="unknown-scan-id"),
    ],
)
def test_findings_rejects_bad_arguments(
    tmp_path: Path, args: dict[str, Any], error_has: str
) -> None:
    FindingStore(tmp_path).save_scan(_scan_result(_SEEDED))
    result = _call(tmp_path, "findings", **args)
    assert set(result) == {"error"}
    assert error_has in result["error"]


def test_tool_schema_declares_the_findings_filter_it_reads() -> None:
    """#1753: the schema is the only place an agent learns parameter names, so a
    key it declares for an op must be the key that op reads. `severity_threshold`
    is a `dazzle sentinel scan` (CLI) parameter, never the findings filter."""
    tools = {t.name: t for t in get_consolidated_tools()}
    props = tools["sentinel"].input_schema["properties"]
    assert "severity_threshold" not in props
    assert props["severity"]["enum"] == ["critical", "high", "medium", "low", "info"]


# ---------------------------------------------------------------------------
# suppress (CLI)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param(
            {"finding_id": "SEEDED", "reason": "false positive"},
            {"status": "suppressed", "finding_id": "SEEDED"},
            id="suppresses-latest-finding",
        ),
        pytest.param({}, {"error": "finding_id and reason are required"}, id="missing-params"),
        pytest.param(
            {"finding_id": "unknown", "reason": "test"},
            {"error": "Finding 'unknown' not found in latest scan"},
            id="unknown-finding",
        ),
    ],
)
def test_suppress(tmp_path: Path, args: dict[str, Any], expected: dict[str, Any]) -> None:
    seeded = _finding()
    FindingStore(tmp_path).save_scan(_scan_result([seeded]))

    def fill(d: dict[str, Any]) -> dict[str, Any]:
        return {k: (seeded.finding_id if v == "SEEDED" else v) for k, v in d.items()}

    assert json.loads(suppress_handler(tmp_path, fill(args))) == fill(expected)


# ---------------------------------------------------------------------------
# status / history (tool)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scanned", [False, True], ids=["no-scan", "after-scan"])
def test_status(tmp_path: Path, scanned: bool) -> None:
    scan = _scan_result()
    if scanned:
        FindingStore(tmp_path).save_scan(scan)
    result = _call(tmp_path, "status")
    assert result["agents"] == [
        {"id": a.agent_id.value, "heuristics": len(a.get_heuristics())} for a in get_all_agents()
    ]
    assert len(result["agents"]) == 9
    last = result["last_scan"]
    assert (last["scan_id"] if last else None) == (scan.scan_id if scanned else None)


@pytest.mark.parametrize(
    ("n_scans", "args", "count"),
    [
        pytest.param(0, {}, 0, id="empty"),
        pytest.param(2, {}, 2, id="all-scans"),
        pytest.param(5, {"limit": 2}, 2, id="respects-limit"),
    ],
)
def test_history(tmp_path: Path, n_scans: int, args: dict[str, Any], count: int) -> None:
    store = FindingStore(tmp_path)
    for _ in range(n_scans):
        store.save_scan(_scan_result())
    result = _call(tmp_path, "history", **args)
    assert result["count"] == len(result["scans"]) == count


# ---------------------------------------------------------------------------
# fuzz_summary (tool) — the campaign itself is the fuzzer's own test subject.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "samples"),
    [pytest.param({}, 10, id="default-10-samples"), pytest.param({"samples": 5}, 5, id="samples")],
)
def test_fuzz_summary_returns_markdown(tmp_path: Path, args: dict[str, Any], samples: int) -> None:
    with patch(
        "dazzle.mcp.server.handlers.sentinel.sentinel_fuzz_summary_impl",
        return_value="# Fuzz Report\n\n0 samples",
    ) as impl:
        assert _call(tmp_path, "fuzz_summary", **args) == "# Fuzz Report\n\n0 samples"
    impl.assert_called_once_with(examples_dir=tmp_path, samples=samples)


def test_fuzz_summary_error_is_json(tmp_path: Path) -> None:
    with patch(
        "dazzle.mcp.server.handlers.sentinel.sentinel_fuzz_summary_impl",
        side_effect=RuntimeError("corpus empty"),
    ) as impl:
        assert _call(tmp_path, "fuzz_summary") == {"error": "corpus empty"}
    impl.assert_called_once()
