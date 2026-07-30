# Agent domain priors: Schema.org/OWL thesis vs measured example sophistication

**Date:** 2026-07-29
**Status:** investigation complete enough to choose a path
**Audience:** agents improving Dazzle cognition / example density
**Related thesis:** `~/Desktop/dazzle-owl-prior-investigation-spec.md` (external research spec)
**Runnable probes:**
- `docs/research/scripts/example_sophistication.py`
- `docs/research/scripts/domain_prior_probe.py`

## Question

Does instrumenting founder/domain analysis with Schema.org + OWL (or any
general-purpose open-world prior) improve **agent cognition** on Dazzle SaaS
builds, in a way that shows up as higher sophistication in example apps?

Success criterion for this investigation: a **clear, implementable path** whose
progress is measurable on the example fleet — not a better ontology essay.

## Method

1. Score all `examples/*` DSL on sophistication axes (personas, processes,
   status+transitions, scopes, stories, …).
2. Run the **actual** agent path (`domain extract` → lifecycle_hint on nouns)
   against each example brief and compare to gold DSL.
3. Run `spec_analyze` discover/lifecycles/patterns on the same briefs.
4. Ask whether Schema.org/OWL would close the measured gaps.

## Finding 1 — Example sophistication is uneven, and process is the rarest density

Re-run:

```bash
.venv/bin/python docs/research/scripts/example_sophistication.py
```

Snapshot (2026-07-29):

| example | score | personas | processes | status+trans | status∄trans | ≥3p∄process |
|---------|------:|---------:|----------:|-------------:|-------------:|:-----------:|
| fieldtest_hub | high | 4 | 0 | 4 | 0 | Y |
| simple_task | high | 3 | **3** | 1 | 0 | . |
| invoice_ops | mid | 6 | **1** | 1 | 2 | . |
| support_tickets | mid | 4 | 0 | 1 | 0 | Y |
| most others | mid–low | 2–4 | 0 | varies | some | often Y |

Interpretation for agents:

- The fleet already has **workspace/story density** on advanced apps.
- **Process blocks** exist almost only on `simple_task` (+ one on `invoice_ops`).
- Several gold apps have **status enums without transitions**
  (`ops_dashboard` Alert/Integration, `llm_ticket_classifier` Ticket,
  `PaymentAttempt` on invoice_ops, …).
- Multi-persona apps without processes are the dominant “thin process model”
  failure mode — including strong apps like `fieldtest_hub` and
  `support_tickets`.

That is the **measurement surface** for any prior work: move apps up on
`status_with_transitions`, `n_processes`, and down on `multi_persona_no_process`
and persona pollution — without inventing chrome entities.

## Finding 2 — Domain extract loses lifecycles that gold DSL already has

Re-run:

```bash
.venv/bin/python docs/research/scripts/domain_prior_probe.py
```

Observed pattern:

| example | gold lifecycle entity | domain lifecycle_hint | failure mode |
|---------|----------------------|----------------------|--------------|
| invoice_ops | `Invoice` draft→…→paid (+ role guards) | only `Payment` generic states | **wrong noun** + wrong template |
| support_tickets | `Ticket` open→…→closed | none on `SupportTicket` | **name mismatch** Ticket vs SupportTicket |
| fieldtest_hub | Device, IssueReport, FirmwareRelease, Task | Device (partial), Task (generic) | partial arrow-chain; firmware/issue missed |
| ops_dashboard | System has trans; Alert/Integration status only | none | extract under-mines lifecycle |
| simple_task | Task | Task (generic pattern) | ok-ish states; processes not proposed |

Causal chain in code (not theory):

1. `domain_brief.extract._run_offline_analyses` calls `identify_lifecycles`.
2. `identify_lifecycles` uses a **hardcoded** `lifecycle_keywords` map and brittle
   arrow-chain regex (splits `in_progress` into `in` / `progress`).
3. Attachment is **exact key match** on entity name
   (`life_by_entity.get(candidate)`). `SupportTicket` ≠ `Ticket`.
4. `inference_kb.toml` already has `workflow_templates` (order, ticket, invoice,
   task, …) seeded into the knowledge graph — but
   **`identify_lifecycles` does not call them**, and
   `propose_patterns` matches `patterns.toml` / counter-priors, not workflow
   templates.

So the high-value prior is **already authored** and **already partially gold**
in examples, yet the agent path does not deliver it into `AGENT_DOMAIN`.

`domain_brief/promote.py` literally tells agents: *“Add status lifecycles where
lifecycle_hint is non-empty.”* Empty hints ⇒ thinner DSL.

## Finding 3 — `discover_entities` still floods noise; extract filters chrome but pollutes personas

On SPECIFICATION-class briefs, raw `spec_analyze.discover_entities` still emits
large polluted sets (`JavaScript`, `Finally`, `Op`, role words as entities, …).
Domain extract’s deny list + grounding correctly **rejects** much of that into
`rejected_chrome`.

