# ADR-0050 — First-party usage signal: framework inference input, or operator feature?

**Status:** Accepted (2026-07-01) — **Option A chosen** (first-party usage is a framework inference input, narrowed). Implementation phased; see the plan referenced below. Option B is retained in this record as the rejected alternative.
**Origin:** #1517 defers two L4 UX-maturity criteria (`1a` region-form inference, `3a` action prominence) as **"telemetry-gated"** — they need usage data the framework doesn't feed into inference. Surfaced while auditing the telemetry landscape (`dev_docs/2026-07-01-telemetry-observability-state-of-play.md`).
**Related:** ADR-0011 (SSR + htmx), ADR-0023/0048/0049 (typed render substrate — the inference *consumer*), ADR-0005 (no new singletons — the wiring constraint), ADR-0008 (Postgres-only in the app runtime — bears on where a usage aggregate lives). Distinct from the compliance/analytics product-analytics stack and from the un-actioned *Vitality* code-health thesis (`dev_docs/dazzle-vitality-*.md`).

## Context

"Telemetry" in Dazzle names **four orthogonal things**, built to four depths, never unified:
end-user usage analytics, code-node vitality, perf observability (shipped: `perf/`, OTLP #1192,
`dazzle perf`), and agent/MCP telemetry (`status telemetry`). The full map is in the
state-of-play note. This ADR is about exactly **one axis: first-party end-user usage** — and
only because it is the one the framework's *core thesis* depends on.

Dazzle's thesis is data-driven UI: `display:auto`, semantic-enum tone, comparison-delta grain,
field economy — *infer the interface from the data*. Several UX-maturity criteria have now hit
a ceiling that reads: **"cannot infer from usage because the framework never observes usage."**
Concretely, #1517:

- **1a** — which *form widget* to auto-select would improve with "which inputs users actually
  engage / abandon."
- **3a** — which *action* to make prominent would improve with "which actions users actually
  invoke, per surface."

The machine to capture this **already exists and is orphaned**:
`http/runtime/analytics_collector.py` records `action` / `click` / `feature_use` events,
tenant-scoped, batched, event-bus-wired — but `mount_ops_platform()` (its only wiring) is
**never called** in the current tree (stranded in the `back/`→`http/` rename, ADR-0041). So
the question is not "build a usage system" but "decide what the existing one is *for*, and
wire the minimal slice."

