"""WP-0 structural gate for the RBAC proof model (docs/reference/rbac-proof-model.md).

This is the machine-checkable gate for Phase 0 of the RBAC proof substrate
(WP-0 → WP-2 + WP-7). It does not prove anything about access control; it asserts
that the normative *proof-obligation model* is present and complete, so that every
downstream WP (and the WP-7 claim ledger) has the clauses it references.

If a section is renamed or an evidence-class row is dropped, this fails — forcing
the model and its consumers back into sync.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[2] / "docs" / "reference" / "rbac-proof-model.md"

# Stable anchors the claim ledger (WP-7) and downstream WPs key off.
REQUIRED_ANCHORS = [
    "WP0:PROOF-MODEL",
    "WP0:FORMALISATION",
    "WP0:THEOREM",
    "WP0:ASSUMPTIONS",
    "WP0:TRUST-CHAIN",
    "WP0:EVIDENCE-CLASSES",
    "WP0:REBAC",
    "WP0:NON-GOALS",
]

# The three theorem directions must all be named (§2).
REQUIRED_THEOREM_TERMS = ["No-escalation", "No-false-deny", "over-approximation"]

# Assumption set A must enumerate all four (§3).
REQUIRED_ASSUMPTIONS = ["A.1", "A.2", "A.3", "A.4"]

# The three evidence classes that license external copy (§5).
EVIDENCE_CLASSES = {"Proof", "Enumeration", "Test"}

# Every WP whose properties must appear with an evidence class in the §5 table.
REQUIRED_WP_ROWS = ["WP-1", "WP-2", "WP-3", "WP-4", "WP-5", "WP-6"]


@pytest.fixture(scope="module")
def text() -> str:
    assert DOC.exists(), f"WP-0 proof model missing: {DOC}"
    return DOC.read_text(encoding="utf-8")


# (clause, terms the clause must state). Downstream WPs and the WP-7 claim
# ledger key off these, so a dropped term is a broken reference.
_CLAUSES: dict[str, tuple[str, ...]] = {
    "anchors": tuple(REQUIRED_ANCHORS),
    "effective-decision-composition": (
        "allow(p, r, a,",
        "tenant_RLS",
        "role_perm",
        "scope_pred",
        "rebac_grant",
    ),
    "theorem-directions": tuple(REQUIRED_THEOREM_TERMS),
    "assumption-set": tuple(REQUIRED_ASSUMPTIONS),
    "trust-chain-links": ("PROOF", "TEST", "ASSUMED"),
    "rebac-declared-classes-only": ("grant_schema", "out of scope", "residual"),
    "non-goals-scoped-tcb": ("scoped", "TCB"),
}


@pytest.mark.parametrize("terms", list(_CLAUSES.values()), ids=list(_CLAUSES))
def test_clause_states_its_terms(text: str, terms: tuple[str, ...]) -> None:
    lowered = text.lower()
    # all-lowercase terms match case-insensitively; anything else exactly
    missing = [t for t in terms if t not in (lowered if t == t.lower() else text)]
    assert not missing, f"proof model clause lost: {missing}"


def test_evidence_class_table_complete(text: str) -> None:
    """Every required WP appears in the §5 table with a valid evidence class."""
    # Grab markdown table rows that carry a WP id in the 'Owning WP' column.
    rows = [ln for ln in text.splitlines() if ln.strip().startswith("|") and "WP-" in ln]
    table_blob = "\n".join(rows)
    for wp in REQUIRED_WP_ROWS:
        assert wp in table_blob, f"evidence-class table missing a row for {wp}"
    # Each table row must name exactly one of the three evidence classes.
    classless = []
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if not any(c.startswith("WP-") for c in cells):
            continue
        if not (EVIDENCE_CLASSES & set(re.split(r"[ +/]", " ".join(cells)))):
            classless.append(row)
    assert not classless, f"evidence-class rows without a valid class: {classless}"
