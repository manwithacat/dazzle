"""WP-7 gate: the claim ledger + README copy-lint (dazzle.rbac.claim_ledger).

Keeps the word "provable" honest: every claim maps to a discharging artefact and
an evidence class, copy that overclaims (asserts proof for a test-class property)
fails, and the real README stays within what is discharged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("z3")

from dazzle.rbac import claim_ledger as CL  # noqa: E402
from dazzle.rbac.prove import EvidenceClass  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ledger_integrity_is_clean() -> None:
    """No undischarged proof-class claim; every anchor exists in the proof model."""
    errors = CL.verify_ledger_integrity()
    assert errors == [], errors


def test_every_proof_class_claim_is_discharged_by_the_prover() -> None:
    for claim in CL.LEDGER:
        if claim.evidence is EvidenceClass.PROOF:
            assert claim.discharged_by == "dazzle rbac prove", claim.id


def test_enforcement_claim_is_test_class_not_proof() -> None:
    """The epistemic crux: runtime enforcement is conformance-TESTED, never proved."""
    enforce = next(c for c in CL.LEDGER if c.id == "enforcement_conformance")
    assert enforce.evidence is EvidenceClass.TEST


def test_overclaim_is_detected() -> None:
    """A deliberately over-strong string must be flagged."""
    bad = "Access control is declared in the DSL and provably enforced."
    findings = CL.find_overclaims(bad, "synthetic")
    assert findings, "overclaim 'provably enforced' was not caught"
    assert "test-class" in findings[0].reason


def test_unconditional_security_overclaim_is_detected() -> None:
    findings = CL.find_overclaims("Dazzle apps are unconditionally secure.", "synthetic")
    assert findings


def test_real_readme_is_within_evidence() -> None:
    """The shipped README must not overclaim (this is the WP-7 copy-lint gate)."""
    findings = CL.lint_readme(REPO_ROOT / "README.md")
    assert findings == [], [f.excerpt for f in findings]


def test_cli_report_lint_exits_zero() -> None:
    from typer.testing import CliRunner

    from dazzle.cli.rbac import rbac_app

    result = CliRunner().invoke(rbac_app, ["report", "--lint"])
    assert result.exit_code == 0, result.output
    assert "clean" in result.output


def test_cli_report_lint_fails_on_injected_overclaim(tmp_path: Path, monkeypatch) -> None:
    """If copy overclaims, the lint must exit non-zero — the gate has teeth."""
    from typer.testing import CliRunner

    from dazzle.cli.rbac import rbac_app

    # Point the linter at a temp README that overclaims, via the ledger helper.
    bad_readme = tmp_path / "README.md"
    bad_readme.write_text("Access control is provably enforced and unconditionally secure.")
    findings = CL.lint_readme(bad_readme)
    assert len(findings) >= 2  # both 'provably enforced' and 'unconditionally secure'
    # And the CLI path surfaces a non-zero exit when findings exist (real README is
    # clean, so we assert the failure semantics via the helper + a monkeypatched root).
    import dazzle.rbac.claim_ledger as mod

    monkeypatch.setattr(mod, "lint_readme", lambda _p: findings)
    result = CliRunner().invoke(rbac_app, ["report", "--lint"])
    assert result.exit_code == 1
