<!-- WP0:PROOF-MODEL — proof-obligation model & trust boundary for "provable RBAC".
     This file is the single source of truth for every external access-control
     claim. The claim ledger (src/dazzle/rbac/claim_ledger.py, WP-7) and the
     structural gate (tests/unit/test_rbac_proof_model.py) both key off the
     anchors and the evidence-class table below. Edit deliberately. -->

# RBAC Proof Model & Trust Boundary

**Status:** normative. Every external claim about DAZZLE access control must map
to a clause here. A marketing string with no discharging obligation in this
document is wrong — fix the string, not the model. The word *provable* is
permitted in external copy only as licensed by the **Evidence classes** table
below (enforced by `dazzle rbac report --lint`, WP-7).

This document states a **scoped** theorem, mechanically checked, with the trusted
computing base named explicitly. It never presents a scoped result as
unconditional (see **Non-goals**).

<!-- WP0:FORMALISATION -->
## 1. Formalisation — the effective decision

The runtime allow/deny for a principal `p`, resource `r`, action `a` in system
state `σ` is the composition (single source of truth for the IR):

```
allow(p, r, a, σ)  ⇔  tenant_RLS(p, r)
                    ∧ role_perm(role(p), r, a)
                    ∧ ( scope_pred(p, r) ∨ rebac_grant(p, r, a, σ) )
```

- **Static core** = `tenant_RLS ∧ role_perm ∧ scope_pred` — finite, enumerable,
  matrix-shaped. This is the part the DSL fully determines. It is the target of
  the proof obligations below.
- **ReBAC overlay** = `rebac_grant(…, σ)` — instance-level, data-dependent on
  live relationship tuples. Target of the over-approximation argument (§4).

The scope compiler already lowers `scope:`/`permit:`/`as:` rules to a formal
predicate algebra over the FK graph (`dazzle.core.ir.predicates.ScopePredicate`).
The SMT encoder (`dazzle.rbac.encode_smt`, WP-1) consumes that algebra directly;
it is the single intermediate both the matrix generator and the prover share.

<!-- WP0:THEOREM -->
## 2. Target theorem (the genuine statement of proof)

Let `σ` be a system state (live relationship tuples + role assignments), `M` the
static access matrix, `Ĝ` the abstract grant relation (relationship-class level),
`Decide` the declared policy semantics, and `Enforce` the actual runtime
allow/deny produced by RLS + middleware. Under **assumption set A** (§3):

- **No-escalation (safety — security-critical):**
  `∀ p,r,a,σ.  Enforce(σ,p,r,a) = allow  ⇒  Decide(M, Ĝ, p,r,a) = allow`
  The runtime never grants what policy denies.
- **No-false-deny (availability):**
  `∀ p,r,a,σ.  Decide(M, Ĝ, p,r,a) = allow  ⇒  Enforce(σ,p,r,a) = allow`
  Declared access is realised.
- **ReBAC over-approximation soundness:**
  `∀ σ.  ConcreteAllow(σ) ⊆ Decide(M, Ĝ)`
  The static matrix is a safe upper bound — anything the matrix denies is
  genuinely denied at runtime. This is the property that licenses an auditor to
  read the matrix as *"who could access"*.

<!-- WP0:ASSUMPTIONS -->
## 3. Assumption set A (the trust boundary — stated, not hidden)

The theorem holds **modulo** these assumptions. They are declared here and
surfaced in `dazzle rbac report`, never buried.

- **A.1 — Authentication is correct.** Principal identity is trusted; authn is
  out of scope.
- **A.2 — Single governed query path.** Every governed access uses the connection
  factory; there is exactly one governed query path. (Statically defended by the
  mediation pass, WP-4 — *test/assurance class*, not proof.)
- **A.3 — No bypass role on request paths.** The application DB role does not hold
  `BYPASSRLS`; no superuser connection serves request paths.
- **A.4 — Trusted computing base.** PostgreSQL's RLS engine, psycopg3, the
  connection pooler, and the OS are trusted. The proof is *modulo* their
  correctness.

<!-- WP0:TRUST-CHAIN -->
## 4. The trust chain — what is proof, what is test, what is assumed

The prover discharges theorems about a **model** of the policy, not about the SQL
PostgreSQL executes. Stating this plainly is what makes the claim defensible
rather than over-claimed. The chain has three links; only the first is proof:

```
   (1) SMT proof about the IR
        │   PROOF    — discharged by Z3; UNSAT core / counter-model emitted
        ▼
   (2) IR faithfully models the emitted RLS/SQL
        │   TEST     — conformance enumeration vs observed RLS (WP-3). NOT proof.
        ▼
   (3) PostgreSQL executes that SQL correctly
            ASSUMED  — TCB, assumption A.4. Declared, not proven.
```

