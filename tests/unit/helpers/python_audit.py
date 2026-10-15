"""PythonAuditAgent end-to-end scan helper (sentinel PA-LLM-07..11 tests).

``scan`` writes a throwaway project and runs one heuristic through the public
``PythonAuditAgent.check_*`` entry point, so the noqa, scan-scope and
catalogue wiring are exercised the way ``dazzle sentinel`` exercises them.
The caller asserts on the returned findings.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.sentinel.agents.python_audit import PythonAuditAgent
from dazzle.sentinel.models import Finding

#: Heuristic id → the public agent method that runs it.
CHECKS: dict[str, str] = {
    "PA-LLM-07": "check_exceptions_as_control_flow",
    "PA-LLM-08": "check_n_plus_one_in_user_code",
    "PA-LLM-09": "check_optional_instead_of_result",
    "PA-LLM-10": "check_magic_string_typing",
    "PA-LLM-11": "check_raw_sql_string_building",
}


def scan(tmp_path: Path, heuristic_id: str, files: dict[str, str]) -> list[Finding]:
    """Write ``files`` (project-relative path → source) and run one heuristic."""
    for rel, source in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    agent = PythonAuditAgent(project_path=tmp_path)
    check = getattr(agent, CHECKS[heuristic_id])
    findings: list[Finding] = check(appspec=None)
    return findings
