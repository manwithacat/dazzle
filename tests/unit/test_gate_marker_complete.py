"""Completeness gate for the ``gate`` marker — the ``/ship`` pre-flight selector.

``/ship`` runs its fast, DB-free structural pre-flight as ``pytest -m gate``. For
that to stay honest, every gate test must actually carry the marker — otherwise it
silently drops from the local pre-flight and only fails in CI's full suite. That is
the #1466 class: ``test_deferred_imports_ratchet_1438`` matched no ``/ship`` glob,
wasn't in the hand-list, and produced a red badge the local pre-flight could not
have caught (v0.86.10 → .11).

This meta-gate enforces marking for the three unambiguous, high-churn gate families
— ``*drift*``, ``test_no_*``, ``*ratchet*`` — where new gates predominantly appear
(and where #1466 lived). Those names are reliable gate indicators with no false
matches. The explicit ``*_gate`` / ``*_contract`` / ``*_cap`` gates are also marked
by convention but are deliberately NOT regex-enforced here: those substrings
false-match non-gates (``ai_gateway``, ``gated_list_helpers``, the separately-jobbed
``ux_contracts``), so a deny-list would be noisier than the protection is worth. Add
``pytestmark = pytest.mark.gate`` when you add such a gate.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

UNIT = Path(__file__).parent

# Unambiguous gate-name families that MUST carry @pytest.mark.gate.
_ENFORCED = re.compile(r"(drift|ratchet)")


def _is_enforced_gate_name(name: str) -> bool:
    return name.startswith("test_no_") or bool(_ENFORCED.search(name))


def test_high_churn_gate_families_are_marked() -> None:
    """Every drift / test_no_ / ratchet test must be selectable via ``-m gate``."""
    missing = [
        f.name
        for f in sorted(UNIT.glob("test_*.py"))
        if _is_enforced_gate_name(f.name) and "pytest.mark.gate" not in f.read_text()
    ]
    assert not missing, (
        "These gate tests (drift / test_no_ / ratchet families) lack "
        "`pytestmark = pytest.mark.gate`, so /ship's `pytest -m gate` pre-flight "
        "would skip them (the #1466 class). Add the marker:\n  " + "\n  ".join(missing)
    )
