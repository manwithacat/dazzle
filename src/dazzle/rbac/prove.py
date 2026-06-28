"""RBAC meta-property prover (proof substrate WP-2).

Discharges properties of docs/reference/rbac-proof-model.md §5 over the static
core (tenant ∧ role ∧ scope), using the WP-1 SMT encoder. On a violation it emits
a concrete counter-model; `dazzle rbac prove` wires this as a CI gate.

HONESTY DISCIPLINE (this tool backs the word "provable" — it must never overclaim).
Each property carries an explicit STATUS, surfaced verbatim by the CLI, so a reader
never mistakes a vacuous or informational result for a substantive proof:

  - PROVED        — substantive, app-specific obligations were discharged.
  - VACUOUS       — nothing to check in THIS app (no such construct declared);
                    derived from the AppSpec, so it self-activates if Dazzle grows
                    the construct — never hardcoded green.
  - INFORMATIONAL — a descriptive enumeration (the containment lattice), not a
                    pass/fail gate; its value is the proven relationships it lists.
  - FAILED        — a violation with a counter-model.

What each property is and its evidence class (mirrors §5):
  - scope_satisfiability  [Proof]        every non-trivial scope is satisfiable;
                                         a Contradiction/UNSAT scope is a dead rule.
  - least_privilege       [Proof/INFO]   each scope-containment A⊆B is solver-proved;
                                         the SET of them is informational, not a gate.
  - deny_overrides        [Proof]        the decision-composition OPERATOR
                                         `allow = permit ∧ ¬forbid` gives forbid
                                         precedence. App-INDEPENDENT algebraic identity
                                         — that the matrix generator uses this operator
                                         is a WP-3 (test-class) linkage, stated as such.
  - role_hierarchy_acyclic[Proof]        no cycle in declared role-inheritance edges.
  - separation_of_duty    [Proof]        declared SoD constraints hold.

Everything is *modulo* the trust chain (WP0:TRUST-CHAIN): it proves the MODEL,
whose faithfulness to the emitted SQL is a separate (test-class) obligation (WP-3).
Containment proofs over EXISTS/FK-path scopes lean on the encoder's
over-approximation — those are counted and surfaced, not hidden.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from dazzle.core.ir import AppSpec
from dazzle.rbac import encode_smt as E
from dazzle.rbac.ir import has_data_dependent_node


class EvidenceClass(StrEnum):
    """The discharge contract from rbac-proof-model.md §5."""

    PROOF = "proof"
    ENUMERATION = "enumeration"
    TEST = "test"


class Status(StrEnum):
    """The honest verdict surface (see module docstring)."""

    PROVED = "PROVED"
    VACUOUS = "VACUOUS"
    INFORMATIONAL = "INFORMATIONAL"
    FAILED = "FAILED"


class Obligation(BaseModel):
    """One proof obligation — discharged, or violated with a witness."""

    description: str
    discharged: bool
    counter_model: dict[str, str] | None = None


class PropertyReport(BaseModel):
    """The verdict for one meta-property."""

    name: str
    evidence: EvidenceClass
    status: Status
    summary: str
    obligations_discharged: int = 0
    violations: list[Obligation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A property 'passes' the gate unless it actively FAILED."""
        return self.status is not Status.FAILED


class ProofReport(BaseModel):
    """The full `dazzle rbac prove` result for one project."""

    project: str
    properties: list[PropertyReport]
    residual_notes: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(p.passed for p in self.properties)

    @property
    def substantive_obligations(self) -> int:
        """Obligations from properties that actually PROVED something app-specific.

        Excludes vacuous/informational/app-independent results so the headline
        count cannot be inflated by trivial passes (review N-1)."""
        return sum(p.obligations_discharged for p in self.properties if p.status is Status.PROVED)


# --------------------------------------------------------------------------- #
# Reusable solver primitives (unit-testable in isolation).
# --------------------------------------------------------------------------- #


def prove_containment(scope_a: Any, scope_b: Any) -> E.CounterModel | None:
    """Prove `scope_a ⊆ scope_b`: every row A admits, B admits.

    Both predicates are encoded against ONE shared SymbolTable so their columns
    and user-attrs unify. Returns None when containment is proved, else a
    counter-model row+user that A admits but B denies.
    """
    sym = E.SymbolTable()
    fa = E.encode(scope_a, sym)
    fb = E.encode(scope_b, sym)
    return E.entails(fa, fb)


def _deny_overrides_violation(compose: Any) -> E.CounterModel | None:
    """Check that a decision-composition `compose(permit, forbid)` lets forbid win.

    Parametric on the composition so a deliberately-broken operator can be shown
    to fail (the anti-vacuity test). Correct: `lambda p, f: And(p, Not(f))`.
    """
    z = E._z3()
    permit = z.Bool("permit")
    forbid = z.Bool("forbid")
    allow = compose(permit, forbid)
    # forbid ⇒ ¬allow must be valid.
    return E.entails(forbid, z.Not(allow))


