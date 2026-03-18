# RBAC Verification Framework

Dazzle provides a three-layer access control verification system that proves DSL-declared security policies are enforced at runtime. This is not a testing framework that checks a few happy paths — it is a systematic verification of every role, entity, and operation in the application.

## Motivation

Most SaaS platforms treat access control as an implementation detail tested by a handful of integration tests. When those tests are green, security is assumed. This assumption fails because:

- Tests cover the paths the developer thought of, not the paths an attacker will find
- Access control code changes silently break existing rules when enforcement logic is refactored
- There is no way to prove to an auditor that the declared policy matches the observed behavior

Dazzle takes a different approach. Because the DSL is the complete specification of the application — including its access control rules — we can verify the entire security surface mechanically.

## Theoretical Foundation

The framework draws on established access control research:

**NIST RBAC Model** (Sandhu, Coyne, Feinstein & Youman, 1996; formalized as ANSI INCITS 359-2004). NIST defines four RBAC levels. Dazzle's `permit:` blocks implement RBAC0 (Core — role-to-permission assignment). The `forbid:` blocks implement RBAC2 (Constrained — static separation of duty). Field-condition rules like `school = current_user.school` extend into ABAC territory (NIST SP 800-162).

**Complete Mediation** (Saltzer & Schroeder, 1975). "Every access to every object must be checked against the access control mechanism." The verification framework probes every endpoint as every role — not just the endpoints with explicit rules — to confirm that unprotected paths are also denied.

**Reference Monitor** (Anderson, 1972). The `evaluate_permission()` function serves as Dazzle's reference monitor — a single, always-invoked mediation point. The audit trail instruments this function to produce a complete decision log.

**Decision Audit** (ISO 27001:2013 A.12.4.1 / ISO 27001:2022 Section 8.15; GDPR Article 30). The audit trail produces machine-readable Records of Processing Activities suitable for compliance reporting.

## Architecture

```
Layer 1: Static Access Matrix     ← "What SHOULD happen"
Layer 2: Dynamic Verification     ← "What DOES happen"
Layer 3: Decision Audit Trail     ← "WHY it happened"
```

Each layer is independently useful. Together they produce a provable security envelope.

### Layer 1: Static Access Matrix

Given a parsed AppSpec, compute the complete access matrix without running the app. For every `(role, entity, operation)` triple, determine:

| Decision | Meaning |
|----------|---------|
| `PERMIT` | Explicitly allowed by a permit rule (pure role gate) |
| `DENY` | Forbidden or no matching permit (default-deny) |
| `PERMIT_FILTERED` | Allowed but row-filtered by a field condition |
| `PERMIT_UNPROTECTED` | No access rules defined (backward-compat allows all) |

This is pure computation over the IR — no server, no database, sub-second for any app.

```bash
dazzle rbac matrix                    # Markdown table to stdout
dazzle rbac matrix --format json      # Machine-readable
dazzle rbac matrix --format csv       # Compliance spreadsheet
```

Example output:

```
| Entity   | Op     | oracle  | sovereign | architect | chromat  | outsider |
|----------|--------|---------|-----------|-----------|----------|----------|
| Shape    | list   | PERMIT  | FILTERED  | FILTERED  | FILTERED | DENY     |
| Shape    | read   | PERMIT  | FILTERED  | FILTERED  | FILTERED | DENY     |
| Shape    | create | PERMIT  | PERMIT    | DENY      | DENY     | DENY     |
| Shape    | delete | PERMIT  | FILTERED  | DENY      | DENY     | DENY     |
```

The matrix also emits static warnings: unrestricted entities (no rules), orphan roles (no permits), and redundant forbids.

### Layer 2: Dynamic Verification

Spin up the app with golden-master data and probe every cell in the matrix:

1. Start the app in test mode
2. Seed deterministic data (uniform distribution across roles/scopes)
3. Create test users — one per role, with known attributes
4. For each matrix cell, authenticate as the role and hit the endpoint
5. Compare observed HTTP status + row counts against expected decisions

A `DENY` cell should produce HTTP 403. A `PERMIT` cell should produce 200 with all rows. A `PERMIT_FILTERED` cell should produce 200 with a subset. Any mismatch is a **violation**.

```bash
dazzle rbac verify          # Full pipeline — CI gate (exit 1 on violations)
dazzle rbac report          # Compliance report from last run
```

### Layer 3: Decision Audit Trail

Every call to `evaluate_permission()` emits a structured `AccessDecisionRecord`:

