"""WP-2 gate: the RBAC meta-property prover (dazzle.rbac.prove + `dazzle rbac prove`).

Two halves, per the WP-2 acceptance criteria:
  - known-good example apps yield certificates (every property proved, CLI exit 0);
  - seeded-broken inputs yield the correct counter-model / failure (anti-vacuity —
    a prover that cannot fail proves nothing).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("z3")

from dazzle.core.appspec_loader import load_project_appspec  # noqa: E402
from dazzle.core.ir.predicates import (  # noqa: E402
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.rbac import prove as P  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CORPUS = ["hr_records", "support_tickets", "simple_task"]


# --------------------------------------------------------------------------- #
# Known-good: example apps prove clean and discharge obligations.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("example", CORPUS)
def test_example_app_all_properties_proved(example: str) -> None:
    report = P.prove_all(load_project_appspec(EXAMPLES / example))
    assert report.passed, [(p.name, p.violations) for p in report.properties if not p.passed]
    # The proof must do real, app-specific work — not vacuously pass everything.
    assert report.substantive_obligations > 0
    # Least-privilege actually proves containments on a multi-persona app, and is
    # honestly labelled INFORMATIONAL (the lattice), not a pass/fail gate.
    lp = next(p for p in report.properties if p.name == "least_privilege")
    assert lp.status is P.Status.INFORMATIONAL
    assert lp.obligations_discharged > 0
    # scope_satisfiability is the substantive per-app proof.
    sat = next(p for p in report.properties if p.name == "scope_satisfiability")
    assert sat.status is P.Status.PROVED


# --------------------------------------------------------------------------- #
# Seeded-broken: each prover primitive must catch its failure with a witness.
# --------------------------------------------------------------------------- #


def test_containment_proves_true_and_refutes_false() -> None:
    owner = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
    everything = Tautology()
    # owner ⊆ everything is PROVED (None).
    assert P.prove_containment(owner, everything) is None
    # everything ⊆ owner is REFUTED with a counter-model.
    cm = P.prove_containment(everything, owner)
    assert cm is not None and cm["row__owner_id"] != cm["user__id"]


def test_disjoint_scopes_are_mutually_non_contained() -> None:
    a = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="open"))
    b = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="closed"))
    assert P.prove_containment(a, b) is not None
    assert P.prove_containment(b, a) is not None


def test_deny_overrides_correct_holds_broken_refuted() -> None:
    import z3

    # Correct composition: allow = permit ∧ ¬forbid → forbid wins (proved).
    assert P._deny_overrides_violation(P._correct_composition) is None
    # Broken composition: allow = permit ∨ forbid → forbid does NOT win.
    broken = lambda permit, forbid: z3.Or(permit, forbid)  # noqa: E731
    cm = P._deny_overrides_violation(broken)
    assert cm is not None


def test_scope_satisfiability_flags_a_dead_rule() -> None:
    """A self-contradictory scope (status == open AND status == closed) must be
    caught as UNSATISFIABLE — a dead rule that silently denies everything."""
    dead = BoolComposite.make(
        BoolOp.AND,
        [
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="open")),
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="closed")),
        ],
    )
    fake = SimpleNamespace(
        name="fake",
        domain=SimpleNamespace(
            entities=[
                SimpleNamespace(
                    name="Doc",
                    access=SimpleNamespace(
                        scopes=[SimpleNamespace(operation="list", personas=["x"], predicate=dead)]
                    ),
                )
            ]
        ),
    )
    report = P.prove_scopes_satisfiable(fake)  # type: ignore[arg-type]
    assert report.passed is False
    assert report.status is P.Status.FAILED
    assert any("UNSATISFIABLE" in v.description for v in report.violations)


def test_contradiction_scope_flagged_as_dead_rule() -> None:
    """review N-2: a raw Contradiction scope (unconditional deny) must be flagged,
    not silently skipped as a 'trivial constant'."""
    from dazzle.core.ir.predicates import Contradiction

    fake = SimpleNamespace(
        name="fake",
        domain=SimpleNamespace(
            entities=[
                SimpleNamespace(
                    name="Doc",
                    access=SimpleNamespace(
                        scopes=[
                            SimpleNamespace(
                                operation="list", personas=["x"], predicate=Contradiction()
                            )
                        ]
                    ),
                )
            ]
        ),
    )
    report = P.prove_scopes_satisfiable(fake)  # type: ignore[arg-type]
    assert report.passed is False
    assert any("CONTRADICTION" in v.description for v in report.violations)


def test_role_hierarchy_cycle_detector() -> None:
    # Acyclic chain → None.
    assert P._find_cycle([("a", "b"), ("b", "c")]) is None
    # Cycle a→b→a → returns the cycle.
    cyc = P._find_cycle([("a", "b"), ("b", "a")])
    assert cyc is not None and cyc[0] == cyc[-1]