But personas systematically include generics (`user`, `admin`, `staff`,
`member`, `owner`, `customer`, `provider`) that are not job personas in gold
DSL for those apps. That steers agents toward extra desks and weak story spines.

Schema.org `Role` / `OrganizationRole` would **amplify** this class of prior,
not correct it.

## Finding 4 — Schema.org / OWL does not close measured gaps

| Measured gap | Schema.org/OWL help? | Why |
|--------------|----------------------|-----|
| lifecycle_hint empty / wrong noun | No | Needs name alignment + Dazzle transition DSL, not class hierarchy |
| status∄transitions in gold | No | Local completeness gate; optional template fill |
| multi-persona ∄ process | No | Process is Dazzle construct; Schema.org Action is not a process block |
| persona pollution | **Harms** | More generic roles |
| permit/scope density | No | Predicate algebra is closed-world, not OWL |
| invoice approval+dispute machine | No | Gold is more specific than Schema.org Invoice / inference template |
| chrome entity pollution | No | Already a grounding problem |

Schema.org *labels* for Invoice/Organization/Person already appear as grounded
nouns when the brief says them. The failure is **downstream structure**
(transitions, processes, scopes), not missing commercial vocabulary.

Open-world RL materialisation cannot flag “Invoice has status enum but no
transitions” or “four personas and zero process” — those are **closed-world
Dazzle completeness** checks.

## Finding 5 — Existing Dazzle priors are higher leverage than a new ontology

Already present:

| Asset | Intended job | Wiring gap |
|-------|--------------|------------|
| `inference_kb.toml` workflow_templates | status machines | not used by `identify_lifecycles` / domain extract |
| entity_archetypes + domain_entities | field packs | KG lookup exists; not auto-attached to AGENT_DOMAIN |
| `propose_patterns` | positive patterns + counter-priors | weak hit rate on example SPECs; no process proposals |
| counter-priors (`bootstrap_pollution`) | refuse polluting path | correct; incomplete positive alternative |
| gold examples | teaching corpus | process density thin; some status∄trans |

The agent cognition problem is **under-delivery of existing priors into the
domain intermediate and validate loop**, not absence of Schema.org.

## Clear path to improvement (agent-facing)

Ordered by expected Δ on example sophistication metrics and implementability.

### P0 — Lifecycle prior that actually attaches (highest leverage)

**Change**

1. In `identify_lifecycles` (or a pure helper it calls):
   - Query `workflow_templates` / lifecycle keywords via the same trigger match
     as `inference.lookup` (or direct TOML/KG).
   - Fuzzy-attach to entity names (`ticket` ⊂ `SupportTicket`, `invoice` ⊂
     `Invoice`).
   - Fix arrow-chain tokeniser so `in_progress` is atomic (`\w+` is wrong when
     states use underscores — use a state token pattern).
2. Optionally prefer **brief-local** arrow chains over generic templates when both
   exist (already intended; broken by tokenisation).
3. Re-extract example `AGENT_DOMAIN` / `agent_domain.json` and assert
   `gold_lifecycle_missing_from_domain` shrinks
   (`domain_prior_probe.py`).

**Measure**

- `domain_prior_probe.py`: count of `gold_lifecycle_missing_from_domain` → 0 on
  support_tickets, invoice_ops, fieldtest_hub.
- After agents re-author from domain: `example_sophistication.py`
  `status_without_transitions` decreases on fleet.

**Does not require** Schema.org or a reasoner.

### P1 — Process proposals for multi-persona domains

**Change**

When domain has ≥2 grounded personas and ≥1 lifecycle-bearing noun, emit
structured **process candidates** (not free-form prose):

- approval / dual-control (requester → approver)
- assignment / escalation (agent → manager)
- settlement / fulfilment (finance after approved)

Seed from `simple_task` processes + `invoice_ops.settle_invoice` as positive
examples in inference_kb or patterns.toml. Surface via
`spec_analyze.propose_patterns` or a `domain research` step.

**Measure**

- `multi_persona_no_process` flips false on ≥2 of
  {support_tickets, fieldtest_hub, design_studio, project_tracker} when
  re-authored or densified under agent loop.
- process count on fleet median > 0.

### P2 — Persona pollution filter

**Change**

After extract: drop persona ids in a generic set unless the brief has a **job
sentence** for them (not just role word in marketing chrome). Prefer personas
that appear in story/persona sections of the brief.

**Measure**

- `persona_pollution` list empty on invoice_ops / hr_records in probe.
- Fewer spurious desks in regenerated AGENT_DOMAIN.

### P3 — Gold example densification as eval harness (not just docs)

Treat the fleet as the cognition benchmark:

1. Close `status_without_transitions` where product-correct
   (Alert, Integration, PaymentAttempt, …).
2. Add **one** process to multi-persona apps that already have story spines
   (support_tickets escalation, fieldtest_hub issue triage, …) — only when the
   process is real, not decorative.
3. Keep scores in CI as a **non-blocking report** first (histogram), then gate
   regressions on P0 examples if desired.

