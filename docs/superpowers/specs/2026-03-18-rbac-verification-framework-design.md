# RBAC Verification Framework

**Date**: 2026-03-18
**Status**: Design
**Issue**: #520 (RBAC rules parsed but not enforced)

## Problem

Dazzle generates applications from DSL specifications that include comprehensive access control declarations (`permit:`, `forbid:`, `visible:` blocks). These declarations are parsed into the IR and converted to backend specs, but enforcement gaps mean the running application may serve data that violates the declared policy. Issue #520 demonstrated this: all authenticated users could access all data regardless of role.

The root cause of #520 is a specific bug in the LIST gate logic (PR #503 regression), but the deeper problem is systemic: **there is no mechanism to prove that the runtime enforces the declared policy**. A point fix for #520 will be followed by more enforcement bugs unless we build verification into the platform.

## Design Principle

Dazzle is a secure-by-construction platform. The DSL is the specification; the runtime is the proof. If you declare access rules, the system must enforce them. The verification framework provides the evidence chain.

Absent wilful short-circuiting, it must not be possible to write a DSL involving roles that allows access to data not explicitly permitted by those roles.

## Theoretical Foundation

The framework is grounded in established access control theory:

- **NIST RBAC** (Sandhu et al., 2000; ANSI INCITS 359-2004) — four levels: Core (users → roles → permissions), Hierarchical (role inheritance), Constrained (separation of duty via forbid), Combined.
- **ABAC** (NIST SP 800-162) — Attribute-Based Access Control. Extends RBAC with field-condition rules (`school = current_user.school`).
- **Complete Mediation** (Saltzer & Schroeder, 1975) — every access to every object must be checked. The verifier exercises the platform's reference monitor (`evaluate_permission()`) by probing every access path.
- **Security Audit** (ISO 27001:2013 A.12.4.1 / ISO 27001:2022 §8.15, GDPR Article 30) — the decision audit trail provides machine-readable Records of Processing Activities.

## Architecture

Three independent layers that cross-check each other:

```
Layer 1: Static Access Matrix     ← "What SHOULD happen" (policy analysis)
Layer 2: Dynamic Verification     ← "What DOES happen" (conformance testing)
Layer 3: Decision Audit Trail     ← "WHY it happened" (evidence chain)
```

Each layer is independently useful. Together they produce a provable security envelope.

---

## Layer 1: Static Access Matrix

### Purpose

Generate the complete access matrix from a parsed AppSpec without running the app. Answers: "according to the DSL, what should each role be able to do?"

### Input/Output

- **Input**: `AppSpec` (parsed DSL)
- **Output**: `AccessMatrix` — maps `(role, entity, operation) → PolicyDecision`

### PolicyDecision enum

| Value | Meaning |
|-------|---------|
| `PERMIT` | Explicitly allowed by a permit rule (pure role gate) |
| `DENY` | Explicitly forbidden, or no matching permit (default-deny with rules present) |
| `PERMIT_FILTERED` | Allowed but row-filtered by a field condition |
| `PERMIT_UNPROTECTED` | No access rules defined — runtime allows all authenticated users (backward-compat) |

**Note on `PERMIT_UNPROTECTED`**: The runtime has a backward-compatibility path where entities with no permission rules allow all authenticated users to access them (`no_rules_default_allow`). The static matrix must reflect this to avoid false violations in Layer 2. The `PERMIT_UNPROTECTED` decision surfaces these entities as a **static warning** ("Unrestricted entity") so app authors can add explicit rules.

### Algorithm

For each `(role, entity, operation)` triple:

1. Collect all permission rules on the entity for the given operation
2. If no permission rules exist for this entity at all → `PERMIT_UNPROTECTED`
3. Evaluate Cedar semantics statically:
   - If any FORBID rule matches the role → `DENY`
   - If any PERMIT rule matches the role:
     - If the rule has no condition or a pure role-check condition → `PERMIT`
     - If the rule has a field-condition or grant-check condition → `PERMIT_FILTERED`
   - No matching rules → `DENY` (default-deny)
4. Role matching: a rule matches if `personas` is empty (applies to all) or the role is in `personas`. For condition-based matching, `role(X)` matches if the role equals X.
5. Unknown condition kinds → `PERMIT_FILTERED` (conservative — assume a field condition exists)

### Static policy warnings

The matrix generator also emits warnings:

- **Unrestricted entity**: entity with no access rules — all authenticated users can access (`PERMIT_UNPROTECTED`)
- **Orphan role**: role with no permits on any entity
- **Redundant forbid**: FORBID on a (role, entity, operation) where no PERMIT exists
- **Conflict note**: PERMIT + FORBID on same triple — informational, Cedar semantics are clear (FORBID wins)