**Axis discipline (load-bearing):** this is *end-user* usage. It is **not** *Vitality*
(code-node exercise, for MCP-graph trust) and **not** product analytics (outbound GA4/GTM for
the app owner's own dashboards). Conflating them is how the last two efforts stalled — one
over-scoped into a consent/GA4 stack, one planned a code-health instrument. Keep them apart.

## Decision (the fork)

> **Is first-party end-user usage capture a first-class *framework signal that feeds UX
> inference*, or an *operator-facing dashboard feature*?**

### Option A — Framework inference input *(recommended, narrowed)*

Usage frequency is a first-class input to the DSL→render inference loop, on the same footing
as the AppSpec.

- Wire a **narrowed** subset of the existing collector into the app-factory lifespan (not the
  full ops platform): capture `feature_use` / `action` counts keyed by `(surface, field|action)`,
  tenant-scoped, respecting ADR-0005 (no new singleton — hang off `RuntimeServices`/`ServerState`).
- Expose **one scope-safe aggregate** (counts per surface+field+action, per tenant) that
  render-time inferers read — the same shape the aggregate pipeline already produces for charts
  (pre-aggregation, no RBAC leak).
- One inferer reads it to resolve **1a** (widget) and **3a** (prominence), unblocking #1517 at
  the source and composing with everything already shipped.
- **Explicitly out of scope of A:** consent banners, third-party sinks, PII vocab — those are
  product analytics, a separate feature. A captures *frequency for inference*, nothing that
  leaves the app.

### Option B — Operator dashboard only

Usage capture is an ops feature the app owner opts into; it does **not** feed inference.

- #1517 `1a`/`3a` stay honestly deferred (no usage signal reaches the render layer).
- The orphaned collector is revived as an opt-in `/_ops`-style dashboard (health + usage +
  API tracking), or formally retired.
- Product analytics (`analytics:` DSL + `compliance/analytics/`) is finished independently by
  wiring **one** example app end-to-end (consent → dataLayer → GA4 sink).

## Decision: Option A (accepted)

**Option A, narrowed.** It is the only telemetry move that advances the *core framework claim*
rather than adding adjacent infrastructure, and it is the cheapest because the capture surface
already exists — the work is *wiring + one aggregate + one inferer*, not a subsystem. B leaves
the thesis-ceiling in place and keeps a production-grade collector stranded and undiscovered.

**Storage refinement (load-bearing, decided with acceptance).** The orphaned collector *already*
persists to **PostgreSQL** — `OpsDatabase.record_analytics_event` INSERTs into an `analytics_events`
table (`http/runtime/ops_database.py`, "psycopg v3 exclusively"; the `.dazzle/ops.db`/SQLite claim
in `dev_docs/observability_platform.md` is **stale doc**, not the code). So this is not a storage
*port*; the real gaps are: (1) that table is **unregistered** — absent from the ADR-0047 db-artifact
registry and the ADR-0044 framework baseline (a consequence of the whole ops platform being
orphaned), so it isn't created for a normal app; and (2) its generic `(event_type, event_name,
properties JSONB)` shape aggregates awkwardly for inference (JSONB extraction in `GROUP BY`).
**Decision:** the narrowed feature captures to a **purpose-built lean framework table** with typed
columns — `_dazzle_usage_events(tenant_id, surface, kind ['field'|'action'], target, ts)` — registered
per ADR-0047 and built by the ADR-0044 orchestrator; inference reads it via a **tenant-fenced
`GROUP BY`** (usage rows are framework-owned and tenant-keyed, so tenant fencing is the scope
contract — it does *not* need the full domain scope-predicate algebra of `Repository.aggregate`).
This is why A is a *narrowing*: the ops platform (health / api-tracking / SSE) is **not** adopted;
only `feature_use`/`action` capture, on a lean typed table built for the inference `GROUP BY`.

## Consequences

- **If A:** the inference loop gains a *dynamic* input (usage), not just the *static* AppSpec —
  a genuine capability step, and the first time the framework closes the observe→infer loop it
  keeps promising. Risks to manage up front: (1) **cold-start** — inference must degrade to the
  current static default when a surface has no usage yet (never worse than today); (2)
  **scope-safety** — the aggregate must be pre-aggregated and tenant-fenced like chart
  aggregates (no per-user leak); (3) **determinism/traceability** (model-driven-failure rubric)
  — a usage-driven UI choice must be explainable ("widget X because field Y engaged N×"), or it
  becomes an un-auditable oracle; (4) **no new singleton** (ADR-0005).
- **If B:** simpler, but #1517's telemetry-gated tail is permanent until revisited, and the
  framework's data-driven story stays static-only.
- **Either way:** *Vitality* and *product analytics* are decided **separately** (this ADR
  deliberately does not fold them in — see Rejected).

## Rejected alternatives

- **Greenfield a usage pipeline.** The collector exists and is production-grade; rebuilding is
  waste. Revive + narrow.
- **Use the full product-analytics stack (GA4/consent) as the inference signal.** Over-scoped:
  inference needs local frequency counts, not a third-party outbound pipeline with consent
  gating. That stack is a separate *outbound* feature; coupling it to inference is how usage
  capture stalled before.
- **Fold Vitality in.** Different axis (code-node health for MCP-graph trust, not end-user
  usage). Bundling a hard node-identity-reconciliation project (its plan §1) into this decision
  would sink both. Vitality gets its own keep/revive/close call.
- **Leave it implicit.** The status quo — a stranded collector, a telemetry-gated deferral, and
  no recorded decision — is precisely the forgotten-islet failure this ADR exists to end.

## Implementation plan (phased)

Anchors verified 2026-07-01. Full plan: `docs/superpowers/plans/2026-07-01-first-party-usage-signal.md`.

- **Phase 1 — Capture foundation (Postgres, registered).** Lean `_dazzle_usage_events` table +
  `ensure_usage_events_table` creator, registered in `dazzle.db.artifact_registry` and called by
  the ADR-0044 orchestrator (`http/runtime/framework_schema.py::_ensure_framework_schema_ddl`);
  regenerate the framework baseline. A narrowed `UsageCollector` (batched writer, adapted from
  `analytics_collector`) hung off `RuntimeServices` (`http/runtime/services.py`) and started via
  `register_lifespan_hook` (`http/runtime/lifespan_hooks.py`, wired at `server.py`) — **no new
  singleton** (ADR-0005). *Gate:* db-artifact contract passes; collector starts; a row lands in PG.
- **Phase 2 — Scope-safe aggregate.** One tenant-fenced `GROUP BY (surface, kind, target)` count
  reader. *Gate:* returns correct counts; a second tenant's rows never appear.
- **Phase 3 — Event origination (the design-risk phase).** *Actions* record server-side when their
  endpoint fires (cheap, exact). *Field engagement* rides the existing `/_analytics/beacon/*`
  endpoints or an htmx event hook (client, best-effort). Kept behind Phase 1's collector so the
  origination method can change without touching storage. *Gate:* invoking an action / engaging a
  field writes the expected `usage_events` row.
- **Phase 4 — Inference consumers, cold-start-safe.** `3a`: replace the static budget/order in
  `page/runtime/action_prominence_resolver.py::resolve_action_prominence` with a usage-derived
  order. `1a`: let usage pre-populate `field_dict["widget"]` before
  `render/fragment/form_field.py::field_dict_to_primitive`. Both **fall back byte-identically to
  today when a surface has no usage rows** (cold-start), and carry an `explain`-style trace so a
  usage-driven choice is auditable (model-driven-failure rubric). *Gate:* seeded usage changes the
  choice; zero usage reproduces today's output exactly.

Phases 1–2 are unambiguous foundation. Phase 3's origination method and Phase 4's per-criterion
thresholds are the parts worth a checkpoint before locking in.