**Measure**

- `example_sophistication.py --json` baseline committed or regenerated in
  research notes; Δscore after prior work.

### P4 — Schema.org (optional, demoted)

Only if P0–P2 are done and commercial noun coverage still fails on novel briefs:

- **Retrieval thesaurus only** (label → Dazzle field pack), no OWL reasoner.
- Never prefer Schema.org names over founder language.
- Eval: same sophistication metrics + fidelity (grounded noun rate).

**Default recommendation:** do not start here. Measured bottlenecks are not
vocabulary coverage.

### Explicit non-goals (from evidence)

- OWL RL materialisation on Schema.org for analysis agents
- LinkML intermediate for founder specs
- Neuro-symbolic axiom loops for bootstrap
- Replacing domain extract with bootstrap/`discover_entities` as default

These optimise for open-world consistency, not Dazzle closed-world executability.

## How an agent should use this note

1. Re-run the two scripts; treat tables as living.
2. Implement **P0** first; ship with unit tests on `identify_lifecycles` name
   attachment + arrow chains (`in_progress`).
3. Use `domain_prior_probe.py` as the gate for P0.
4. Only then open P1 process proposals.
5. Cite example sophistication Δ in the PR, not ontology coverage %.

## Implementation status (2026-07-30)

P0–P2 landed in-tree (no Schema.org):

| Change | Location |
|--------|----------|
| Lifecycle core (arrow tokens, fuzzy match, workflow_templates, process candidates) | `src/dazzle/domain_brief/lifecycles.py` |
| `spec_analyze.identify_lifecycles` delegates to core | `src/dazzle/mcp/server/handlers/spec_analyze.py` |
| Domain extract: re-bind on grounded nouns, fuzzy lifecycle, process_candidates, persona job filter | `src/dazzle/domain_brief/extract.py` |
| `ProcessCandidate` on `AgentDomain` + promote steps + markdown section | `models.py`, `promote.py`, `store.py` |
| Tests | `tests/unit/test_domain_brief_lifecycles.py` |

**Probe after P0** (`domain_prior_probe.py`): `gold_lifecycle_missing_from_domain` is empty for
invoice_ops, support_tickets, fieldtest_hub, design_studio, project_tracker. Residual miss:
ops_dashboard `System` (often not grounded as a noun). Persona pollution reduced but not zero
on long SPECIFICATION chrome.

**Next (P3):** densify gold examples (status∄trans, real processes) using the new domain
signals as the authoring checklist — optional fleet re-extract of AGENT_DOMAIN.

## Improve-loop integration (cycle 1462)

| Piece | Role |
|-------|------|
| `scripts/domain_cognition_bar.py` | Residual sensor: domain_stale, multi_persona∄process+candidates, status∄trans |
| `scripts/improve_example_probes.py` | Emits `domain_cognition` line; `next_strategy=domain_lifecycle_priors` when only residual |
| `improve/strategies/domain_lifecycle_priors.md` | Dig playbook: reextract → process/transitions densify |
| Capability map | `dazzle domain` + domain lifecycle/process priors Class COGNITION |

**First dig result:** reextract cleared fleet `domain_stale`; `support_tickets` process densify from `escalation` candidate raised sophistication score and cleared mpp. Residual remains on other multi-persona apps — intentional multi-cycle COGNITION work, not WI densify.

## Thesis verdict (for the external OWL/Schema.org spec)

| Claim | Verdict |
|-------|---------|
| Analysis-phase structured prior can help | **Yes**, if prior is Dazzle-shaped (lifecycle templates, process patterns, grounding) |
| Schema.org + OWL is the right prior | **No** on current evidence |
| Reasoner adds analysis quality | **Not supported**; gaps are attachment + completeness |
| Success via example sophistication | **Supported** — concrete metrics and scripts exist |

The external spec’s experimental protocol remains useful if re-targeted:

- **Baseline:** current domain extract + hand-author + validate
- **Treatment:** P0/P1 instrumented extract (inference_kb wired)
- **Not:** Schema.org retrieval vs baseline (low expected Δ)

## Appendix — code pointers

| Concern | Location |
|---------|----------|
| Domain extract + lifecycle attach | `src/dazzle/domain_brief/extract.py` |
| Lifecycle patterns (hardcoded) | `src/dazzle/mcp/server/handlers/spec_analyze.py` → `identify_lifecycles` |
| Workflow templates (unused by lifecycle) | `src/dazzle/mcp/inference_kb.toml` `[[workflow_templates]]` |
| Inference query API | `src/dazzle/mcp/inference.py` |
| Promote instruction depends on hints | `src/dazzle/domain_brief/promote.py` |
| Bootstrap pollution counter-prior | `docs/counter-priors/bootstrap-pollution.md` |
| Gold multi-process reference | `examples/simple_task` |
| Gold multi-party invoice lifecycle | `examples/invoice_ops/dsl/entities.dsl` `entity Invoice` |