### CLI

```bash
dazzle rbac matrix                    # markdown table to stdout
dazzle rbac matrix --format json      # machine-readable
dazzle rbac matrix --format csv       # compliance spreadsheet import
```

### MCP

`policy access_matrix` operation — returns the matrix as structured data. Distinct from the existing `policy coverage` operation which reports coverage gaps rather than the full (role, entity, operation) decision matrix.

### Performance

Pure computation over the IR. Sub-second for any app. No I/O, no server, no database.

---

## Layer 2: Dynamic Verification

### Purpose

Spin up the app with golden-master data and systematically probe every cell in the access matrix. Answers: "does the running app actually enforce what the DSL declares?"

### Input/Output

- **Input**: `AccessMatrix` (from Layer 1) + running app + golden-master database
- **Output**: `VerificationReport` — the matrix annotated with observed behavior

### Probe strategy

For each `(role, entity, operation)` cell:

1. Authenticate as a test user with the given role
2. Probe the endpoint:
   - **LIST**: `GET /{entities}/` — record HTTP status code + response row count
   - **READ**: `GET /{entities}/{id}` — against a known seeded record (one visible, one not)
   - **CREATE**: `POST /{entities}/` — with valid payload
   - **UPDATE**: `PUT /{entities}/{id}` — against a known record
   - **DELETE**: `DELETE /{entities}/{id}` — against a known record
3. Compare observed vs expected:

| Expected | Observed | Result |
|----------|----------|--------|
| `DENY` | HTTP 403 | PASS |
| `DENY` | HTTP 200 | **VIOLATION** |
| `PERMIT` | HTTP 200 + full row count | PASS |
| `PERMIT` | HTTP 403 | **VIOLATION** (over-restrictive) |
| `PERMIT_FILTERED` | HTTP 200 + row count ≤ total and > 0 | PASS |
| `PERMIT_FILTERED` | HTTP 200 + full row count | **VIOLATION** (unfiltered) |
| `PERMIT_FILTERED` | HTTP 200 + 0 rows | **WARNING** (may be seed gap) |
| `PERMIT_UNPROTECTED` | HTTP 200 + full row count | PASS |
| `PERMIT_UNPROTECTED` | HTTP 403 | **VIOLATION** (unexpected restriction) |

### Golden-master database

Seeded deterministically so expected row counts per role are computable:

- Seed N records per entity with guaranteed distribution: each colour bucket, realm bucket, and material bucket gets exactly the same count (uniform by construction, not by random chance)
- For each `PERMIT_FILTERED` cell, ensure both visible and invisible records exist
- Expected counts are pure arithmetic from the seed parameters
- Deterministic seed ensures reproducibility

**Distribution guarantee**: The seed generator constructs shapes by iterating over combinations, not by random sampling. For example, 60 shapes = 3 realms × 20 shapes/realm, with each realm getting exactly 4 shapes per colour (20/5=4). This makes expected counts exact, not approximate.

### Report persistence

Verification results are saved to `.dazzle/rbac-verify-report.json` as a serialized `VerificationReport`. This file is consumed by `dazzle rbac report` and `policy verify_status`.

### Execution model

```bash
dazzle rbac verify                     # full pipeline
dazzle rbac verify --role Oracle       # single role
dazzle rbac verify --entity Shape      # single entity
dazzle rbac verify --keep-server       # don't shut down after (for debugging)
```

Pipeline:
1. Generate access matrix (Layer 1)
2. Start app in test mode (`--local --test-mode`)
3. Seed golden-master database
4. Create test users (see Test Users section below)
5. For each matrix cell, probe endpoint as corresponding role
6. Collect access decisions via in-memory audit sink (Layer 3)
7. Compare observed vs expected, cross-reference with audit decisions
8. Shut down
9. Save `VerificationReport` to `.dazzle/rbac-verify-report.json`
10. Output summary to stdout

Exit code 0 = all cells match. Exit code 1 = violations found. **This is the CI gate.**

### Test users

The verifier creates test users from a `list[TestUserSpec]` configuration, not a 1:1 persona mapping. This allows multiple instantiations of the same persona with different attributes:

```python
@dataclass
class TestUserSpec:
    username: str
    roles: list[str]
    attributes: dict[str, str]  # realm, colour, etc.
```

For the Shapes app, 8 test users are created (Sovereign appears twice):

