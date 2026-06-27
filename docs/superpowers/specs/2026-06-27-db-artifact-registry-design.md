# DB-artifact registry — single source of truth for every database artifact

**Date:** 2026-06-27
**Status:** Approved (design) — pending implementation plan
**Motivating incident:** #1495 (events + process-consumer ran ungated boot-DDL → `InsufficientPrivilege` under a non-owner runtime role; the #1462 residual). Diagnosing it required reconstructing five orthogonal facts per table from scattered ADRs and code comments.

## Problem

Dazzle manages many database artifacts across several classes, and an agent touching any DB bug must currently reconstruct, per table, five orthogonal facts that live in five different places:

| Dimension | Where it lives today |
|---|---|
| **Class** (framework-internal / event-bus transport / ops-DB / app-entity / tenant) | implicit — inferred from which subsystem creates it |
| **Creator** (which function issues the DDL) | the subsystem source |
| **Owner** (owner role vs the runtime's own role) | `rls_schema.py` role model + split-ownership docs |
| **RLS posture** (fenced / non-fenced / N/A) | `rls_schema.py` DDL generators |
| **In the ADR-0044 baseline?** | `framework_schema.py` + `framework_schema_snapshot.IN_SCOPE_TABLES` + the parity test (**triplicated, hand-synced**) |
| **Boot-DDL gated?** (guards with `skip_boot_schema_ddl()`) | emergent — whether each creator happens to call the gate |

No single per-artifact view ties these together. To know "is `_dazzle_event_inbox` in-baseline-and-gateable but `{prefix}events` excluded-and-self-creating?" an agent cross-references five locations. And the core enumerable fact — the in-scope table list — is triplicated across three files kept in sync by hand.

The #1495 class of bug is the direct consequence: a boot-DDL path that *should* be gated isn't, and nothing asserts the invariant, so it ships and only surfaces in production logs.

## Goal

A **definitive source of truth** with two faces, that **simplifies agent cognition**:

1. **The decision rules** — the taxonomy (the five dimensions, the five classes, the rule governing each: e.g. *in-baseline framework tables gate their boot-DDL; excluded dynamic-prefix transport tables self-create*).
2. **The per-artifact facts** — each artifact → its five properties, **declared** (not emergent) and **executably enforced** so they cannot rot.

## Decisions taken (the two forks)

- **Registry IS the source** (not a read-only lens): a single declarative registry that the parity test + a new contract gate read from, collapsing the triplicated in-scope list into one and making each property a *declared* field. It declares metadata *about* each table and cross-checks the orchestrator; it does **not** rewrite the DDL (the shared `ensure_*` functions stay).
- **Executable contract** (not a descriptive baseline): the gate *asserts* the invariants — in-baseline membership, the boot-DDL-gating invariant (the #1495 catcher), and RLS posture — so a new framework table or an ungated boot-DDL path fails CI until registry and code agree.

## Design

### A — The registry (declarative source)

New module `src/dazzle/db/artifact_registry.py` — pure data, no DB access, lives beside `schema_snapshot/diff/render`. Importable by the http-layer parity test, the inspect command, and doc-gen; **core does not depend on it** in v1.

```python
class ArtifactClass(StrEnum):
    FRAMEWORK_INTERNAL   # in the ADR-0044 baseline; owner-created; boot-DDL gated
    EVENT_BUS_TRANSPORT  # {prefix}events/offsets/dlq; excluded from baseline; self-creating
    OPS_DB               # separate ops database; own lifecycle; not in app-DB baseline
    APP_ENTITY           # per-DSL; migration-engine generated; class-row, not enumerated
    TENANT_REGISTRY      # public.tenants + per-tenant schemas; class-row

class Ownership(StrEnum):   OWNER_ROLE | RUNTIME_SELF | N_A
class RlsPosture(StrEnum):  FENCED | NON_FENCED | NOT_APPLICABLE

@dataclass(frozen=True)
class Artifact:
    name: str                 # exact name, OR a name_pattern for {prefix}* / per-tenant
    cls: ArtifactClass
    creator: str              # dotted ref to the function that issues the DDL
    owner: Ownership
    rls: RlsPosture
    in_baseline: bool         # in ensure_framework_schema / the ADR-0044 baseline
    boot_ddl_gated: bool      # creator must guard with skip_boot_schema_ddl()
    notes: str = ""
    is_pattern: bool = False  # name is a pattern (dynamic prefix / per-tenant), not exact

DB_ARTIFACTS: tuple[Artifact, ...] = ( ... )

def in_baseline_tables() -> frozenset[str]:
    """THE single source of the in-scope framework table set."""
    return frozenset(a.name for a in DB_ARTIFACTS if a.in_baseline and not a.is_pattern)
```

**Scope split — enumerate the static, describe the dynamic:**
- **Per-table rows** for the statically-knowable classes: `FRAMEWORK_INTERNAL` (the ~30 baseline tables), `EVENT_BUS_TRANSPORT` (the 3 prefixed shapes, as `is_pattern=True` rows), `OPS_DB` (the fixed ops set).
- **One class-descriptor row each** for the dynamic classes — `APP_ENTITY` (per-DSL) and `TENANT_REGISTRY` (per-tenant) — carrying the governing rule + creator pattern, since their tables can't be enumerated at framework build time. This keeps the registry complete ("all DB artifacts") without pretending to list per-app tables.

### B — The executable contract + collapsing the triplication

The registry becomes the **single** source of the in-scope list:
- `framework_schema_snapshot.IN_SCOPE_TABLES` → `= in_baseline_tables()` (registry-derived)
- the real-PG parity test imports the same helper
- `framework_schema.py`'s docstring stops re-listing and points at the registry

New `tests/unit/test_db_artifact_contract.py` (static, no DB) asserts declared-vs-real:
1. **Gating invariant (the #1495 catcher)** — a uniform biconditional over every enumerated artifact that names a concrete `creator` (skip `is_pattern` rows and the dynamic class-descriptor rows, which have no single creator fn): AST-scan the `creator` function and assert it early-returns on `skip_boot_schema_ddl()` **iff** `boot_ddl_gated=True`. So framework-internal in-baseline tables must gate (the #1495 fix); self-creating transport tables and ops-DB tables (`gated=False`) must *not*. One test covers every subsystem; an ungated boot-DDL path — or a spuriously-gated self-creating one — fails CI.
2. **Creator resolves** — every `creator` dotted-ref imports cleanly (no rotted references).
3. **RLS posture** — `FENCED` artifacts appear in `rls_schema.build_all_rls_ddl(...)` output with `FORCE ROW LEVEL SECURITY`; `NON_FENCED` framework tables do not. Static, against the DDL generator (no DB).

The existing real-PG parity gate (`tests/integration/test_framework_baseline_parity_pg.py`) keeps the structural three-way "orchestrator ≡ baseline ≡ snapshot" check — now reading `in_baseline_tables()`, so its no-unlisted-table guard is registry-sourced. The per-subsystem runtime tests (#1462, #1495) remain the behavioral backstop beneath the AST contract.

**How the gating invariant reads "is this creator gated":** AST scan of the creator function (static, robust, one test covers all) — *not* a runtime probe per creator. The runtime probes already exist as #1462/#1495 behavioral tests; the AST contract is the generic, exhaustive gate.

### C — The surfaces (what an agent touches)

- **`dazzle inspect db-artifacts`** — mirrors the `dazzle inspect api` family; prints the per-artifact table (`--json`, `--class <name>` filter). No `--write`/committed text mirror — the registry *is* the committed declarative form and the contract test is the gate (cleaner than api-surface's text-diff baseline).
- **`docs/reference/db-artifacts.md`** — the agent-readable reference: the five dimensions, the five classes + their rules, and "run `dazzle inspect db-artifacts` for the live per-table facts." The doc holds the *why*; the registry holds the *what* (no duplication). Wired into `docs/reference/index.md` + `semantics_kb/doc_pages.toml` so MCP surfaces it.
- **ADR-0047** (next free number; 0046 is taken) — short decision record: "the DB-artifact registry is the single source of truth for artifact metadata; the executable contract enforces the gating / in-baseline / RLS-posture invariants." Cross-links ADR-0008 / 0017 / 0044 / 0045 / 0036 / 0037.
- **ADR-0044 amendment** — add a forward-reference header (do **not** rewrite the body): artifact *membership + per-artifact metadata* is now sourced from the registry (ADR-0047); 0044's `IN_SCOPE_TABLES` is registry-derived. 0044 remains the record of the *baseline-construction-and-parity mechanism* (the squash, the shared-DDL-core, the three-way gate — all still live). Clean boundary, no two docs claiming to own the in-scope set.
- **CLAUDE.md pointer** — one line under the DB/ADR section: before adding a table / boot-DDL / RLS, read `docs/reference/db-artifacts.md` or run `dazzle inspect db-artifacts`; the registry is the source, the contract enforces the invariants. *This is the agent-cognition entry point.*

### ADR boundary (the reframe)

| Concern | Owner after this work |
|---|---|
| How the migration baseline is constructed + parity-gated | **ADR-0044** (unchanged decisions; gains a forward-ref header) |
| Which artifacts exist, and each one's class / owner / RLS / gating | **the registry / ADR-0047** |

ADR-0044 is **not superseded** — there is no reversal, and its parity mechanism still catches orchestrator↔baseline drift. Its scope is *narrowed and made explicit*, with membership/metadata handed to the registry.

## Blast radius & risk

Moderate, concentrated in one place: repointing `IN_SCOPE_TABLES` at the registry — must keep the real-PG parity gate green (the chief risk). Everything else is additive: the registry module, the AST contract test, the inspect command, the reference doc, ADR-0047, the ADR-0044 header, the CLAUDE.md line.

The registry restates some facts that live in DDL (creator function names as dotted strings); the contract test (creator-resolves + gating-invariant) makes those un-rottable — a renamed/ungated creator fails CI.

## Out of scope (v1)

- No rewrite of the orchestrator DDL or the `ensure_*` functions.
- No live-DB RLS introspection in the new contract (RLS check is static against `rls_schema`; live RLS drift detection already exists via `dazzle db verify` / `rls_drift.py`).
- No per-app-entity enumeration (those are dynamic; represented by the `APP_ENTITY` class row).
- No change to the migration engine (ADR-0045) or the squashed baseline (ADR-0044 mechanism).

## Success criteria

1. One module declares every framework DB artifact + its five properties; `in_baseline_tables()` is the *only* in-scope list, consumed by the snapshot + parity test (triplication gone).
2. `tests/unit/test_db_artifact_contract.py` fails if any `boot_ddl_gated=True` creator is ungated — i.e. the #1495 class is caught at test time.
3. `dazzle inspect db-artifacts` answers all five facts per artifact in one view; `docs/reference/db-artifacts.md` states the rules; CLAUDE.md points to both.
4. ADR-0044 + ADR-0047 have a clean, non-overlapping boundary.
5. Existing real-PG parity gate stays green.