```json
{
  "timestamp": "2026-03-18T14:30:00Z",
  "request_id": "a1b2c3d4",
  "user_id": "user-1",
  "roles": ["teacher"],
  "entity": "Student",
  "operation": "list",
  "allowed": true,
  "effect": "permit",
  "matched_rule": "permit list when role(teacher)",
  "tier": "gate"
}
```

The audit sink is pluggable: `NullAuditSink` in production (zero overhead), `InMemoryAuditSink` during verification (for cross-referencing), `JsonFileAuditSink` for persistent logging (`dazzle serve --audit-access`).

## The Shapes Validation App

Rather than testing RBAC against a real domain (where business logic confuses the security picture), Dazzle includes an abstract validation app: `examples/shapes_validation/`.

The domain is geometric: Shapes have a form, colour, and material, and belong to a Realm. Seven personas exercise every RBAC pattern:

| Persona | RBAC Pattern | What They Prove |
|---------|-------------|-----------------|
| **Oracle** | Platform admin (RBAC0) | Unrestricted cross-tenant access |
| **Sovereign** | Tenant admin | Everything in own realm, nothing outside |
| **Architect** | Scope filter (ABAC) | Row-level filtering by realm |
| **Chromat** | Attribute filter (ABAC) | Row-level filtering by colour |
| **Forgemaster** | Forbid override (RBAC2) | Separation of duty — FORBID > PERMIT |
| **Witness** | Mixed OR condition | Composite rules don't leak |
| **Outsider** | Deny-all baseline | Complete mediation — every endpoint rejects |

The golden-master seed is deterministic and uniform: expected row counts per role are pure arithmetic. Two Sovereigns (in different realms) prove multi-tenancy isolation: both are admins, neither sees the other's data.

This domain is deliberately abstract. Nobody looks at "Forgemaster can't see shadow-material shapes" and thinks "well, maybe it should." The access rules are the geometry, not the business logic.

## CI Integration

The Shapes RBAC matrix runs as a security gate in CI on every push:

```yaml
- name: Validate Shapes RBAC matrix (security gate)
  run: |
    cd examples/shapes_validation
    python -m dazzle rbac matrix --format json > /tmp/rbac-matrix.json
    # Fails CI if any entity has PERMIT_UNPROTECTED decisions
```

This catches:
- Entities added without access rules
- Changes to the Cedar evaluation engine that break enforcement
- Regressions in the `_is_field_condition` gate logic

## Cedar-Style Evaluation

Dazzle uses Cedar-inspired three-rule evaluation semantics:

1. **FORBID** — if any matching FORBID rule fires, access is denied (highest priority)
2. **PERMIT** — if any matching PERMIT rule fires, access is allowed
3. **Default deny** — if no rules match, access is denied

This means you can write permissive rules and then constrain them with targeted forbids:

```dsl
entity Shape "Shape":
  # Forgemaster sees metal and stone
  permit:
    list: material = metal or material = stone

  # But never shadow material (even if metal or stone)
  forbid:
    list: material = shadow
```

## Two-Tier Enforcement

Access rules evaluate in two tiers at runtime (see also [Access Control Reference](access-control.md#runtime-evaluation-model)):

**Tier 1 (Gate)**: Before any database query, check if the user's role has permission for this operation on this entity. Pure role-check rules (`list: role(teacher)`) are evaluated here. If denied, return 403 immediately.

**Tier 2 (Row Filter)**: Field-condition rules (`list: school = current_user.school`) are converted to SQL WHERE clauses and applied at query time. This ensures only authorized rows are returned.

The verification framework tests both tiers: Tier 1 failures produce 403 (caught by the `DENY` comparison), Tier 2 failures produce incorrect row counts (caught by the `PERMIT_FILTERED` comparison).

## References

- Anderson, J.P. (1972). *Computer Security Technology Planning Study*. ESD-TR-73-51. US Air Force Electronic Systems Division.
- Sandhu, R., Coyne, E.J., Feinstein, H.L. & Youman, C.E. (1996). Role-Based Access Control Models. *IEEE Computer*, 29(2), 38-47.
- Saltzer, J.H. & Schroeder, M.D. (1975). The Protection of Information in Computer Systems. *Proceedings of the IEEE*, 63(9), 1278-1308.
- NIST (2014). *Attribute Based Access Control (ABAC)*. NIST Special Publication 800-162.
- ANSI (2004). *Role Based Access Control*. ANSI INCITS 359-2004.
- ISO/IEC (2022). *Information Security Management Systems*. ISO/IEC 27001:2022.
