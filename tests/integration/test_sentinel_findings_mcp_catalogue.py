"""End-to-end: Finding.catalogue_entry survives the full Sentinel pipeline.

Closes #1260. Asserts that the catalogue_entry field added in v0.75.0 round-trips
intact from PythonAuditAgent through FindingStore JSON persistence and back out via
the `sentinel findings` MCP handler. The MCP layer is what agents read on the next
iteration — if catalogue_entry silently drops anywhere, the feedback loop closes
weaker than designed.
"""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.mcp.server.handlers.sentinel import sentinel_findings_impl
from dazzle.sentinel.agents.python_audit import PythonAuditAgent
from dazzle.sentinel.models import (
    AgentId,
    AgentResult,
    ScanConfig,
    ScanResult,
    ScanSummary,
    ScanTrigger,
    Severity,
)
from dazzle.sentinel.store import FindingStore


def _run_and_persist(project_path: Path) -> ScanResult:
    """Run PA-LLM-07 against project_path and persist the result via FindingStore."""
    agent = PythonAuditAgent(project_path=project_path)
    findings = agent.check_exceptions_as_control_flow(appspec=None)  # type: ignore[arg-type]

    result = ScanResult(
        trigger=ScanTrigger.MANUAL,
        agent_results=[
            AgentResult(agent=AgentId.PA, findings=findings, heuristics_run=1, duration_ms=0.0)
        ],
        findings=findings,
        summary=ScanSummary(
            total_findings=len(findings),
            by_severity={Severity.MEDIUM.value: len(findings)},
            by_agent={AgentId.PA.value: len(findings)},
        ),
        config=ScanConfig(),
    )
    FindingStore(project_path).save_scan(result)
    return result


def test_catalogue_entry_round_trips_through_mcp_findings(tmp_path: Path) -> None:
    """A PA-LLM-07 finding's catalogue_entry survives store + MCP serialisation."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "sync.py").write_text(
        "def sync():\n    try:\n        v = d[k]\n    except KeyError:\n        v = None\n"
    )

    scan = _run_and_persist(tmp_path)
    assert len(scan.findings) == 1, "PA-LLM-07 should have fired exactly once on the seeded file"

    response = sentinel_findings_impl(
        project_path=tmp_path, scan_id=None, agent="PA", severity=None
    )

    assert response["count"] == 1, response
    finding_dict = response["findings"][0]
    assert finding_dict["heuristic_id"] == "PA-LLM-07"
    assert finding_dict["catalogue_entry"] == "exceptions-as-control-flow"


def test_catalogue_url_in_remediation_references(tmp_path: Path) -> None:
    """The catalogue URL is preserved in remediation.references through the round-trip."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n    try:\n        do()\n    except Exception:\n        pass\n"
    )

    _run_and_persist(tmp_path)

    response = sentinel_findings_impl(
        project_path=tmp_path, scan_id=None, agent="PA", severity=None
    )

    finding_dict = response["findings"][0]
    references = finding_dict["remediation"]["references"]
    assert any("docs/counter-priors/exceptions-as-control-flow.md" in ref for ref in references), (
        f"catalogue URL missing from remediation.references: {references!r}"
    )


def test_mcp_handler_json_output_includes_catalogue_entry(tmp_path: Path) -> None:
    """The wrapped handler's JSON string output (what the agent actually reads) carries the field."""
    from dazzle.mcp.server.handlers.sentinel import findings_handler

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "y.py").write_text(
        "def g():\n    try:\n        v = obj.attr\n    except AttributeError:\n        v = None\n"
    )

    _run_and_persist(tmp_path)

    json_response = findings_handler(tmp_path, {"agent": "PA"})
    parsed = json.loads(json_response)

    assert parsed["count"] == 1
    assert parsed["findings"][0]["catalogue_entry"] == "exceptions-as-control-flow"