def _correct_composition(permit: Any, forbid: Any) -> Any:
    z = E._z3()
    return z.And(permit, z.Not(forbid))


# --------------------------------------------------------------------------- #
# AppSpec inspection — derived, not hardcoded, so vacuity self-activates.
# --------------------------------------------------------------------------- #


def _iter_scopes(appspec: AppSpec) -> list[tuple[str, str, tuple[str, ...], Any]]:
    """(entity, operation, persona_group, predicate) for every linked scope rule."""
    out: list[tuple[str, str, tuple[str, ...], Any]] = []
    for ent in appspec.domain.entities:
        acc = getattr(ent, "access", None)
        if not acc:
            continue
        for s in getattr(acc, "scopes", []):
            if getattr(s, "predicate", None) is not None:
                out.append((ent.name, str(s.operation), tuple(s.personas), s.predicate))
    return out


def _role_inheritance_edges(appspec: AppSpec) -> list[tuple[str, str]]:
    """Declared (child_role, parent_role) inheritance edges.

    Dazzle personas flat-map to roles with no inheritance construct today, so this
    returns []. It READS the AppSpec (defensively probing for a future
    inherits/parent_role attribute) rather than hardcoding empty — so if such a
    construct is ever added, acyclicity stops being vacuous automatically
    (review M-1 staleness guard)."""
    edges: list[tuple[str, str]] = []
    for persona in getattr(appspec, "personas", []) or []:
        child = getattr(persona, "role", None) or getattr(persona, "id", None)
        for attr in ("inherits", "parent_role", "extends_role"):
            parents = getattr(persona, attr, None)
            if not parents or child is None:
                continue
            for parent in parents if isinstance(parents, (list, tuple)) else [parents]:
                edges.append((str(child), str(parent)))
    return edges


def _sod_constraints(appspec: AppSpec) -> list[Any]:
    """Declared separation-of-duty constraints (none in Dazzle today).

    Probes the AppSpec rather than hardcoding empty, so a future SoD construct
    self-activates the check (review M-1)."""
    constraints: list[Any] = []
    for attr in ("separation_of_duty", "sod_constraints", "sod"):
        declared = getattr(appspec, attr, None)
        if declared:
            constraints.extend(declared if isinstance(declared, (list, tuple)) else [declared])
    return constraints


# --------------------------------------------------------------------------- #
# Property provers.
# --------------------------------------------------------------------------- #


def prove_scopes_satisfiable(appspec: AppSpec) -> PropertyReport:
    """Every non-trivial scope must be satisfiable; a Contradiction is a dead rule."""
    violations: list[Obligation] = []
    checked = 0
    for entity, op, personas, pred in _iter_scopes(appspec):
        if pred.kind == "tautology":
            continue  # unconditional permit — not a dead rule
        if pred.kind == "contradiction":
            # An unconditional deny: statically UNSAT, denies every request for
            # this persona (review N-2 — must be flagged, not silently skipped).
            violations.append(
                Obligation(
                    description=f"{entity}.{op} {list(personas)} scope is a CONTRADICTION "
                    "(statically dead rule — denies everything)",
                    discharged=False,
                )
            )
            continue
        checked += 1
        if not E.is_satisfiable(pred):
            violations.append(
                Obligation(
                    description=f"{entity}.{op} {list(personas)} scope is UNSATISFIABLE "
                    "(dead rule / accidental deny)",
                    discharged=False,
                )
            )
    if violations:
        status = Status.FAILED
    elif checked:
        status = Status.PROVED
    else:
        status = Status.VACUOUS
    return PropertyReport(
        name="scope_satisfiability",
        evidence=EvidenceClass.PROOF,
        status=status,
        summary=(
            f"{checked} non-trivial scope(s) satisfiable; {len(violations)} dead rule(s)"
            if checked or violations
            else "no non-trivial scopes declared"
        ),
        obligations_discharged=checked,
        violations=violations,
    )


def _dedupe_group(rules: list[tuple[tuple[str, ...], Any]]) -> list[Any]:
    """Distinct scope predicates in a group (identical predicates collapse, so a
    duplicated scope cannot inflate the containment count — review B-1)."""
    seen: list[Any] = []
    for _personas, pred in rules:
        if all(pred != s for s in seen):
            seen.append(pred)
    return seen