| Username | Role | Realm | Colour |
|----------|------|-------|--------|
| oracle | Oracle | — | — |
| sovereign_prism | Sovereign | Prism | — |
| sovereign_void | Sovereign | Void | — |
| architect | Architect | Prism | — |
| chromat | Chromat | — | blue |
| forgemaster | Forgemaster | — | — |
| witness | Witness | Prism | — |
| outsider | Outsider | — | — |

The two-Sovereign test proves tenancy isolation: both are admins, neither sees the other's data.

---

## Layer 3: Decision Audit Trail

### Purpose

Instrument `evaluate_permission()` to emit structured records of every access decision. Answers: "for this specific request, which rule matched, why, and what was the outcome?"

### AccessDecisionRecord

```python
@dataclass
class AccessDecisionRecord:
    timestamp: str           # ISO 8601
    request_id: str          # correlation ID
    user_id: str
    roles: list[str]
    entity: str
    operation: str           # list, read, create, update, delete
    allowed: bool
    effect: str              # permit, forbid, default_deny, no_rules_default_allow
    matched_rule: str        # human-readable: "permit list when role(Oracle)"
    record_id: str | None    # for per-record checks (None for list gate)
    tier: str                # "gate" or "row_filter"
```

**Note on `effect` values**: The `effect` field preserves the runtime's full decision taxonomy: `permit` (explicit rule matched), `forbid` (explicit forbid matched), `default_deny` (rules exist, none matched), `no_rules_default_allow` (no rules defined, backward-compat path). This maps directly to `PolicyDecision` values, enabling precise cross-referencing with Layer 1.

### AccessAuditSink protocol

```python
class AccessAuditSink(Protocol):
    def emit(self, record: AccessDecisionRecord) -> None: ...
```

Implementations:
- **JsonFileAuditSink** — writes to `.dazzle/access-audit.jsonl` (default when enabled)
- **InMemoryAuditSink** — used by Layer 2 verifier to collect decisions during test runs
- **NullAuditSink** — default in production (zero overhead)

### Instrumentation point

`access_evaluator.py:evaluate_permission()` — after computing the `AccessDecision`, emit to the configured sink. The evaluator already has all the data; this adds one function call.

**Fallthrough handling**: The evaluator's `return True` fallthrough for unknown condition kinds (line 300) will emit an audit record with `effect="permit"` and `matched_rule="unknown_condition_fallthrough"`. This makes the fallthrough visible in the audit trail rather than silently permitting access.

### Activation

- Off by default in production (NullAuditSink)
- `dazzle serve --audit-access` enables JsonFileAuditSink
- `dazzle rbac verify` automatically uses InMemoryAuditSink
- Configurable in `dazzle.toml`:
  ```toml
  [access_audit]
  enabled = false
  sink = "jsonl"           # "jsonl" | "null"
  path = ".dazzle/access-audit.jsonl"
  ```

### Cross-reference with Layer 2

The verifier collects audit decisions during probing and includes them in the verification report. For each violation, the report shows:
- What the matrix predicted
- What HTTP response was observed
- What access decision was logged (and which rule matched)

This three-way cross-check makes violations unambiguous.

---

## Compliance Report

```bash
dazzle rbac report                     # from last verify run
dazzle rbac report --format markdown   # default
dazzle rbac report --format json       # machine-readable
```

Reads from `.dazzle/rbac-verify-report.json` (persisted by `dazzle rbac verify`).

### Report structure

```markdown
# RBAC Verification Report
App: shapes_validation | Date: 2026-03-18T14:30:00Z | Dazzle: v0.42.0

## Summary
- Roles tested: 7 (Oracle, Sovereign, Architect, Chromat, Forgemaster, Witness, Outsider)
- Test users: 8 (Sovereign instantiated for Prism and Void)
- Entities tested: 3 (Shape, Realm, Inscription)
- Operations tested: 5 (list, read, create, update, delete)
- Total cells: 120
- Passed: 120 | Violated: 0

## Access Matrix (verified)
| Entity      | Op     | Oracle | Sovereign(P) | Sovereign(V) | Architect | Chromat | Forgemaster | Witness | Outsider |
|-------------|--------|--------|--------------|--------------|-----------|---------|-------------|---------|----------|
| Shape       | list   | PASS   | PASS         | PASS         | PASS      | PASS    | PASS        | PASS    | PASS     |
| ...         | ...    | ...    | ...          | ...          | ...       | ...     | ...         | ...     | ...      |

## Violations
(none)

## Decision Audit Trail
[for each cell: timestamp, matched rule, effect, HTTP status observed]

## Methodology
- Static matrix: NIST SP 800-162 policy analysis over DSL-declared permit/forbid rules
- Dynamic verification: Complete mediation testing (Saltzer & Schroeder, 1975)
- Decision audit: Per ISO 27001:2013 A.12.4.1 (ISO 27001:2022 §8.15)
- Golden-master seed: 60 shapes, 3 realms, deterministic (seed=42)
```

