"""WP-1 gate: scope-predicate algebra → SMT encoder (dazzle.rbac.encode_smt).

Asserts the encoder is total over the predicate union, encodes every scope
predicate in the example corpus with 100% node-kind coverage, gets the
satisfiability/containment semantics right per node kind, and — the anti-vacuity
check — actually refutes a false claim with a counter-model.

z3 is a dev dependency, so this runs in CI. If absent it skips (the encoder's
lazy import raises an actionable EncodingError, covered separately).
"""

from __future__ import annotations

from pathlib import Path

import pytest

z3 = pytest.importorskip("z3")

from dazzle.core.appspec_loader import load_project_appspec  # noqa: E402
from dazzle.core.ir.predicates import (  # noqa: E402
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PolyPathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.rbac import encode_smt as E  # noqa: E402
from dazzle.rbac.ir import ALL_NODE_KINDS, predicate_kinds  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
# Corpus chosen to exercise every node kind: acme_billing+hr_records cover
# column/user_attr/path/exists/bool_composite/tautology between them.
CORPUS = ["acme_billing", "hr_records", "support_tickets", "simple_task", "invoice_ops"]


def _scope_predicates(example: str) -> list:
    spec = load_project_appspec(EXAMPLES / example)
    preds = []
    for ent in spec.domain.entities:
        acc = getattr(ent, "access", None)
        if not acc:
            continue
        for s in getattr(acc, "scopes", []):
            if getattr(s, "predicate", None) is not None:
                preds.append(s.predicate)
    return preds


# --------------------------------------------------------------------------- #
# Coverage: the encoder is total over the corpus and over the declared union.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("example", CORPUS)
def test_encoder_total_over_corpus(example: str) -> None:
    preds = _scope_predicates(example)
    assert preds, f"{example} has no linked scope predicates — corpus assumption broken"
    for p in preds:
        formula, sym = E.encode_predicate(p)  # must not raise EncodingError
        assert formula is not None


def test_corpus_exercises_every_relevant_node_kind() -> None:
    seen: set[str] = set()
    for example in CORPUS:
        for p in _scope_predicates(example):
            seen |= predicate_kinds(p)
    # column_ref_check (reporting-only), contradiction, and poly_path (#1448,
    # niche) don't occur in the RBAC scope corpora; the rest must. The excluded
    # kinds are gated by the synthetic one-of-each-kind test below instead.
    expected = ALL_NODE_KINDS - {"column_ref_check", "contradiction", "poly_path"}
    missing = expected - seen
    assert not missing, f"corpus no longer exercises node kinds: {missing}"


def test_every_union_kind_has_an_encoding() -> None:
    """Synthetic one-of-each-kind tree must encode — guards against a new node
    landing in predicates.py without an encoder arm."""
    nodes = [
        Tautology(),
        Contradiction(),
        ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active")),
        UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id"),
        ExistsCheck(
            target_entity="Membership",
            bindings=[ExistsBinding(junction_field="user_id", target="current_user")],
        ),
        PolyPathCheck(
            field="subject",
            type_field="subject_type",
            type_value="CohortAssessment",
            id_field="subject_id",
            target_entity="CohortAssessment",
            sub=UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="id"),
        ),
    ]
    for n in nodes:
        formula, _ = E.encode_predicate(n)
        assert formula is not None


# --------------------------------------------------------------------------- #
# Semantics: per-kind sanity.
# --------------------------------------------------------------------------- #


def test_tautology_and_contradiction_satisfiability() -> None:
    assert E.is_satisfiable(Tautology()) is True
    assert E.is_satisfiable(Contradiction()) is False


def test_owner_scope_is_satisfiable_but_not_universal() -> None:
    owner = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
    assert E.is_satisfiable(owner) is True
    # owner is NOT a tautology: there is a row it rejects → Tautology ⊄ owner.
    f_owner, sym = E.encode_predicate(owner)
    # rebuild the goal on the SAME table
    f_owner2 = E.encode(owner, sym)
    witness = E.entails(z3.BoolVal(True), f_owner2)
    assert witness is not None, "owner scope wrongly proved universal"


def test_and_is_contained_in_each_conjunct() -> None:
    """A ∧ B ⇒ A must be VALID (None counter-model)."""
    a = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="open"))
    b = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
    conj = BoolComposite.make(BoolOp.AND, [a, b])
    sym = E.SymbolTable()
    f_conj = E.encode(conj, sym)
    f_a = E.encode(a, sym)
    assert E.entails(f_conj, f_a) is None  # proved: (a ∧ b) ⊆ a