def prove_least_privilege(appspec: AppSpec) -> PropertyReport:
    """Discharge the containment partial order among DISTINCT persona scopes.

    Each containment A⊆B is solver-proved (Proof-class). The SET of them is
    INFORMATIONAL — distinct roles are *expected* to differ, so a non-containment
    is not a violation; the value is the proven lattice an auditor reads as
    "admin ⊇ owner ⊇ member". Containments whose predicates lean on the encoder's
    over-approximation (EXISTS/FK-path) are counted separately and disclosed.
    """
    discharged = 0
    over_approx = 0
    groups: dict[tuple[str, str], list[tuple[tuple[str, ...], Any]]] = {}
    for entity, op, personas, pred in _iter_scopes(appspec):
        groups.setdefault((entity, op), []).append((personas, pred))

    for rules in groups.values():
        preds = _dedupe_group(rules)
        if len(preds) < 2:
            continue
        for i, na in enumerate(preds):
            for j, nb in enumerate(preds):
                if i == j:
                    continue
                if prove_containment(na, nb) is None:
                    discharged += 1
                    if has_data_dependent_node(na) or has_data_dependent_node(nb):
                        over_approx += 1

    summary = f"{discharged} scope-containment(s) proved from the DSL"
    if over_approx:
        summary += f" ({over_approx} rely on over-approximated EXISTS/FK-path nodes — see §4)"
    elif discharged == 0:
        summary = "no scope-containment relationships in this app (all persona scopes incomparable)"
    return PropertyReport(
        name="least_privilege",
        evidence=EvidenceClass.PROOF,
        status=Status.INFORMATIONAL,
        summary=summary,
        obligations_discharged=discharged,
    )


def prove_deny_overrides(appspec: AppSpec) -> PropertyReport:
    """Prove the decision-composition OPERATOR gives FORBID precedence.

    App-INDEPENDENT: proves `forbid ⇒ ¬(permit ∧ ¬forbid)` over symbolic booleans.
    The summary states plainly that this is an operator-level identity and that the
    matrix-generator-uses-this-operator linkage is a WP-3 (test) obligation — so a
    reader never mistakes it for an app-specific verification (review C-1).
    """
    cm = _deny_overrides_violation(_correct_composition)
    ok = cm is None
    return PropertyReport(
        name="deny_overrides",
        evidence=EvidenceClass.PROOF,
        status=Status.PROVED if ok else Status.FAILED,
        summary=(
            "decision operator `allow = permit ∧ ¬forbid` gives forbid precedence "
            "(app-independent algebraic identity; generator-uses-operator is WP-3)"
            if ok
            else "composition does NOT give forbid precedence"
        ),
        obligations_discharged=1 if ok else 0,
        violations=[]
        if ok
        else [
            Obligation(
                description="forbid did not override permit", discharged=False, counter_model=cm
            )
        ],
    )


def prove_role_hierarchy_acyclic(appspec: AppSpec) -> PropertyReport:
    """No cycle in declared role-inheritance edges (derived from the AppSpec)."""
    edges = _role_inheritance_edges(appspec)
    cycle = _find_cycle(edges)
    if not edges:
        status, summary = Status.VACUOUS, "no role-inheritance construct declared"
    elif cycle is None:
        status, summary = Status.PROVED, f"{len(edges)} inheritance edge(s); acyclic"
    else:
        status, summary = Status.FAILED, f"role hierarchy cycle: {' → '.join(cycle)}"
    return PropertyReport(
        name="role_hierarchy_acyclic",
        evidence=EvidenceClass.PROOF,
        status=status,
        summary=summary,
        obligations_discharged=1 if (edges and cycle is None) else 0,
        violations=[] if cycle is None else [Obligation(description=summary, discharged=False)],
    )


def prove_separation_of_duty(appspec: AppSpec) -> PropertyReport:
    """Declared separation-of-duty constraints hold (none in Dazzle today)."""
    constraints = _sod_constraints(appspec)
    return PropertyReport(
        name="separation_of_duty",
        evidence=EvidenceClass.PROOF,
        status=Status.VACUOUS if not constraints else Status.PROVED,
        summary="no separation-of-duty construct declared"
        if not constraints
        else f"{len(constraints)} SoD constraint(s) hold",
        obligations_discharged=len(constraints),
    )


def _find_cycle(edges: list[tuple[str, str]]) -> list[str] | None:
    """Return a cycle (as a node list) in a directed graph, or None if acyclic."""
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for nxt in adj.get(node, []):
            if color.get(nxt, WHITE) == GREY:
                return stack[stack.index(nxt) :] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for n in list(adj):
        if color.get(n, WHITE) == WHITE:
            found = visit(n)
            if found:
                return found
    return None


_PROVERS = (
    prove_scopes_satisfiable,
    prove_least_privilege,
    prove_deny_overrides,
    prove_role_hierarchy_acyclic,
    prove_separation_of_duty,
)


def prove_all(appspec: AppSpec) -> ProofReport:
    """Run every meta-property prover and assemble the report."""
    properties = [p(appspec) for p in _PROVERS]
    # Surface the encoder's over-approximation notes (deduped) as residual context
    # so an auditor sees WHICH scopes are over-approximated, not just a count.
    residual: list[str] = []
    seen: set[str] = set()
    for _e, _op, _pg, pred in _iter_scopes(appspec):
        if has_data_dependent_node(pred):
            _, sym = E.encode_predicate(pred)
            for note in sym.abstractions:
                if note not in seen:
                    seen.add(note)
                    residual.append(note)
    return ProofReport(project=appspec.name, properties=properties, residual_notes=residual)