---

## CLI Command Group

```
dazzle rbac matrix       # Layer 1: static access matrix
dazzle rbac verify       # Layer 2+3: dynamic verification with audit
dazzle rbac report       # Compliance report from last verify run
```

### MCP operations

Added to the existing `policy` tool:
- `policy access_matrix` — returns access matrix as structured data (distinct from existing `policy coverage`)
- `policy verify_status` — returns last verification report summary

---

## Shapes Validation App

**Location**: `examples/shapes_validation/`

A purpose-built abstract domain designed to exercise every RBAC pattern without real-world domain bias. The access rules are the geometry, not the business logic.

### Domain model

**Entities**:

| Entity | Purpose | Fields |
|--------|---------|--------|
| **Realm** | Tenancy boundary | `name`, `sigil` |
| **Shape** | Core entity — all access patterns | `form` (enum), `colour` (enum), `material` (enum), `realm` (ref), `creator` (ref) |
| **Inscription** | Child entity — cascading access (see below) | `text`, `shape` (ref), `author` (ref) |

**Enums**:
- `form`: circle, triangle, square, hexagon, star
- `colour`: red, blue, green, gold, void
- `material`: glass, stone, metal, shadow

### Inscription cascading access

Inscription does **not** use automatic inheritance from Shape. The DSL has no first-class parent-child access inheritance. Instead, Inscription's access rules are written to deliberately mirror Shape's rules, with the field condition referencing the parent relationship:

```dsl
entity Inscription "Inscription":
  text: str(500) required
  shape: ref Shape required
  author: ref User required

  permit:
    # Mirrors Shape access rules through the parent ref
    list: role(oracle)
    read: role(oracle)
    list: shape.realm = current_user.realm    # Architect/Sovereign see inscriptions on their realm's shapes
    read: shape.realm = current_user.realm
```

This tests relationship traversal in access rules (`shape.realm`) without introducing a new DSL concept. The verification framework treats Inscription like any other entity — Layer 1 generates its matrix cells, Layer 2 probes its endpoints.

### Personas (7)

| Persona | RBAC Pattern | Tenancy | Access Description |
|---------|-------------|---------|-------------------|
| **Oracle** | Platform admin (RBAC0) | Cross-tenant | Everything — all shapes, all realms |
| **Sovereign** | Tenant admin (multi-tenancy) | Single-tenant | Everything in own realm, nothing outside |
| **Architect** | Scope filter (ABAC) | Single-tenant | All shapes in own realm |
| **Chromat** | Field-condition filter (ABAC) | Cross-tenant | Shapes matching their assigned colour, any realm |
| **Forgemaster** | Enum filter + forbid override (RBAC2) | Cross-tenant | Metal/stone shapes only, forbidden from shadow material |
| **Witness** | Mixed OR rule (ABAC composite) | Single-tenant | Own realm OR shapes they created |
| **Outsider** | Deny-all baseline (complete mediation) | None | Nothing — proves every endpoint rejects |

### What each persona exercises

| RBAC Concept | Persona | Assertion |
|-------------|---------|-----------|
| RBAC0 (Core) — pure role gate | Oracle, Outsider | Oracle: 200 + all rows. Outsider: 403 on every endpoint. |
| RBAC2 (Constrained) — separation of duty | Forgemaster | Permitted metal/stone, forbidden shadow. Mixed PERMIT + FORBID evaluation. |
| ABAC — single field condition | Chromat | Only shapes where `colour = current_user.colour`. Exactly 12 shapes (60 total, 5 colours, uniform). |
| ABAC — scope/tenancy filter | Architect, Sovereign | Only shapes where `realm = current_user.realm`. Exactly 20 shapes (60 total, 3 realms, uniform). |
| Multi-tenancy isolation | Sovereign × 2 | Two Sovereigns in different realms. Neither sees the other's data. Both are admins. |
| Composite OR condition | Witness | `realm = current_user.realm OR creator = current_user`. Verifies OR short-circuit doesn't leak. |
| Cascading access via ref traversal | All personas on Inscription | Inscription mirrors Shape rules via `shape.realm` ref traversal. |
| Complete mediation | Outsider | Every entity × every operation → 403. No endpoint is unprotected. |
| Default-deny | Any new entity added without rules | Matrix shows DENY for all roles. Verifier confirms 403. |

### Golden-master seed

