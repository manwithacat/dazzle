"""Scope-predicate algebra → SMT (Z3) encoder (RBAC proof substrate WP-1).

Promotes the de-risking spike into a production encoder over the existing
`dazzle.core.ir.predicates.ScopePredicate` union. It is the single intermediate
the meta-property prover (`prove.py`, WP-2) consumes.

WHAT THIS ENCODES — and the abstractions it makes — is specified normatively in
docs/reference/rbac-proof-model.md (WP0:TRUST-CHAIN). In short, every abstraction
points *toward* "could match", so the encoding is sound for the **safety /
no-escalation** direction (the security-critical one):

  - literals interned into a discrete, ordered integer domain (sound for = ≠ < >);
  - EXISTS junction sub-queries → uninterpreted booleans (junction contents not
    modelled — we never assume a matching row exists);
  - multi-hop FK paths → free symbols (join target unconstrained);
  - IN / NOT IN → uninterpreted membership booleans keyed by (column, value-set),
    with NOT IN the proper negation of IN (flagged in SymbolTable.abstractions).

z3 is an OPTIONAL dependency (`pip install dazzle-dsl[proof]`), imported lazily so
core installs are unaffected until a proof actually runs.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    ColumnRefCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    PathCheck,
    PolyPathCheck,
    Tautology,
    UserAttrCheck,
)

# z3 expressions are typed `Any` throughout: z3-solver ships no py.typed, so the
# solver handles are opaque to mypy (the [proof]-extra override relaxes
# warn_return_any at this boundary). The predicate IR we consume is fully typed.

# Discrete-domain layout (see module docstring). Numeric literals keep their real
# value for sound ordering; non-numeric values are interned into a high disjoint
# band so equality is exact and they never collide with plausible numeric values.
# The band is set far above any plausible RBAC literal (incl. ms timestamps ~1e12
# and currency-cents), and `intern` fail-closes (raises) on a numeric that could
# reach it — refusing to encode is sound; encoding an aliasing collision is not.
_NULL_SENTINEL = -999_999
_INTERN_BASE = 10**15

# Non-identifier separator for composite symbol keys (FK paths, EXISTS bindings,
# membership sets, poly-ref sub-namespaces). DSL identifiers cannot contain it, so
# distinct structures never collide on a shared key (review MAJOR-2).
_SEP = "\x1f"

CounterModel = dict[str, str]


class EncodingError(RuntimeError):
    """A predicate node has no SMT encoding (a WP-1 coverage gap)."""


def _z3() -> Any:
    """Lazy-import z3 with an actionable error if the [proof] extra is absent."""
    try:
        import z3
    except ImportError as exc:  # pragma: no cover — exercised only without the extra
        raise EncodingError(
            "The RBAC prover needs the z3 SMT solver. Install it with:\n"
            "    pip install 'dazzle-dsl[proof]'\n"
            "(or `uv sync --extra proof`). See docs/reference/rbac-proof-model.md."
        ) from exc
    return z3


class SymbolTable:
    """Symbolic environment shared across the predicates in one query.

    Columns, user attributes, interned literals and EXISTS markers all live here
    so predicates compared in one query (e.g. containment A ⊆ B) unify on the
    same Z3 constants — `row.x` must mean the *same* `x` on both sides.

    Interning is deterministic (insertion-ordered counter), so encoding is
    reproducible across runs.
    """

    def __init__(self) -> None:
        self._z = _z3()
        self._col: dict[str, Any] = {}
        self._usr: dict[str, Any] = {}
        self._bool: dict[str, Any] = {}
        self._intern: dict[tuple[str, object], int] = {}
        self._next = 0
        # Human-readable notes on which over-approximating abstractions fired.
        # The prover surfaces these as residual-risk context (WP0:TRUST-CHAIN).
        self.abstractions: list[str] = []

    def col(self, name: str) -> Any:
        if name not in self._col:
            self._col[name] = self._z.Int(f"row__{name}")
        return self._col[name]

    def usr(self, attr: str) -> Any:
        if attr not in self._usr:
            self._usr[attr] = self._z.Int(f"user__{attr}")
        return self._usr[attr]

    def marker(self, prefix: str, key: str, note: str) -> Any:
        """A reusable uninterpreted boolean keyed by (prefix, key).

        Same key → same symbol, so a proposition unifies across both sides of a
        containment query; distinct keys → independent symbols, so the solver may
        choose them freely (the over-approximation). Used for EXISTS junction
        sub-queries and IN/NOT-IN membership (their contents are not modelled).
        """
        full = f"{prefix}{_SEP}{key}"
        if full not in self._bool:
            self._bool[full] = self._z.Bool(f"{prefix}__{key}")
            self.abstractions.append(note)
        return self._bool[full]

    def intern(self, value: object) -> int:
        """Map a literal to a discrete int: injective for non-numerics, order-
        preserving for numerics (see module docstring)."""
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            iv = int(value)
            if abs(iv) >= _INTERN_BASE:
                # Fail-closed: a numeric this large could alias an interned
                # non-numeric and merge two distinct literals (review MINOR-1).
                raise EncodingError(
                    f"numeric literal {value!r} is outside the encoder's safe "
                    f"domain (±{_INTERN_BASE}); refusing to encode rather than "
                    "risk a literal-aliasing collision."
                )
            return iv
        key = (type(value).__name__, value)
        if key not in self._intern:
            self._intern[key] = _INTERN_BASE + self._next
            self._next += 1
        return self._intern[key]


_ORDER: dict[CompOp, Any] = {
    CompOp.EQ: lambda a, b: a == b,
    CompOp.NEQ: lambda a, b: a != b,
    CompOp.GT: lambda a, b: a > b,
    CompOp.LT: lambda a, b: a < b,
    CompOp.GTE: lambda a, b: a >= b,
    CompOp.LTE: lambda a, b: a <= b,
    CompOp.IS: lambda a, b: a == b,
    CompOp.IS_NOT: lambda a, b: a != b,
}


def _value(sym: SymbolTable, vref: Any) -> Any:
    """Resolve a ValueRef to a Z3 term."""
    z = _z3()
    if getattr(vref, "literal_null", False):
        return z.IntVal(_NULL_SENTINEL)
    if getattr(vref, "current_user", False):
        return sym.usr("id")
    if getattr(vref, "current_tenant", False):
        return sym.usr("__host_tenant__")
    if getattr(vref, "user_attr", None) is not None:
        return sym.usr(vref.user_attr)
    return z.IntVal(sym.intern(vref.literal))


def _vref_key(sym: SymbolTable, vref: Any) -> str:
    """A stable key for a ValueRef, so a membership set is identified by its value.

    Distinct comparison values → distinct keys → distinct membership symbols, so
    two different IN sets on the same column never alias (review MINOR-3).
    """
    if getattr(vref, "literal_null", False):
        return "null"
    if getattr(vref, "current_user", False):
        return "cu"
    if getattr(vref, "current_tenant", False):
        return "ct"
    if getattr(vref, "user_attr", None) is not None:
        return f"ua:{vref.user_attr}"
    return f"lit:{sym.intern(vref.literal)}"


def _membership(sym: SymbolTable, prefix: str, key: str, op: CompOp, note: str) -> Any:
    """Encode an IN / NOT IN membership as a keyed uninterpreted boolean.

    NOT IN is the negation of the *same* marker as the corresponding IN, so the
    two are proper logical opposites rather than independent free booleans
    (review MINOR-3). Sound for safety: membership truth is left free.
    """
    z = _z3()
    marker = sym.marker(prefix, key, note)
    return z.Not(marker) if op is CompOp.NOT_IN else marker


def encode(node: Any, sym: SymbolTable, col_prefix: str = "") -> Any:
    """ScopePredicate → Z3 boolean. Raises EncodingError on an unknown node.

    ``col_prefix`` namespaces row-column symbols. It is empty at the top level
    and set when descending into a poly-ref sub-predicate so the joined entity's
    columns never alias the outer row's columns (review MAJOR-1).
    """
    z = _z3()

    def col(name: str) -> Any:
        return sym.col(col_prefix + name)

    if isinstance(node, Tautology):
        return z.BoolVal(True)
    if isinstance(node, Contradiction):
        return z.BoolVal(False)
    if isinstance(node, ColumnCheck):
        op = _ORDER.get(node.op)
        if op is None:  # IN / NOT IN
            key = f"{col_prefix}{node.field}{_SEP}{_vref_key(sym, node.value)}"
            return _membership(
                sym, "in", key, node.op, f"{node.op.value} on {node.field} abstracted"
            )
        return op(col(node.field), _value(sym, node.value))
    if isinstance(node, UserAttrCheck):
        op = _ORDER.get(node.op)
        if op is None:
            key = f"{col_prefix}{node.field}{_SEP}ua:{node.user_attr}"
            return _membership(
                sym, "in", key, node.op, f"{node.op.value} on {node.field} abstracted"
            )
        return op(col(node.field), sym.usr(node.user_attr))
    if isinstance(node, ColumnRefCheck):
        op = _ORDER.get(node.op)
        if op is None:
            key = f"{col_prefix}{node.field}{_SEP}ref:{node.other_field}"
            return _membership(
                sym, "in", key, node.op, f"{node.op.value} on {node.field} abstracted"
            )
        return op(col(node.field), col(node.other_field))
    if isinstance(node, PathCheck):
        # Multi-hop FK target abstracted as a free symbol (over-approximation).
        # _SEP-joined so distinct paths never alias (review MAJOR-2).
        path_repr = _SEP.join(node.path)
        colname = f"path{_SEP}{path_repr}"
        sym.abstractions.append(f"FK path {'.'.join(node.path)} abstracted as free symbol")
        op = _ORDER.get(node.op)
        if op is None:
            key = f"{col_prefix}{colname}{_SEP}{_vref_key(sym, node.value)}"
            return _membership(sym, "in", key, node.op, f"{node.op.value} on FK path abstracted")
        return op(col(colname), _value(sym, node.value))
    if isinstance(node, ExistsCheck):
        # Junction sub-query: uninterpreted boolean (contents not modelled).
        binding_key = _SEP.join(f"{b.junction_field}{b.operator}{b.target}" for b in node.bindings)
        key = f"{node.target_entity}{_SEP}{binding_key}"
        marker = sym.marker(
            "exists", key, f"EXISTS via {node.target_entity} abstracted as free boolean"
        )
        return z.Not(marker) if node.negated else marker
    if isinstance(node, PolyPathCheck):
        # The branch tag is an OUTER column; the sub-predicate is rooted on the
        # JOINED entity, so it gets an isolated column namespace — its columns
        # must never alias the outer row's columns (review MAJOR-1).
        branch = col(node.type_field) == z.IntVal(sym.intern(node.type_value))
        sub_prefix = f"{col_prefix}poly{_SEP}{node.field}{_SEP}"
        return z.And(branch, encode(node.sub, sym, sub_prefix))
    if isinstance(node, BoolComposite):
        kids = [encode(c, sym, col_prefix) for c in node.children]
        if node.op is BoolOp.AND:
            return z.And(*kids)
        if node.op is BoolOp.OR:
            return z.Or(*kids)
        if node.op is BoolOp.NOT:
            return z.Not(kids[0])
    raise EncodingError(f"no SMT encoding for predicate node {type(node).__name__}")


def encode_predicate(node: Any) -> tuple[Any, SymbolTable]:
    """Encode a predicate against a fresh SymbolTable; return (formula, table)."""
    sym = SymbolTable()
    return encode(node, sym), sym


def is_satisfiable(node: Any) -> bool:
    """True if some (row, user) assignment satisfies the predicate.

    An UNSAT non-trivial scope is a dead rule / accidental deny worth flagging.
    """
    z = _z3()
    formula, _ = encode_predicate(node)
    solver = z.Solver()
    solver.add(formula)
    return bool(solver.check() == z.sat)


def _model_to_counter(model: Any) -> CounterModel:
    """Render a Z3 model as a stable, sorted name→value dict (the witness)."""
    return {d.name(): str(model[d]) for d in sorted(model.decls(), key=lambda d: d.name())}


def entails(hypothesis: Any, goal: Any) -> CounterModel | None:
    """Try to prove `hypothesis ⇒ goal`.

    Returns None when the implication is VALID (proved — UNSAT of
    `hypothesis ∧ ¬goal`). Otherwise returns a counter-model: a concrete witness
    assignment under which the hypothesis holds but the goal fails.

    `hypothesis` and `goal` MUST be Z3 formulas built by `encode(...)` against the
    SAME SymbolTable — otherwise their shared columns/users won't be the same Z3
    constants and the result is meaningless. The caller owns that invariant.
    """
    z = _z3()
    solver = z.Solver()
    solver.add(z.And(hypothesis, z.Not(goal)))
    if solver.check() == z.unsat:
        return None
    return _model_to_counter(solver.model())
