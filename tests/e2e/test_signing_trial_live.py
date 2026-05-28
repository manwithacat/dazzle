"""Live LLM persona signing trial. Opt-in: DAZZLE_E2E_SIGNING_TRIAL=1.

Each test runs `dazzle qa trial` against a real example app with a
real LLM persona. Slow (~2-5 min per run) and burns tokens. Gated
behind an env var so CI does not run it by default.

The trial outputs a markdown report to dev_docs/. We parse the
"Signing Outcomes" section to verify that signing detection,
inference, and functional checks all passed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _parse_signing_outcomes_from_markdown(md_text: str) -> dict[str, bool | str] | None:
    """Extract and parse the Signing Outcomes block from markdown report.

    Returns a dict with keys: detected, expected_outcome_inferred, functional_status.
    Returns None if the block is not found.
    """
    # Find the "## Signing Outcomes" section
    match = re.search(r"## Signing Outcomes\s*\n(.*?)(?=\n## |\Z)", md_text, re.DOTALL)
    if not match:
        return None

    section = match.group(1)
    outcomes = {}

    # Parse each line in the block
    # Expected format:
    # - **detected:** True
    # - **expected outcome (inferred):** signed
    # - **functional:** {'status': 'pass', 'evidence': '...'}
    # - **signature integrity:** {'status': 'pass', 'evidence': '...'}

    detected_match = re.search(r"- \*\*detected:\*\*\s*(\w+)", section)
    if detected_match:
        outcomes["detected"] = detected_match.group(1).lower() in ("true", "yes")

    expected_match = re.search(r"- \*\*expected outcome \(inferred\):\*\*\s*(\w+)", section)
    if expected_match:
        outcomes["expected_outcome_inferred"] = expected_match.group(1)

    functional_match = re.search(r"- \*\*functional:\*\*\s*(.+?)(?=\n|$)", section)
    if functional_match:
        functional_text = functional_match.group(1).strip()
        # Parse dict-like format: {'status': 'pass', 'evidence': '...'}
        if "pass" in functional_text.lower():
            outcomes["functional_status"] = "pass"
        elif "fail" in functional_text.lower():
            outcomes["functional_status"] = "fail"

    return outcomes if outcomes else None


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("DAZZLE_E2E_SIGNING_TRIAL") != "1",
    reason="Opt-in: set DAZZLE_E2E_SIGNING_TRIAL=1 to enable",
)
@pytest.mark.parametrize(
    ("app", "scenario"),
    [
        ("contact_manager", "engagement_letter_happy_path"),
        ("support_tickets", "sla_waiver_happy_path"),
    ],
)
def test_signing_trial_happy_path_with_live_llm(app: str, scenario: str, tmp_path: Path):
    """Run a signing trial scenario against a real LLM persona.

    Verifies:
    1. The trial command exits successfully.
    2. The markdown report is generated.
    3. The Signing Outcomes section is present and shows pass status.
    4. Detection, outcome inference, and functional checks all passed.
    """
    project_dir = EXAMPLES / app
    assert project_dir.exists(), f"Example app {app} not found at {project_dir}"

    # Run the trial command with a timeout of 10 minutes (600 seconds)
    result = subprocess.run(
        ["dazzle", "qa", "trial", "--scenario", scenario],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )

    # Verify command exited successfully
    assert result.returncode == 0, (
        f"Trial command failed with return code {result.returncode}.\nStderr: {result.stderr}"
    )

    # Find the generated report file in dev_docs/
    dev_docs = project_dir / "dev_docs"
    assert dev_docs.exists(), f"dev_docs directory not found in {project_dir}"

    # Find the most recently created qa-trial-{scenario}-*.md file
    pattern = f"qa-trial-{scenario}-*.md"
    reports = sorted(dev_docs.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    assert reports, f"No trial report found matching {pattern} in {dev_docs}"

    report_file = reports[0]
    report_text = report_file.read_text()

    # Parse the Signing Outcomes block
    outcomes = _parse_signing_outcomes_from_markdown(report_text)
    assert outcomes is not None, "Signing Outcomes block not found in trial report"

    # Verify signing detection
    assert outcomes.get("detected") is True, "Signing was not detected in the trial"

    # Verify expected outcome inference
    assert outcomes.get("expected_outcome_inferred") == "signed", (
        f"Expected outcome inferred as 'signed', got {outcomes.get('expected_outcome_inferred')}"
    )

    # Verify functional check passed
    assert outcomes.get("functional_status") == "pass", (
        f"Functional check did not pass, got {outcomes.get('functional_status')}"
    )
