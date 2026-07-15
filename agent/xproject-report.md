## Cross-Project Scan — 2026-07-13 (improve cycle 485)

Scanned sibling Dazzle apps on `/Volumes/SSD` via framework CLI (validate/lint/pulse/discovery).

### 1. AegisMark (0 hard findings)
**Scale:** 75 entities, 238 surfaces, 10 personas
**Health:** 98% launch ready (pulse)
**DSL:** valid

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| — | soft | lint | Various entities with permissions but missing surfaces (internal/admin models) — expected product posture |

### 2. cyfuture (1 framework-migration finding)
**Scale:** reports_count=25 (discovery); dsl_valid=**False**
**Health:** 32% launch ready (pulse degraded under parse fail)

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| 1 | high | validate | `stories.dsl:5` uses `actor:` — renamed to `persona:` in #1559 |

### 3. pennydreadful (1 framework-migration finding)
**Scale:** dsl_valid=**False**
**Health:** 30% launch ready

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| 1 | high | validate | `app.dsl:2770` uses `actor:` — renamed to `persona:` in #1559 |

## Cross-Project Synthesis
**Projects scanned:** 3 | **Hard findings:** 2 (same root cause)

### Shared patterns
- **`actor:` → `persona:` story field rename (#1559)** hits cyfuture + pennydreadful. AegisMark already migrated. This is consumer lag behind a framework rename, not a new Dazzle core bug.

### Framework impact assessment
- Rename messaging is clear (validate prints sed fix). No Dazzle-core regression this scan.
- AegisMark shows the healthy large-app posture (98% pulse).

### Per-project health comparison
| Project | Health | Entities | Surfaces | Findings |
|---------|--------|----------|----------|----------|
| AegisMark | 98% | 75 | 238 | soft surface gaps only |
| cyfuture | 32% | — | — | actor→persona parse |
| pennydreadful | 30% | — | — | actor→persona parse |

### Recommended actions
1. **Per-project:** migrate cyfuture + pennydreadful story fields (`actor:` → `persona:`) via the sed one-liner validate prints.
2. **Framework:** no new core fix required this cycle.