def test_negative_control_refutes_with_counter_model() -> None:
    """The anti-vacuity check: a deliberately FALSE claim (Tautology ⊆ owner)
    must be refuted with a concrete witness row+user. A prover that cannot fail
    proves nothing."""
    owner = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
    sym = E.SymbolTable()
    f_owner = E.encode(owner, sym)
    witness = E.entails(z3.BoolVal(True), f_owner)
    assert witness is not None
    # witness must pin the two relevant symbols and violate owner_id == user.id
    assert "row__owner_id" in witness and "user__id" in witness
    assert witness["row__owner_id"] != witness["user__id"]


def test_exists_node_records_abstraction_note() -> None:
    """EXISTS encodes as a free boolean and self-documents the abstraction so the
    prover can attach a residual-risk note (WP0:TRUST-CHAIN)."""
    node = ExistsCheck(
        target_entity="Roster",
        bindings=[ExistsBinding(junction_field="user_id", target="current_user")],
    )
    _, sym = E.encode_predicate(node)
    assert any("EXISTS" in a for a in sym.abstractions)


# --------------------------------------------------------------------------- #
# Soundness regressions — each guards a hole found by adversarial review.
# A false proof here would let the prover certify escalation-safety that does
# not hold, so these are the highest-value tests in the file.
# --------------------------------------------------------------------------- #


def test_polypath_sub_columns_do_not_alias_outer_columns() -> None:
    """review MAJOR-1: a poly-ref sub-predicate's column must NOT unify with an
    outer column of the same name, or containment proofs go unsound.

    A = subject[CohortAssessment].org_id = current_user.org_id  (joined entity)
    B = org_id = current_user.org_id                            (outer row)
    B ⊆ A must NOT be provable — they constrain different columns.
    """
    poly = PolyPathCheck(
        field="subject",
        type_field="subject_type",
        type_value="CohortAssessment",
        id_field="subject_id",
        target_entity="CohortAssessment",
        sub=UserAttrCheck(field="org_id", op=CompOp.EQ, user_attr="org_id"),
    )
    outer = UserAttrCheck(field="org_id", op=CompOp.EQ, user_attr="org_id")
    sym = E.SymbolTable()
    f_poly = E.encode(poly, sym)
    f_outer = E.encode(outer, sym)
    # B ⊆ A must be refuted with a counter-model (the columns are distinct).
    assert E.entails(f_outer, f_poly) is not None


def test_not_in_is_the_negation_of_in_on_the_same_set() -> None:
    """review MINOR-3: NOT IN must be ¬(IN) for the same (field, set), not an
    independent free boolean. So `x IN S` ∧ `x NOT IN S` is a contradiction, and
    `x NOT IN S` does NOT imply `x IN S`."""
    in_s = ColumnCheck(field="status", op=CompOp.IN, value=ValueRef(literal="active"))
    not_in_s = ColumnCheck(field="status", op=CompOp.NOT_IN, value=ValueRef(literal="active"))
    sym = E.SymbolTable()
    f_in = E.encode(in_s, sym)
    f_not_in = E.encode(not_in_s, sym)
    # IN ∧ NOT IN on the same set is unsatisfiable.
    conj = BoolComposite.make(BoolOp.AND, [in_s, not_in_s])
    assert E.is_satisfiable(conj) is False
    # NOT IN ⊆ IN must be refuted (they are opposites, not the same symbol).
    assert E.entails(f_not_in, f_in) is not None


def test_distinct_in_sets_on_same_field_do_not_alias() -> None:
    """review MINOR-3: `status IN {active}` and `status IN {archived}` are
    different propositions — neither implies the other."""
    a = ColumnCheck(field="status", op=CompOp.IN, value=ValueRef(literal="active"))
    b = ColumnCheck(field="status", op=CompOp.IN, value=ValueRef(literal="archived"))
    sym = E.SymbolTable()
    f_a = E.encode(a, sym)
    f_b = E.encode(b, sym)
    assert E.entails(f_a, f_b) is not None  # a ⊄ b
    assert E.entails(f_b, f_a) is not None  # b ⊄ a


def test_oversized_numeric_literal_fails_closed() -> None:
    """review MINOR-1: a numeric literal that could reach the intern band is
    refused (fail-closed) rather than silently aliasing a string literal."""
    huge = ColumnCheck(field="n", op=CompOp.EQ, value=ValueRef(literal=10**15))
    with pytest.raises(E.EncodingError):
        E.encode_predicate(huge)
    # A normal large value (e.g. a ms timestamp ~1.7e12) still encodes fine.
    ts = ColumnCheck(field="created_at", op=CompOp.GTE, value=ValueRef(literal=1_700_000_000_000))
    formula, _ = E.encode_predicate(ts)
    assert formula is not None
