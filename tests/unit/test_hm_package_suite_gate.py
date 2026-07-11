"""The HM package's non-browser suite runs inside the Dazzle gate sweep.

Closes the stale-dist class (2026-07-10: a shadow-token change shipped
without a dist rebuild and sat unnoticed — HM tests only ran in the
standalone repo's CI post-sync). Browser suites (behaviour/visual/wcag)
stay standalone-CI-only; this gate is the fast structural set."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.gate, pytest.mark.xdist_group("hm-package-suite")]

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"
NON_BROWSER = [
    "tests/test_contract.py",
    "tests/test_boundary.py",
    "tests/test_contracts.py",
    "tests/test_hyperpart_cohesion.py",
    "tests/test_css_parse_integrity.py",
    "tests/test_icon_contract.py",
    "tests/test_pretty.py",
    "tests/test_morph_template_gates.py",
    "tests/test_agent_didactics.py",
    # tools/template_lint.py is exercised by test_morph_template_gates
]


def test_hm_non_browser_suite_is_green() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *NON_BROWSER,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(HM),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    # Cap nested output: full pytest assertion diffs can dump multi-KB CSS
    # (e.g. catalogue drift) and flood CI logs. Prefer the tail of stderr
    # (failures) and a short stdout tail.
    assert proc.returncode == 0, (
        "HM package non-browser suite failed inside the monorepo gate sweep "
        "(the stale-dist class). Output:\n"
        + (proc.stderr[-2000:] if proc.stderr else "")
        + (proc.stdout[-1500:] if proc.stdout else "")
    )
