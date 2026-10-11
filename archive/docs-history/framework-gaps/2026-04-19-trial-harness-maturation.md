# Framework Gap — Trial Harness Maturation

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-04-19** during Dazzle's autonomous-improvement cycles. It records the
    framework as it was then and the gap being worked at the time; **it may not
    describe current behaviour.** Start from the [documentation home](../../index.md),
    or see [Project Evolution](../../architecture/evolution.md) for how these fit together.


**Status:** Nearly Fixed (6 of 7 contributing issues shipped; 1 deferred follow-up)
**Synthesized:** Cycle 258 (framework_gap_analysis)
**Contributing cycles:** /trial-cycle runs 1–14, /issues runs that resolved #810–#822
**Evidence weight:** 13 GitHub issues filed, 12 closed, over ~9 trial-cycle runs × 5 example apps

---

## Problem statement

`dazzle qa trial` (shipped v0.57.78) is the framework's qualitative-signal loop — an LLM acts as a business user evaluating a Dazzle app. Between 2026-04-18 and 2026-04-19 the loop ran ~14 cycles across all 5 example apps and surfaced a series of **harness-maturation defects** that, compounded, made the loop useless as a signal generator: every trial ended with the same dominant friction ("empty app, can't evaluate") because the fresh-DB, seed, and completion-detection paths each had broken invariants.

The trial harness is now fully functional. This gap doc consolidates what shipped and what's left.

## Evidence and resolution

| Issue | Observation | Status | Commit/version |
|-------|-------------|--------|----------------|
| #810  | --fresh-db flag proposed (seed cleanness) | ✓ shipped | v0.57.84 |
| #814  | --fresh-db silently no-ops (wrong DATABASE_URL — CLI commands never loaded .env) | ✓ fixed | v0.57.87 — promoted `_load_dotenv` into shared `cli.dotenv.load_project_dotenv`, called from `_resolve_url` |
| #814 (part 2) | --fresh-db tried to TRUNCATE virtual entities (SystemHealth, SystemMetric, etc.) | ✓ fixed | v0.57.87 — moved `VIRTUAL_ENTITY_NAMES` to `dazzle.db.virtual`, filtered out in `db_reset_impl` |
| #817  | --fresh-db leaves apps empty, every verdict becomes "no data" | ✓ fixed | v0.57.91 — `_seed_demo_data_for_trial` post-launch generates + loads blueprint data |
| #820  | Seed auths as admin, but apps scope create to business personas (3/5 apps had 100% 403 failure rate) | ✓ fixed | v0.57.92 — replaced DemoDataLoader HTTP path with direct POST to `/__test__/seed` (bypasses Cedar) |
| #818  | `submit_verdict` never called, 100% fallback-synthesis rate | ✓ fixed | v0.57.90 — step-N-5 nudge injected into `_build_messages` when budget drains; new `Mission.terminal_tools` declares the wrap-up tool name |
| #822  | `submit_verdict` doesn't terminate loop (outcome=max_steps even after verdict) | ✓ fixed | v0.57.92 — `_trial_completion` was `getattr(action, "tool_name", "")` vs the actual `action.target`. One-line fix + 5 tests |
| #819  | Dedup threshold too lenient (17 raw, 0 clustered) | ✓ fixed | v0.57.90 — lowered `_CLUSTER_SIMILARITY_THRESHOLD` 0.8 → 0.65 |
| #821  | Blueprints generate invalid data (full_name vs name, lorem ipsum in str(20), dates on enum/ref fields) | ✓ partially fixed | v0.57.93 — User `name`/`full_name` alias; heuristic guard drops wrong-typed values; 9 enum fields flipped from date_relative to enum_weighted |
| (meta)| Blueprint validation needs to be static not just runtime | ✓ added | v0.57.94 — `dazzle demo verify` CLI + soft-gate in `qa trial --fresh-db` |
| #813  | Ref-entity filter silently empty (page_size=200 exceeded backend cap of 100) | ✓ fixed | v0.57.82 |
| #815  | Plural entity URLs 404 (users type /app/tickets, Dazzle routes /app/ticket) | ✓ fixed | v0.57.88 — 301 redirect from plural to singular |
| #816  | Browser tab title stuck on "Page Not Found" after hx-boost navigation | ✓ fixed | v0.57.89 — `HX-Trigger-After-Swap: dz:titleUpdate` on partial responses |
| **deferred** | Blueprint ref-field authoring drift (free_text_lorem on ref fields in 4 apps, should be foreign_key) | ○ pending | Per-app authoring, not framework |

