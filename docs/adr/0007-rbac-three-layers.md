# ADR-0007: Three-Layer RBAC Verification

**Status:** Accepted
**Date:** 2026-03-18

## Context

Dazzle generates production APIs from DSL declarations. Those APIs carry access control rules expressed as `permit:` and `scope:` blocks. As the platform moves into financial services and education deployments, two requirements became non-negotiable:

1. **Provable enforcement** — declared access rules must be demonstrably enforced at runtime, not just present in the DSL.
2. **Audit evidence** — ISO 27001 and SOC 2 auditors require an evidence chain showing that access control decisions are logged and that logs match the declared policy.

A single enforcement point (e.g. a middleware check) satisfies neither requirement: it can be bypassed, and it produces no evidence chain.

## Decision

Implement **three independent verification layers**, each cross-checking the others:

- **Layer 1 — Static Access Matrix**: Generated from `AppSpec` at parse time. Produces a deterministic `AccessMatrix` (persona × resource × action) that is the ground truth for what the DSL declares. CI validates this matrix against a golden master on every push.
- **Layer 2 — Dynamic Conformance Testing**: At test time, a golden-master database fixture is populated and every (persona, resource, action) triple from Layer 1 is exercised against the live FastAPI stack. Mismatches between declared and enforced access are hard failures.
- **Layer 3 — Immutable Decision Audit Trail**: At runtime, every access control decision (allow or deny) is appended to an append-only audit log with persona, resource, action, decision, and timestamp. The log is never mutated or deleted.

Layers 1 and 2 cross-check at test time. Layers 1 and 3 cross-check in the compliance report: any runtime decision that diverges from the static matrix is flagged as a violation.

### Package Structure

```
src/dazzle/rbac/
  matrix.py      # Layer 1 — static matrix generation
  verifier.py    # Layer 2 — dynamic conformance types
  audit.py       # Layer 3 — append-only decision log
  report.py      # Cross-layer compliance report
```

## Consequences

### Positive

- "Secure by construction" — a DSL change that weakens access control fails CI before it reaches production.
- Complete mediation: every access decision is logged, enabling post-hoc audit.
- Compliance reports generated from `src/dazzle/rbac/report.py` provide ready evidence for ISO 27001 control A.9 and SOC 2 CC6.
- The `examples/rbac_validation/` example exercises every RBAC pattern and serves as both documentation and regression baseline.

### Negative

- Layer 2 requires a test database fixture for every app — adds setup cost for new examples.
- Append-only audit log grows without bound; rotation policy is out of scope for this ADR.
- Three layers means three places to update when RBAC semantics change.

### Neutral

- The CI security gate (`.github/workflows/ci.yml`) validates the Shapes RBAC golden master on every push.
- 118 RBAC tests across five test files cover the matrix, verifier, audit, and report modules.

## Alternatives Considered

### 1. Runtime-Only Enforcement Without Specification Validation

Enforce access control in middleware and trust that the code is correct.

**Rejected:** No way to prove the declared policy matches the enforced policy. Fails the "provable enforcement" requirement.

### 2. Point Fixes Without Systematic Verification

Add RBAC checks reactively when issues are found.

**Rejected:** Leaves gaps between fixes. No audit trail. Cannot satisfy compliance auditors.

### 3. Single-Layer RBAC Checks

One unified check that both validates the spec and enforces at runtime.

**Rejected:** A single layer cannot cross-check itself. Does not produce the evidence chain required for ISO 27001 / SOC 2.

## Implementation

See `src/dazzle/rbac/` for all four modules. The bootstrap workflow (step 7 and step 14) requires RBAC matrix verification for all new apps. The compliance pipeline in `src/dazzle/compliance/` consumes the Layer 3 audit trail for evidence extraction.