Two of three links are not proof. **Link 2 is load-bearing and must be closed by
test, not by self-consistency:** the WP-1 round-trip compares `Decide(IR)` against
the existing matrix generator, but both share the same abstraction, so that check
cannot catch a model-vs-SQL divergence. The faithful oracle is WP-3, which
compares `Decide(IR)` against **observed RLS behaviour on real PostgreSQL**, with
a stated residual-risk figure.

### Abstractions the SMT encoding makes
All abstract *toward* "could match" (sound for the **safety / no-escalation**
direction; not for no-false-deny without refinement — §6 records which theorem
each supports):

- **Literals** interned to a discrete ordered integer domain — sound for
  `= ≠ < > ≤ ≥`.
- **`EXISTS` junction sub-queries** → uninterpreted booleans (table contents not
  modelled). We never assume a junction row exists.
- **Multi-hop FK paths** → free symbols (join target unconstrained).
- **`IN` / `NOT IN`** → free booleans (rare in scope rules; flagged by the
  encoder for exact handling).

<!-- WP0:EVIDENCE-CLASSES -->
## 5. Evidence classes (the discharge contract)

The noun *provable* is permitted in external copy for a property **iff** that
property carries a named evidence class below. Three classes exist:

- **Proof** — discharged by a solver (SMT/Datalog); certificate or UNSAT core
  emitted on success, counter-model on failure.
- **Enumeration** — a finite domain provably traversed in full; cardinality
  mechanically checked (not asserted).
- **Test** — property-based or red-team, with stated coverage and a residual-risk
  note.

Copy that claims "proof" for a property whose class here is "test" fails CI
(`dazzle rbac report --lint`, WP-7).

| Property | Evidence class | Owning WP | Status |
|---|---|---|---|
| Matrix is a deterministic function of the DSL | Enumeration | WP-1 | live |
| Scope predicates type-check & resolve on the FK graph | Enumeration | WP-1 | live (`dazzle validate`) |
| Predicate algebra → solver encoding is total (every node) | Enumeration | WP-1 | this build |
| Role-hierarchy acyclicity | Proof | WP-2 | this build |
| Deny-overrides (FORBID > PERMIT > DENY) precedence soundness | Proof | WP-2 | this build |
| Least-privilege containment / reachability / leak queries | Proof | WP-2 | this build |
| Separation-of-duty (per declared SoD constraints) | Proof | WP-2 | this build |
| Refinement: runtime Enforce conforms to the matrix | Enumeration + Test | WP-3 | planned |
| Default-deny for off-matrix tuples | Enumeration | WP-3 | planned |
| Complete mediation (single governed query path; no BYPASSRLS) | Test | WP-4 | planned (human-gated) |
| Adversarial bypass resistance (per attack class) | Test | WP-5 | planned (human-gated) |
| ReBAC over-approximation soundness (declared grant classes) | Proof | WP-6 | planned (see §7) |

<!-- WP0:REBAC -->
## 6. ReBAC stance (scope of the over-approximation claim)

The over-approximation theorem (§2) is provable **only over DSL-declared grant
classes** (`grant_schema`). That is the supported, analysed surface:

- **In scope (Proof class):** grants that instantiate a relationship-class
  declared in the DSL. The matrix is a provable upper bound over these — the
  "who could access" reading holds.
- **Out of scope (explicit residual, not a silent caveat):** grants minted by
  arbitrary builder application code outside the declared classes remain
  *supported at runtime* but are **not** covered by the proof. The report labels
  any app that mints such grants with a residual-risk note; the claim for that app
  degrades from "proven upper bound" to "upper bound over declared classes".

This keeps WP-6 in the Proof class for the common, declarative case while leaving
the door open for builder-defined grants — at a stated, bounded loss of proof
coverage rather than an unstated one.

<!-- WP0:NON-GOALS -->
## 7. Non-goals (prevent over-claim)

- Timing / covert-channel resistance.
- Correctness of the TCB (PostgreSQL / psycopg3 / pooler) — assumed (A.4), not
  proven.
- A closed, assumption-free proof. The claim is *scoped*; the scope **is**
  assumption set A. A scoped result is never presented as unconditional.
- Proof over builder-minted grants outside declared classes (§6).

## 8. How each downstream artefact references this model

- `dazzle.rbac.encode_smt` (WP-1) — implements the §1 composition's `scope_pred`
  encoding under the §4 abstractions.
- `dazzle rbac prove` (WP-2) — discharges every **Proof**-class row in §5,
  emitting a certificate/UNSAT core on success and a counter-model on failure.
- `dazzle rbac verify --exhaustive` (WP-3) — closes trust-chain link 2 (§4).
- `src/dazzle/rbac/claim_ledger.py` + `dazzle rbac report --lint` (WP-7) — maps
  each external claim string to its row in §5 and fails the build on any claim
  exceeding its discharged evidence class.
