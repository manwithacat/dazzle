# /ux-cycle session retrospective — 2026-04-21

**Window:** cycle 366 (last idle tick) → cycle 372 (this retro). One session,
7 cycles, 4 productive. Wrote as the budget counter approached the 100-soft-cap
so the operator gets a clean handoff.

## What the loop produced this session

**5 infrastructure commits** (pre-resume, from the operator-led design session):

| Shape | What | Commit |
|---|---|---|
| #1 | Widened `test_page_route_coverage.py` to cover `workspace/` / `experience/` / `reports/` families; added `render_fragment` + `env.get_template` patterns; scan `src/dazzle/` in addition to dazzle_ui/dazzle_back | `8d076dc6` |
| #2 | New `test_ir_field_reader_parity.py` ratchet lint + 186-entry JSON baseline; AST-based reader scan over `.attr` accesses, `getattr` literals, and Jinja `.attr` refs | `95a23c4a` |
| #3 | New `tests/unit/audit_internals.py` + `make audit-internals` target; two-section report (IR orphans + module orphans) with re-export propagation | `fc8a2096` |
| #4 | Extended external-resource lint with a canonical-registry assertion: every allowlisted origin must cite a replacement path (#NNN / gap doc / cycle) | `e101fef7` |

Preflight gate: **6 lints → 7 lints**. Silent-drift coverage table: **6 → 8** entries.

**4 productive cycles** post-resume:

| Cycle | Strategy | Outcome | Commit |
|---|---|---|---|
| 367 | finding_investigation | **#838** filed — `TwoFactorConfig` has no producer + no consumer. Triple signal convergence (external-resource + page-route + reader-parity all point at 2FA) | `4dd472a7` |
| 368 | framework_gap_analysis | **Gap doc** `2026-04-21-ir-policy-field-drift.md` — systematised #838 into a subsystem-wide pattern covering ~50 of the 186 baselined orphans | `3c2b8b7d` |
| 369 | finding_investigation | **#839** filed — compliance pipeline has 3 tested-but-unwired modules (citation/renderer/slicer). Same shape as #834 | `f105bb7b` |
| 371 | finding_investigation | **Audit-tool fix** — suspected "fitness DSL orphan" was a bug in `_imports_in_file` (relative imports ignored). 150 → 65 orphans. New substrate-intel mode #5 added to the skill catalog | `4ddc525e` |

**1 housekeeping cycle** (370, `5715b076`) refreshed `dev_docs/ux-loop-state.md`
after 32 cycles of staleness.

## The three-way 2FA picture (coordinated for `/issues` pickup)

The loop now has **three independent filings** describing the same broken
subsystem. They should be picked up together:

- **#829** (cycle 299) — QR code leaks TOTP secret to `api.qrserver.com`
- **#831** (cycle 303) — `templates/2fa/*.html` ship, no page routes serve them
- **#838** (cycle 367) — `TwoFactorConfig` IR type has no producer / consumer

Each is a different layer (template / runtime / IR). Fixing all three is
probably a single coherent PR. Not fixing all three leaves the subsystem
broken regardless of which two you pick.

Cross-ref: `dev_docs/framework-gaps/2026-04-21-ir-policy-field-drift.md`
generalises #838 — the pattern (IR vocabulary without runtime teeth) also
applies to messaging, governance tenant-provisioning, grants, HLESS, approvals,
and LLM cost tracking.

## The external-resource triad (also coordinated)

- **#830** (cycle 301) — SRI hashes on external CDN loads
- **#832** (cycle 323) — Vendor Tailwind + own dist
- **#833** (cycle 325) — CSP default alignment

All three are phases of `dev_docs/framework-gaps/2026-04-20-external-resource-integrity.md`.

## Audit-tool blindspot work (cycle 371 discovered one; more remain)

The shape-#3 audit is a heuristic, not authoritative. After the relative-import
fix landed (150 → 65 orphans), the remaining 65 still include likely FPs:

- **node_modules paths**: `dazzle.examples.simple_task.build.simple_task.node_modules.flatted.python.flatted` — should be path-excluded
- **Build artefacts under src/**: anything in `src/**/build/`
- **MCP handler registration**: ~10 `dazzle.mcp.server.handlers.*` modules appear orphan but are almost certainly registered via decorators or a handlers dict rather than direct import
- **Agent missions loaded dynamically**: `dazzle.agent.missions.ux_explore_subagent` is called by the `/ux-cycle` skill's Step 5 via a subprocess `python -c` — no AST edge exists
- **Test discovery**: modules discovered by pytest but not imported elsewhere

Rough estimate: the real findings in the remaining 65 are probably ~5-10 (similar to the compliance trio), with the rest being blindspots. A followup audit-tool improvement pass (similar to cycle 371 relative-import fix) would tighten the list further.

## Explore budget state

- **Before session:** 93/100, auto-paused at cycle 340 (secondary short-circuit)
- **After session:** 99/100 — one slot from the primary soft cap
- The cap is designed to force operator review. Next productive cycle hits 100 and auto-pauses until a deliberate batch reset.

## Loop health

- **Finding-rate post-resume:** 100% (4/4 productive cycles delivered artifacts)
- **Shape-#3 audit real-finding rate:** 2/150 → 2/65 after cycle 371 fix (3.1% hit rate, up from 1.3%)
- **Heuristic 1 saves:** 1 this session (cycle 371 — prevented spurious fitness-parser issue)
- **Synthesis debt:** 0 (cycle 368 gap doc covered the one emerging theme)

## Operator decision points

1. **Pick up the 9 filed issues.** Natural grouping for `/issues`:
   - 2FA triad (#829, #831, #838) — one PR
   - External-resource triad (#830, #832, #833) — one staged PR set
   - Orphan-module pair (#834, #839) — each needs per-module triage (wire / retire / public-API)
   - WorkspaceContract persona (#835) — 2-option fix sketch already in the issue

2. **Triage the gap doc.** `2026-04-21-ir-policy-field-drift.md` covers ~50
   baselined orphans. Needs a subsystem-by-subsystem Verdict A/B call before
   individual fix cycles.

3. **Budget reset.** When ready to continue, `echo "0" > .dazzle/ux-cycle-explore-count`
   (or whatever delta you prefer). The loop's detection infrastructure is now
   solid — it will find new things faster than pre-resume.

4. **Audit-tool tightening.** The 65-orphan list can shrink further with:
   (a) `.gitignore`-aware path exclusion, (b) MCP handler registration pattern
   detection, (c) dynamic-import awareness for `python -c ...` subprocess calls.
   Not urgent; only matters if the advisory audit becomes authoritative.

## Where the loop was productive vs. where it wasn't

**Productive:** loop doing investigation + synthesis when seeded with
detection infrastructure. Cycle 340's 26-tick pause was correct behaviour
given the pre-resume detection was exhausted; cycles 367-369 validated that
new detection = new productivity.

**Not productive:** filing more issues without shipping fixes for the
existing queue. The 9-issue backlog is probably close to saturation for
`/issues`; filing a 10th provides diminishing value until closures happen.

**Load-bearing insight:** the loop is most valuable when paired with
detection infrastructure that keeps producing signal. It's least valuable
when re-walking the same backlog at the same resolution. New lints are the
durable investment; new issues off existing lints are transient.
