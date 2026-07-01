# Plan — First-party usage signal → UX inference (ADR-0050, Option A)

**Decision:** ADR-0050 (Accepted, Option A). **Unblocks:** #1517 `1a` (region-form inference) / `3a` (action prominence).
**Thesis:** close the *observe→infer* loop — usage frequency becomes a dynamic input to the DSL→render inference layer, alongside the static AppSpec.
**Anchors verified 2026-07-01** against the current tree.

## Invariants (hold across every phase)

- **Cold-start = today.** A surface with zero usage rows renders **byte-identically** to current output. Usage only ever *refines* a default that already works.
- **Tenant-fenced.** Every read is `WHERE tenant_id = <current>`; a second tenant's usage never influences another's UI.
- **No new singleton** (ADR-0005) — the collector hangs off `RuntimeServices` / lifespan hooks.
- **Postgres-only** (ADR-0008); framework table registered (ADR-0047) + in the baseline (ADR-0044).
- **Traceable** (model-driven-failure rubric) — a usage-driven UI choice is explainable ("widget X because field Y engaged N×"), never a silent oracle.
- **Not** product analytics (no consent/GA4/PII here) and **not** Vitality (code-node health).

## Phase 1 — Capture foundation (Postgres, registered)

**Goal:** a lean framework table exists and a narrowed collector writes to it, started at boot.

- New `_dazzle_usage_events(id, tenant_id, surface, kind, target, ts)` — `kind ∈ {'field','action'}`, `target` = field name or action name. Indexes: `(tenant_id, surface, kind, target)`, `(tenant_id, ts)`.
- `ensure_usage_events_table(cur)` creator (idempotent `CREATE TABLE IF NOT EXISTS` + indexes), pattern from `http/runtime/audit_log.py::ensure_audit_log_table`.
- Register in `dazzle.db.artifact_registry` via `_fw(...)`; call from `http/runtime/framework_schema.py::_ensure_framework_schema_ddl`; regenerate baseline (`dazzle db reframework-baseline`).
- `UsageCollector` (batched async writer, adapted from `analytics_collector.py`'s batch/flush; `feature_use`/`action` only) on `RuntimeServices` (`http/runtime/services.py`); start/stop via `register_lifespan_hook` (`http/runtime/lifespan_hooks.py`, wired in `server.py`).

**Gate:** `pytest -k db_artifact_contract` green (table registered + gated); real-PG test: collector.record → flush → row present. `dazzle db` parity gates green.

## Phase 2 — Scope-safe aggregate

**Goal:** one reader returns usage counts per `(surface, kind, target)` for the current tenant.

- `usage_counts(tenant_id, surface) -> dict[(kind,target), int]` — a single tenant-fenced `GROUP BY`. (Framework-owned, tenant-keyed → tenant fence *is* the scope contract; no domain scope-predicate needed.)

**Gate:** real-PG test: seeded rows aggregate correctly; a second tenant's rows are excluded.

## Phase 3 — Event origination

**Sequencing decided (James, 2026-07-01): 3a-first, defer the 1a fork.**

### 3a — heading-action clicks (SHIPPED)

**Mechanism decided (James, 2026-07-01): tag anchors + recording hook** (over a
boot route-map middleware). Workspace heading actions render as `hx-boost`ed
anchors (`_render_shell.py`); each is tagged with `hx-headers` carrying its
`"<surface>|<route>"` identity. A **raw ASGI** `UsageSignalMiddleware` (NOT
`BaseHTTPMiddleware` — SSE/streaming-safe, per the `csrf.py` convention) records
the click **after the response** (when `request.state.tenant` is resolved),
reusing the internally-safe `record_usage_from_request`. Pure declarative htmx —
no bespoke JS. Verified end-to-end (post-response tenant visibility via shared
scope state) with a TestClient test.

### 1a — field engagement (DEFERRED, fork open)

Client-side capture of which form fields users engage. Fork to settle *after* 3a
proves the loop: existing `/_analytics/beacon/*` endpoint vs a small htmx/Alpine
focus hook vs skip 1a. Deferred by decision.

**Gate (3a):** clicking a heading action writes an `action` row keyed by
`(surface, route)`; a non-heading request writes nothing.

## Phase 4 — Inference consumers (cold-start-safe, traceable)

**Goal:** usage refines the two deferred criteria.

- **3a — action prominence:** `page/runtime/action_prominence_resolver.py::resolve_action_prominence` currently keeps the first `budget=3` by declaration order. Reorder/promote by usage count; zero usage → declaration order (today).
- **1a — form widget:** `render/fragment/form_field.py::field_dict_to_primitive` dispatches on `field_dict["widget"]`. Let usage pre-populate `widget` (e.g. promote combobox for a heavily-used enum) *before* dispatch; zero usage → current `display:auto` choice.
- Each carries an `explain`-style trace of the signal that moved the choice.

**Gate:** seeded usage changes the rendered choice; a zero-usage surface reproduces today's DOM **exactly** (byte parity fixture).

## Checkpoints (worth a decision before locking in)

1. **Phase 3 field-origination** — beacon vs htmx-hook vs 3a-first (defer 1a). Recommendation: **ship 3a first** (server-side action signal is clean and needs no client work), then decide 1a's client capture with real 3a data in hand.
2. **Phase 4 thresholds** — how much usage before overriding a static default (avoid thrash on thin data). Recommend a minimum-sample floor per surface; below it, stay static.

## Sequencing note

Phases 1→2 are unambiguous foundation — build straight through. Phase 3 splits: **actions (3a) are the low-risk high-signal path; do them first**, prove the loop end-to-end on `3a`, then extend to `1a` field capture once the mechanism is proven. This delivers a *complete closed loop* (capture→aggregate→infer for actions) before taking on the fiddlier client-side field capture.
