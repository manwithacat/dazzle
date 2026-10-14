"""Structural helpers over the scope-predicate algebra (RBAC proof substrate WP-1).

`dazzle.core.ir.predicates.ScopePredicate` is already a normalised, discriminated
IR (BoolComposite.make() canonicalises identity/absorption at construction). This
module does not re-invent that; it provides the *traversal and census* utilities
the SMT encoder (`encode_smt.py`) and the meta-property prover (`prove.py`) both
need — so neither re-implements tree walking and they agree on what a predicate
references.

See docs/reference/rbac-proof-model.md (WP0:FORMALISATION) for how this IR sits in
the effective-decision composition.
"""

from __future__ import annotations

from collections.abc import Iterator

from dazzle.core.ir.predicates import (
    BoolComposite,
    ExistsCheck,
    PathCheck,
    PolyPathCheck,
)

# Every concrete node kind the union can hold. Kept here as the single list the
# encoder's coverage test and the prover both assert against — if predicates.py
# grows a node, this and the encoder must grow with it (caught by the WP-1 gate).
ALL_NODE_KINDS: frozenset[str] = frozenset(
    {
        "column_check",
        "column_ref_check",
        "user_attr_check",
        "path_check",
        "exists_check",
        "poly_path",
        "bool_composite",
        "tautology",
        "contradiction",
    }
)


def iter_nodes(node: object) -> Iterator[object]:
    """Depth-first traversal yielding every node in a predicate tree (self first)."""
    yield node
    if isinstance(node, BoolComposite):
        for child in node.children:
            yield from iter_nodes(child)
    elif isinstance(node, PolyPathCheck):
        yield from iter_nodes(node.sub)


def has_data_dependent_node(node: object) -> bool:
    """True if the predicate's truth depends on data the static model abstracts.

    EXISTS junction sub-queries and multi-hop FK paths are encoded as free
    symbols (see encode_smt + WP0:TRUST-CHAIN). A proof that relies on such a
    node is sound only in the over-approximation direction; the prover surfaces
    this so the report can attach the right residual-risk note.
    """
    return any(isinstance(n, (ExistsCheck, PathCheck)) for n in iter_nodes(node))
