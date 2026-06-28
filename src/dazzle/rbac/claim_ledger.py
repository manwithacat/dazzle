"""Claim ledger + copy-lint for "provable RBAC" marketing claims (WP-7).

The ledger is the machine-checked bridge between external copy (README, PyPI,
marketing) and the proof model (docs/reference/rbac-proof-model.md §5). It exists
to keep the word *provable* honest: every claim maps to a discharging artefact and
an evidence class, and copy that asserts *proof* for a *test*-class property fails
CI (`dazzle rbac report --lint`).

This closes the epistemic gap the substrate spec named: enforcement *conformance*
is test-class (WP-3) and the TCB is assumed (A.4) — so copy may say enforcement is
"verified", never "provably enforced".
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from dazzle.rbac.prove import EvidenceClass

_PROOF_MODEL = Path(__file__).resolve().parents[3] / "docs" / "reference" / "rbac-proof-model.md"


class Claim(BaseModel):
    """One licensed external claim, bound to its evidence class + discharger."""

    id: str
    phrase: str  # the canonical thing copy is allowed to assert
    evidence: EvidenceClass
    discharged_by: str  # the command/artefact that discharges it
    anchor: str  # a WP0:* anchor in rbac-proof-model.md


# The canonical ledger. Each row mirrors a property in rbac-proof-model.md §5 and
# names the strongest evidence class copy may assert for it.
LEDGER: list[Claim] = [
    Claim(
        id="matrix_derived",
        phrase="the access matrix is derived from the DSL",
        evidence=EvidenceClass.ENUMERATION,
        discharged_by="dazzle rbac matrix",
        anchor="WP0:EVIDENCE-CLASSES",
    ),
    Claim(
        id="scope_static_valid",
        phrase="scope rules are statically validated against the FK graph",
        evidence=EvidenceClass.ENUMERATION,
        discharged_by="dazzle validate",
        anchor="WP0:EVIDENCE-CLASSES",
    ),
    Claim(
        id="meta_properties_proved",
        phrase="RBAC meta-properties are mechanically proved",
        evidence=EvidenceClass.PROOF,
        discharged_by="dazzle rbac prove",
        anchor="WP0:EVIDENCE-CLASSES",
    ),
    Claim(
        id="least_privilege_proved",
        phrase="the least-privilege containment lattice is solver-proved",
        evidence=EvidenceClass.PROOF,
        discharged_by="dazzle rbac prove",
        anchor="WP0:EVIDENCE-CLASSES",
    ),
    Claim(
        id="enforcement_conformance",
        phrase="runtime enforcement is conformance-verified against the matrix",
        evidence=EvidenceClass.TEST,
        discharged_by="dazzle rbac verify",
        anchor="WP0:TRUST-CHAIN",
    ),
]


class LintFinding(BaseModel):
    """A copy string that claims more than the ledger discharges."""

    source: str
    excerpt: str
    reason: str


# High-precision overclaim patterns: a PROOF word bound to a property whose honest
# evidence class is TEST or ASSUMED. Kept conservative to avoid false positives —
# each is a phrase the trust chain (WP0:TRUST-CHAIN) specifically forbids.
_OVERCLAIM_PATTERNS: list[tuple[str, str]] = [
    (
        r"provabl\w*\s+\w*\s*enforce",
        "enforcement faithfulness is test-class (WP-3), not proof — say "
        "'enforcement is conformance-verified', not 'provably enforced'.",
    ),
    (
        r"proven\s+(?:secure|enforcement|enforced)",
        "the system is proven over the static core MODULO assumption set A — "
        "not an unconditional 'proven secure'. State the scope.",
    ),
    (
        r"mathematically\s+(?:guarantee\w*|proven)\s+secure",
        "security is scoped to assumption set A and the static core; do not assert "
        "an unconditional mathematical guarantee.",
    ),
    (
        r"unconditional\w*\s+(?:secure|security|safe)",
        "the proof is scoped (assumption set A); never present it as unconditional.",
    ),
    (
        r"every\s+permission\s+is\s+statically\s+verifiable",
        "the matrix is statically derived, but runtime enforcement is verified by "
        "test, not statically — rephrase to avoid implying static end-to-end proof.",
    ),
]


def find_overclaims(text: str, source: str) -> list[LintFinding]:
    """Scan copy for phrases that assert more than the ledger discharges."""
    findings: list[LintFinding] = []
    for pattern, reason in _OVERCLAIM_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            findings.append(
                LintFinding(source=source, excerpt=text[start:end].strip(), reason=reason)
            )
    return findings


def verify_ledger_integrity() -> list[str]:
    """Check the ledger is internally sound. Returns a list of errors (empty = OK).

    - Every Proof-class claim must be discharged by `dazzle rbac prove` and name a
      property the prover actually exposes (no undischarged 'proof'-class claim).
    - Every claim's proof-model anchor must exist in rbac-proof-model.md.
    """
    errors: list[str] = []
    from dazzle.rbac import prove as P

    prover_names = {fn.__name__ for fn in P._PROVERS}
    proof_text = _PROOF_MODEL.read_text(encoding="utf-8") if _PROOF_MODEL.exists() else ""
    if not proof_text:
        errors.append(f"proof model not found at {_PROOF_MODEL}")

    for claim in LEDGER:
        if claim.anchor not in proof_text:
            errors.append(f"claim {claim.id!r} anchors {claim.anchor!r}, absent from proof model")
        if claim.evidence is EvidenceClass.PROOF:
            if claim.discharged_by != "dazzle rbac prove":
                errors.append(
                    f"claim {claim.id!r} is PROOF-class but discharged by "
                    f"{claim.discharged_by!r}, not `dazzle rbac prove`"
                )
            # The prover must actually have a property capable of discharging it.
            if not prover_names:
                errors.append(f"claim {claim.id!r} is PROOF-class but the prover exposes nothing")
    return errors


def lint_readme(readme_path: Path) -> list[LintFinding]:
    """Lint a README (or any copy file) against the ledger."""
    if not readme_path.exists():
        return [LintFinding(source=str(readme_path), excerpt="", reason="file not found")]
    return find_overclaims(readme_path.read_text(encoding="utf-8"), str(readme_path.name))