## Root cause synthesis

The trial harness is a layered system — truncate → seed → auth → evaluate → submit — and each layer had its own invariant violations:

1. **Layer: env config** — CLI commands outside `dazzle serve` never loaded `.env`, so URL resolution defaulted to the manifest-level DATABASE_URL (wrong DB per app). Fix: promote `.env` loading into shared CLI plumbing.
2. **Layer: SQL schema** — `db_reset_impl` didn't know about virtual entities (entities whose data lives in Redis, not Postgres). Fix: extract `VIRTUAL_ENTITY_NAMES` to a shared module, filter at truncate time.
3. **Layer: Cedar access** — seed auth was hardcoded to `admin`, but business entities scope create to business personas. Fix: use the RBAC-bypass `/__test__/seed` endpoint that calls the repository layer directly.
4. **Layer: agent wrap-up** — the `submit_verdict` tool was wired, documented in the system prompt, and available to the agent — but the budget was drained before the agent ever thought to call it. Fix: step-N-5 hard-stop nudge injected dynamically into `_build_messages`.
5. **Layer: completion signalling** — `_trial_completion` checked the wrong attribute on `AgentAction`. Fix: `action.target`, not `action.tool_name`.
6. **Layer: reporting** — 17 raw observations clustering to 0 was a threshold calibration bug. Fix: lower the SequenceMatcher ratio from 0.8 to 0.65.
7. **Layer: data quality** — blueprints had strategy/type mismatches (enum fields getting `date_relative`, ref fields getting `free_text_lorem`). Two fixes: runtime heuristic guard (drops obviously-wrong values) plus static `dazzle demo verify` CLI.

Each fix was small. The aggregate effect is large: simple_task now seeds 23/23 rows and the agent writes substantive, grounded verdicts. A loop that was producing uniform "can't evaluate" noise now produces app-specific UX critique.

## Deferred (not a framework bug)

- **Per-blueprint ref-field authoring** — 4 of 5 example apps have blueprints where ref fields (`assigned_to`, `created_by`, `system`, etc.) use `free_text_lorem` when they should use `foreign_key`. The heuristic guard (v0.57.93) drops these before POSTing so seed runs degrade gracefully, and `dazzle demo verify` (v0.57.94) flags them statically as errors. Fixing the blueprints themselves is authoring work per app, not framework work.

## Cross-gap signal

This gap intersects cleanly with two others:

- **persona-unaware-affordances** (this session's cycle 258 close): the trial harness's RBAC-bypass seed route (`#820` fix) demonstrates that the right answer for test infrastructure is a parallel, Cedar-exempt ingestion path — NOT retrofitting admin into every permit list. Applied lesson: keep production RBAC strict, give test scaffolding a side door with a shared secret gate.
- **error-page-navigation-dead-end** (this session's cycle 258 close): both this gap and that one are "a shipped feature had invariant X false when tested end-to-end". The class of bug is load-bearing — features pass unit tests, pass local hand-testing, and then a different consumer (the trial agent, or a different persona path) surfaces a gap.

## Open questions

1. Is 0.65 the right dedup threshold long-term? #819 shipped it as a tuning response to the cycle-3/cycle-8 false-negative cluster rate. If future trials show over-clustering, lower further or switch to (category, url) clustering with description as tiebreaker.
2. Should `dazzle demo verify` be wired into `dazzle demo generate` as a hard gate (refuse to write bad files)? Currently only `qa trial --fresh-db` runs it as a soft gate. Upside: no more silent "garbage written to dsl/seeds/demo_data/". Downside: users iterating on a blueprint may want generate-with-warnings as a workflow.
3. Is there a next-surface defect once blueprint data is clean? The trial loop has been dominated by harness defects for 2 days; once the surface settles, we should expect defects of the form "framework X doesn't handle realistic data Y" — e.g. pagination under 100+ rows, search relevance with real text, filter combinations that exercise index coverage. These were invisible while every trial ran against empty apps.