Deterministic (seed=42), uniform by construction (not random sampling):

- **3 Realms**: Prism, Void, Lattice
- **60 Shapes**: 20 per realm. Within each realm: 4 per colour (20/5), ensuring exact colour distribution. Form and material are distributed across shapes to cover all combinations.
- **30 Inscriptions**: 10 per realm, linked to shapes in that realm
- **8 test users**: one per persona, Sovereign instantiated twice (Prism, Void)

Expected row counts per persona (exact, not approximate):

| Persona | Realm | Colour | Expected Shape list count |
|---------|-------|--------|--------------------------|
| Oracle | — | — | 60 (all) |
| Sovereign (Prism) | Prism | — | 20 |
| Sovereign (Void) | Void | — | 20 |
| Architect | Prism | — | 20 |
| Chromat | — | blue | 12 (4 per realm × 3 realms) |
| Forgemaster | — | — | computable from seed (metal+stone, minus shadow combos) |
| Witness | Prism | — | ≥20 (realm shapes + any self-created elsewhere) |
| Outsider | — | — | 0 (HTTP 403) |

---

## Prerequisite: Fix #520

Before the verification framework can produce meaningful results, the LIST gate bug must be fixed.

**Bug**: `route_generator.py` line 916 — the condition `has_field_conditions = any(r.condition is not None for r in list_rules)` erroneously classifies `role_check` conditions (which are evaluable without a record) as field conditions, causing the gate to be skipped for rules that use `condition.kind == "role_check"` instead of `personas`. Since the DSL parser always produces role checks as condition objects (never populating `personas`), the gate is effectively disabled for all role-based LIST rules.

**Fix**: Replace the `condition is not None` test with `_is_field_condition(condition)` which correctly classifies each condition kind:

```python
def _is_field_condition(condition: AccessConditionSpec | None) -> bool:
    """Return True if condition requires record data (field comparisons).

    Role checks and grant checks are evaluable at the gate (without a record).
    Note: grant_check evaluated with record=None will deny (grant scope field
    lookup returns None), which is correct gate behavior — the grant isn't
    proven without a record, so deny is safe.
    """
    if condition is None:
        return False
    if condition.kind == "role_check":
        return False  # evaluable without record
    if condition.kind == "grant_check":
        return True   # needs record.get(grant_scope_field)
    if condition.kind == "comparison":
        return True   # needs record field value
    if condition.kind == "logical":
        left_field = _is_field_condition(condition.logical_left)
        right_field = _is_field_condition(condition.logical_right)
        return left_field or right_field
    return False  # unknown kind — treat as gate-evaluable (deny is safe)
```

Then the gate becomes:
```python
has_field_conditions = any(_is_field_condition(r.condition) for r in list_rules)
```

**Test correction**: The existing test `test_list_returns_403_when_role_denied` uses `personas=["school_admin"]` with `condition=None` — a structure the DSL parser never produces. It must be updated to use `condition=AccessConditionSpec(kind="role_check", role_name="school_admin")` with `personas=[]` to match the real production code path.

---

## Implementation order

1. **Fix #520** — point fix to gate logic + test correction (prerequisite)
2. **Layer 1** — static access matrix generator (`src/dazzle/rbac/matrix.py`)
3. **Shapes app** — the example DSL (`examples/shapes_validation/`)
4. **Layer 3** — audit trail instrumentation (small — one emit call in evaluator)
5. **Layer 2** — dynamic verifier (`src/dazzle/rbac/verifier.py`)
6. **CLI** — `dazzle rbac` command group
7. **Report** — compliance document generator
8. **MCP** — `policy access_matrix` and `policy verify_status` operations

---

## File locations

| Component | Path |
|-----------|------|
| Access matrix generator | `src/dazzle/rbac/matrix.py` |
| Dynamic verifier | `src/dazzle/rbac/verifier.py` |
| Audit trail types + sinks | `src/dazzle/rbac/audit.py` |
| Compliance report | `src/dazzle/rbac/report.py` |
| CLI commands | `src/dazzle/cli/rbac.py` |
| Shapes validation app | `examples/shapes_validation/` |
| Audit sink wiring | `src/dazzle_back/runtime/access_evaluator.py` (instrumentation) |
| Verification report storage | `.dazzle/rbac-verify-report.json` |

## Non-goals

- Role inheritance (RBAC1) — not currently in the DSL. Can be added later.
- Real-time enforcement monitoring — this is verification, not runtime intrusion detection.
- UI-level testing (Playwright) — the verifier tests API endpoints. Surface-level access is a separate concern already handled by surface `access:` declarations.
