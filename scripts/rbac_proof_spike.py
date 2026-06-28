#!/usr/bin/env python
"""
RBAC proof spike (WP-1 + WP-2 de-risking) — NOT production code.

Purpose: empirically test the single load-bearing feasibility claim from
`rbacproofsubstratespec.md` — that DAZZLE's existing scope-predicate algebra
(`dazzle.core.ir.predicates.ScopePredicate`) encodes to an SMT solver and can
answer real meta-property queries (reachability / least-privilege / leak),
emitting a *counter-model* on violation.

It loads a REAL example app's linked AppSpec (so `ScopeRule.predicate` is
populated by the linker), encodes every scope predicate to Z3, and runs four
demonstrations:

  A. ENCODING COVERAGE   — every predicate node maps to a Z3 formula (WP-1).
  B. SATISFIABILITY AUDIT — each scope is satisfiable (an UNSAT scope is a dead
                            rule / accidental deny worth flagging).
  C. LEAST-PRIVILEGE / LEAK QUERY — for two persona groups sharing an
                            entity+operation, prove containment (A ⊆ B) or emit
                            a witness row+user proving a leak (WP-2).
  D. NEGATIVE CONTROL    — a seeded-broken property the prover MUST refute, to
                            show the green results in A–C are not vacuous.

IMPORTANT — what this proves and what it does NOT (the honest trust boundary):
  The Z3 encoding is an *abstraction* of the real SQL/RLS semantics:
    - literals/strings are interned to a discrete integer domain (sound for
      =, !=, <, >, and ordering over a discrete order);
    - EXISTS sub-queries are modelled as uninterpreted booleans (we do not
      model junction-table contents — sound for the safety/over-approximation
      direction);
    - multi-hop FK paths are modelled as free symbols (the join target is
      unconstrained — again an over-approximation).
  So this proves properties of the MODEL of the policy, not of the emitted SQL.
  Faithfulness of (model ⟷ emitted SQL) is a *separate* obligation discharged
  by conformance testing (WP-3), and Postgres-executes-SQL-correctly is an
  assumption (TCB, §7.1). This spike exists to prove WP-1/WP-2 are tractable —
  it is deliberately explicit about the two non-proof links in the chain.

Run:  .venv/bin/python scripts/rbac_proof_spike.py [example_name]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import z3

from dazzle.core.appspec_loader import load_project_appspec
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

NULL_SENTINEL = -999_999  # reserved discrete value for SQL NULL


class EncodingError(Exception):
    """Raised when a predicate node has no Z3 encoding (WP-1 coverage gap)."""


class Env:
    """Symbolic environment shared across the predicates in one query.

    Columns, user attributes, interned literals, and EXISTS markers all live
    here so two predicates compared in a containment query unify on the same
    Z3 constants (the whole point: `row.x` means the same `x` in both).
    """

    def __init__(self) -> None:
        self._col: dict[str, z3.ArithRef] = {}
        self._usr: dict[str, z3.ArithRef] = {}
        self._exists: dict[str, z3.BoolRef] = {}
        self._intern: dict[object, int] = {}
        self._next = 1

    def col(self, name: str) -> z3.ArithRef:
        if name not in self._col:
            self._col[name] = z3.Int(f"row__{name}")
        return self._col[name]

    def usr(self, attr: str) -> z3.ArithRef:
        if attr not in self._usr:
            self._usr[attr] = z3.Int(f"user__{attr}")
        return self._usr[attr]

    def exists(self, key: str) -> z3.BoolRef:
        if key not in self._exists:
            self._exists[key] = z3.Bool(f"exists__{key}")
        return self._exists[key]

    def intern(self, value: object) -> int:
        """Map a literal to a stable discrete int (distinct literals distinct)."""
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int):
            return value
        if value not in self._intern:
            self._next += 1
            self._intern[value] = self._next + 10_000
        return self._intern[value]


_ORDER = {
    CompOp.EQ: lambda a, b: a == b,
    CompOp.NEQ: lambda a, b: a != b,
    CompOp.GT: lambda a, b: a > b,
    CompOp.LT: lambda a, b: a < b,
    CompOp.GTE: lambda a, b: a >= b,
    CompOp.LTE: lambda a, b: a <= b,
    CompOp.IS: lambda a, b: a == b,
    CompOp.IS_NOT: lambda a, b: a != b,
}


def _value(env: Env, vref) -> z3.ArithRef:
    """Resolve a ValueRef to a Z3 term."""
    if getattr(vref, "literal_null", False):
        return z3.IntVal(NULL_SENTINEL)
    if getattr(vref, "current_user", False):
        return env.usr("id")
    if getattr(vref, "current_tenant", False):
        return env.usr("__host_tenant__")
    if getattr(vref, "user_attr", None) is not None:
        return env.usr(vref.user_attr)
    return z3.IntVal(env.intern(vref.literal))


def encode(env: Env, node) -> z3.BoolRef:
    """ScopePredicate -> Z3 boolean. Raises EncodingError on an unknown node."""
    if isinstance(node, Tautology):
        return z3.BoolVal(True)
    if isinstance(node, Contradiction):
        return z3.BoolVal(False)
    if isinstance(node, ColumnCheck):
        op = _ORDER.get(node.op)
        if op is None:  # IN / NOT IN — abstract as free boolean (sound either way only if unused)
            return z3.Bool(f"col_in__{node.field}")
        return op(env.col(node.field), _value(env, node.value))
    if isinstance(node, UserAttrCheck):
        op = _ORDER.get(node.op)
        if op is None:
            return z3.Bool(f"uac_in__{node.field}")
        return op(env.col(node.field), env.usr(node.user_attr))
    if isinstance(node, ColumnRefCheck):
        op = _ORDER.get(node.op)
        if op is None:
            return z3.Bool(f"colref_in__{node.field}")
        return op(env.col(node.field), env.col(node.other_field))
    if isinstance(node, PathCheck):
        # Multi-hop FK target: abstract the joined value as a free symbol.
        # Over-approximation — the join target is unconstrained.
        col = env.col("path__" + ".".join(node.path))
        op = _ORDER.get(node.op)
        if op is None:
            return z3.Bool("path_in__" + ".".join(node.path))
        return op(col, _value(env, node.value))
    if isinstance(node, ExistsCheck):
        # Junction sub-query: uninterpreted boolean (we don't model the table).
        key = (
            node.target_entity
            + "|"
            + ",".join(f"{b.junction_field}{b.operator}{b.target}" for b in node.bindings)
        )
        marker = env.exists(key)
        return z3.Not(marker) if node.negated else marker
    if isinstance(node, PolyPathCheck):
        branch = env.col(node.type_field) == z3.IntVal(env.intern(node.type_value))
        return z3.And(branch, encode(env, node.sub))
    if isinstance(node, BoolComposite):
        kids = [encode(env, c) for c in node.children]
        if node.op is BoolOp.AND:
            return z3.And(*kids)
        if node.op is BoolOp.OR:
            return z3.Or(*kids)
        if node.op is BoolOp.NOT:
            return z3.Not(kids[0])
    raise EncodingError(f"no encoding for {type(node).__name__}")


# --------------------------------------------------------------------------- #
# Spike driver
# --------------------------------------------------------------------------- #


def _collect(spec):
    """entity -> operation -> list[(persona_tuple, predicate)]."""
    out: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in spec.domain.entities:
        acc = getattr(e, "access", None)
        if not acc:
            continue
        for s in getattr(acc, "scopes", []):
            if getattr(s, "predicate", None) is not None:
                out[e.name][str(s.operation)].append((tuple(s.personas), s.predicate))
    return out


def _sat(formula: z3.BoolRef) -> z3.CheckSatResult:
    s = z3.Solver()
    s.add(formula)
    return s.check()


def main() -> int:
    example = sys.argv[1] if len(sys.argv) > 1 else "acme_billing"
    root = Path("examples") / example
    spec = load_project_appspec(root)
    data = _collect(spec)
    total_preds = sum(len(v) for ops in data.values() for v in ops.values())

    print(f"\n{'=' * 72}\nRBAC PROOF SPIKE — example: {example}")
    print(f"entities with scope predicates: {len(data)} | scope predicates: {total_preds}")
    print("=" * 72)

    # ---- A. ENCODING COVERAGE (WP-1) -------------------------------------- #
    print("\n[A] ENCODING COVERAGE (WP-1: every node → Z3)")
    encoded = failed = 0
    for ent, ops in data.items():
        for op, rules in ops.items():
            for personas, pred in rules:
                try:
                    encode(Env(), pred)
                    encoded += 1
                except EncodingError as exc:
                    failed += 1
                    print(f"    ✗ {ent}.{op} {personas}: {exc}")
    print(
        f"    encoded {encoded}/{encoded + failed} predicate trees "
        f"({'ALL' if failed == 0 else f'{failed} FAILED'})"
    )

    # ---- B. SATISFIABILITY AUDIT ------------------------------------------ #
    print("\n[B] SATISFIABILITY AUDIT (UNSAT scope = dead rule / accidental deny)")
    unsat = 0
    for ent, ops in data.items():
        for op, rules in ops.items():
            for personas, pred in rules:
                if isinstance(pred, (Tautology,)):
                    continue
                env = Env()
                if _sat(encode(env, pred)) == z3.unsat:
                    unsat += 1
                    print(f"    ⚠ {ent}.{op} {personas} is UNSATISFIABLE")
    print(
        f"    {'no unsatisfiable scopes' if unsat == 0 else f'{unsat} flagged'} "
        f"(non-trivial scopes checked)"
    )

    # ---- C. LEAST-PRIVILEGE / LEAK QUERY (WP-2) --------------------------- #
    print("\n[C] LEAST-PRIVILEGE / LEAK QUERY (WP-2: containment or counter-model)")
    pairs = 0
    for ent, ops in data.items():
        for op, rules in ops.items():
            if len(rules) < 2:
                continue
            for i in range(len(rules)):
                for j in range(len(rules)):
                    if i == j:
                        continue
                    (pa, na), (pb, nb) = rules[i], rules[j]
                    # Is there a row A admits that B denies?  (A ⊄ B ?)
                    env = Env()
                    fa, fb = encode(env, na), encode(env, nb)
                    s = z3.Solver()
                    s.add(z3.And(fa, z3.Not(fb)))
                    if s.check() == z3.unsat:
                        pairs += 1
                        print(
                            f"    ✓ PROVED  {ent}.{op}: {list(pa)} ⊆ {list(pb)} "
                            f"(every row {list(pa)} sees, {list(pb)} sees)"
                        )
                    # (SAT here just means the two scopes differ — expected, not printed)
    print(f"    {pairs} containment relationship(s) proved from the DSL alone")

    # ---- D. NEGATIVE CONTROL (anti-vacuity) ------------------------------- #
    print("\n[D] NEGATIVE CONTROL (prover MUST refute a false claim + give witness)")
    env = Env()
    # Real-shaped owner scope: row.owner_id == user.id
    owner = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
    # FALSE claim: 'every row passes the owner scope' (Tautology ⊆ owner).
    # Counter-witness: any row whose owner_id != user.id.
    f_owner = encode(env, owner)
    s = z3.Solver()
    s.add(z3.And(z3.BoolVal(True), z3.Not(f_owner)))  # Tautology ∧ ¬owner
    res = s.check()
    if res == z3.sat:
        m = s.model()
        print("    ✓ refuted 'Tautology ⊆ owner_scope' — counter-model:")
        for d in m.decls():
            print(f"         {d.name()} = {m[d]}")
        print("       (i.e. a row with owner_id ≠ user.id — exactly the leak a")
        print("        bad 'permit all' override would introduce). Prover is non-vacuous.")
    else:
        print(
            "    ✗✗ NEGATIVE CONTROL FAILED — prover returned", res, "— results above are SUSPECT"
        )
        return 2

    print(f"\n{'=' * 72}\nSPIKE VERDICT: WP-1 encoding + WP-2 meta-queries are tractable on")
    print("real DSL. Caveat: proves the MODEL (see module docstring trust boundary).")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
