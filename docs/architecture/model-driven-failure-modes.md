# Model-driven failure modes and risk scoring

Date: 2026-06-04

This document treats 4GL, CASE, and model-driven engineering history as a
threat model for Dazzle. Dazzle is intentionally in the same broad family:
higher-level specification, executable model, generated or interpreted runtime
behaviour, and a promise that routine business-app construction should require
less scattered hand-written code.

The point is not to prove that Dazzle is different. The point is to identify the
old failure modes early enough that Dazzle can measure and defend against them.

## 1. Core thesis

The old tools usually failed when they mistook "less code" for "less
complexity". They removed accidental complexity, then hid essential complexity:
domain exceptions, integration constraints, authorization, lifecycle state,
performance, migration, and operational behaviour.

Dazzle should make a narrower promise:

```text
Make app semantics explicit enough that humans and agents can safely collaborate.
```

That is not no-code, automatic programming, or a universal model of software. It
is a constrained runtime for a class of business applications whose repeated
semantics can be made inspectable.

One extension here is genuinely new relative to the cited 4GL/MDE literature:
**agent amplification**. The references below predate agent-authored change, so
their failure catalogue assumes humans write at human speed. Dazzle's agents
generate conforming changes faster than humans rebuild causal understanding, so
every classic failure mode gets an accelerant. That is why MDF-14 and the
`agent_multiplier` term carry weight the historical analysis cannot supply, and
why they should be read as first-class, not a footnote to the older modes.

## 2. Reference base

These references are the initial basis for the failure-mode catalogue and the
scoring model.

| Reference | Why it matters here |
|---|---|
| Fred Brooks, "No Silver Bullet - Essence and Accidents of Software Engineering", Computer, 1987. | Separates accidental complexity from essential complexity. Dazzle must avoid abstracting away the essence of app behaviour. |
| Parastoo Mohagheghi, Wasif Gilani, Alin Stefanescu, Miguel-Angel Fernandez, "An empirical study of the state of the practice and acceptance of model-driven engineering in four industrial cases", Empirical Software Engineering 18(1), 2013, DOI: https://doi.org/10.1007/s10664-012-9196-x | Finds usefulness, ease of use, and tool maturity as adoption determinants. Maps directly to Dazzle's developer and agent ergonomics. |
| Jon Whittle, John Hutchinson, Mark Rouncefield, "Model-driven engineering practices in industry: Social, organizational and managerial factors that lead to success or failure", Science of Computer Programming 89(B), 2014, DOI: https://doi.org/10.1016/j.scico.2013.03.017 | Finds that MDE success is strongly shaped by organizational and process integration, not only technical power. For Dazzle, the analogue is integration with Git, CLI, tests, local Python, and Postgres. |
| Adrian Rutle and Alessandro Rossini, "A Tentative Analysis of the Factors Affecting the Industrial Adoption of MDE", ChaMDE 2008. | Calls out metamodel development and version control as weak points. Dazzle's textual DSL and frozen IR are direct countermeasures, but metamodel growth remains a risk. |
| Vadim Zaytsev and Johan Fabry, "Fourth Generation Languages are Technical Debt", TechDebt 2019. | Frames 4GL legacy as a maintainability and migration problem. Dazzle must avoid becoming a private island whose apps cannot be inspected, migrated, or partially replaced. |

## 3. Failure-mode catalogue

Each failure mode has a historical mechanism, a Dazzle-specific shape, and a
candidate measurable signal. The "first detector" column names a plausible first
automated check, not a commitment that the detector exists today.

| ID | Failure mode | Historical mechanism | Dazzle-specific risk | Measurable signals | First detector |
|---|---|---|---|---|---|
| MDF-01 | Essential complexity hidden | Model claims the business is simpler than it is. Exceptions move into side code or manual process. | DSL constructs look clean while real user workflows require unmodelled policy, state, or integration branches. | Trial failures tagged "missing semantic construct"; route overrides per entity; custom services per surface. | Trial finding classifier plus override density scanner. |
| MDF-02 | Model/runtime drift | Diagrams/specifications stop matching generated or hand-edited implementation. | DSL/AppSpec says one thing, generated routes/rendered DOM/Postgres schema do another. | Validator pass but runtime route missing; AppSpec surface has no page route; schema columns absent or extra. | AppSpec-to-runtime drift gate. |
| MDF-03 | Opaque generation | Generated output cannot be understood or debugged by the team. | Runtime emits behaviour that cannot be traced from DSL to route/service/repository/render path. | Failing issue lacks a single inspect command to show source DSL, IR node, route, SQL, and rendered HTML. | Traceability smoke tests for each core construct. |
| MDF-04 | Escape-hatch collapse | 90 percent easy, 10 percent impossible or unmaintainable. | Custom behaviour requires bypassing RBAC, repository, renderer, or validation layers. | Route overrides without policy checks; custom renderers without contracts; app code importing private internals. | Escape-hatch audit. |
| MDF-05 | Metamodel overgrowth | Every edge case becomes a new modelling concept. | Parser/IR grows constructs faster than runtime semantics and docs can stay coherent. | New keyword count per release; constructs without examples; parser support without validator/runtime/docs/tests. | Construct completeness matrix. |
| MDF-06 | Version-control impedance | Visual or binary models cannot be reviewed, diffed, merged, or bisected. | Text DSL avoids most of this, but generated artefacts, snapshots, and docs can still become noisy or unauditable. | Non-text model artefacts under app source; large generated diffs; snapshots changed without source DSL changes. | Reviewability scanner. |
| MDF-07 | Database abstraction inversion | Tool hides the DB until important DB semantics cannot be expressed. | Dazzle loses Postgres-native guarantees behind portable abstractions or ad-hoc Python checks. | Framework code avoids RLS, partial indexes, JSONB, CTEs, or aggregate SQL where they are the correct model. | Postgres-native feature coverage audit. |
| MDF-08 | Integration/conformity blind spot | Model fits the ideal app, not the messy surrounding institutions. | External APIs, tenant rules, email, file storage, auth providers, and legacy schemas become untyped side channels. | Integrations lacking typed request/response contracts; app code with raw HTTP calls outside integration layer. | Integration contract coverage scan. |
| MDF-09 | Round-trip engineering loss | Code generation and manual edits fight each other. | Dazzle claims no generated-code drift, but downstream generated specs, migrations, docs, or stubs may become edited by hand. | Manual edits in generated files; generated file hash drift; source change not reflected downstream. | Generated-file guard plus provenance tags. |
| MDF-10 | Tool maturity gap | Tool is promising but brittle, slow, or hard to debug. | Agents can build faster than runtime maturity, creating comprehension debt and brittle app behaviour. | Flaky tests; repeated "works in example, fails in app" findings; missing diagnostics in CLI/MCP. | Maturity scorecard tied to failures and diagnostics. |
| MDF-11 | Adoption fantasy | Tool assumes users will adopt a new process wholesale. | Dazzle requires too much mental-model change before a competent engineer can make safe edits. | Docs gaps; repeated support questions; users bypass DSL for Python because placement is unclear. | Onboarding trial plus docs-search success metric. |
| MDF-12 | Correlated QA blind spots | The same author writes renderer and tests, so both miss the same bug. | DOM/IR tests pass while geometry, behaviour, accessibility, or data correctness fails. | Visual/Playwright failures with green unit/contract tests; consumer app catches framework issue first. | Orthogonal QA coverage matrix. |
| MDF-13 | Demo cliff | Happy-path app works; real data and real roles break. | Example apps look convincing but fail under permissions, empty states, large data, concurrency, or write paths. | Trial findings in create/update/delete flows; list performance degradation; persona-specific dead ends. | Qualitative trial and write-path audit. |
| MDF-14 | Agent-amplified abstraction debt | Agents generate conforming changes faster than humans can rebuild causal understanding. | Dazzle accumulates working runtime behaviour whose ownership and invariants are not internalised. | Large agent-authored changes without trace docs; repeated fixes in same subsystem; low inspectability. | Agent-change risk ledger. |

## 4. Scoring model

The first version should be simple enough to calculate from repository state,
test results, and backlog/trial evidence.

Each failure mode receives a 0-100 residual risk score:

```text
base = severity * exposure * detection_gap          # each term <= 1, so base <= 1
risk = round(100 * min(1.0, base * agent_multiplier))
```

Where:

| Term | Range | Meaning | How to calculate |
|---|---:|---|---|
| `severity` | 0.2 - 1.0 | How damaging the failure is if present. | Catalogue constant: 1=0.2, 2=0.4, 3=0.6, 4=0.8, 5=1.0. |
| `exposure` | 0.0 - 1.0 | How much of the current project/framework surface is vulnerable. | Scanner-specific ratio. Example: unchecked custom routes / all custom routes. |
| `detection_gap` | 0.05 - 1.0 | How likely the current QA stack is to miss it. | `max(0.05, 1 - detector_coverage)`. Coverage is efficacy-weighted, not a headcount of live detectors (see "Detector dimensions"). The 0.05 floor means a fully-detected mode never scores exactly 0 while `severity * exposure > 0`. |
| `agent_multiplier` | 1.0 - 1.3 | Whether agent coding tends to amplify this failure. | 1.0 low, 1.15 medium, 1.3 high. Catalogue constant until calibrated. |

This is intentionally not a pure FMEA RPN. Classic severity x occurrence x
detection is useful, but Dazzle needs three adaptations:

- "Occurrence" should be measured as exposure, because many failures are latent
  structural risks rather than already-observed incidents.
- Agent amplification matters because the system can now change faster than
  human comprehension.
- Detector coverage must be efficacy-weighted, not a count of live detectors: a
  detector that a real finding slipped past loses credit. Otherwise the score
  trends green as checks are added regardless of whether bugs still escape — the
  exact false-confidence trap MDF-12 describes.

### Severity constants

| ID | Severity | Rationale |
|---|---:|---|
| MDF-01 | 5 | Hidden essential complexity invalidates the whole model. |
| MDF-02 | 5 | Drift destroys trust in DSL as source of truth. |
| MDF-03 | 4 | Debug opacity slows every fix and raises comprehension debt. |
| MDF-04 | 5 | Unsafe escape hatches bypass core guarantees. |
| MDF-05 | 4 | Metamodel bloat creates long-term framework drag. |
| MDF-06 | 3 | Text DSL mitigates this, but generated artefacts can still rot. |
| MDF-07 | 5 | Losing Postgres-native semantics undermines correctness. |
| MDF-08 | 4 | Integration side channels are frequent production failure points. |
| MDF-09 | 4 | Round-trip loss recreates classic generated-code failure. |
| MDF-10 | 4 | Immature tooling blocks adoption even when the idea is sound. |
| MDF-11 | 3 | Adoption friction is serious but usually recoverable. |
| MDF-12 | 4 | Correlated QA gives false confidence. |
| MDF-13 | 5 | Demo cliff blocks real deployment. |
| MDF-14 | 4 | Agent-speed debt compounds unless made inspectable. |

### Detector dimensions

Each detector should be marked as `absent`, `defined`, or `live`.

```text
absent  = 0.0
defined = 0.4  # documented or test exists but not exercised in normal workflow
live    = 1.0  # runs in validate/lint/test/qa cycle with actionable output
```

Raw coverage is the average of the required dimensions for the failure mode. A
failure mode should normally require at least two dimensions so a single
author-correlated check cannot zero the risk.

Coverage is then efficacy-weighted by observed escapes, so a "live" detector
that a real finding slipped past does not get full credit:

```text
raw_coverage      = mean(required_dimension_levels)            # 0.0 - 1.0
escape_penalty    = serious_findings_that_slipped_live_detectors_90d
                    / max(1, serious_findings_90d)             # 0.0 - 1.0
detector_coverage = raw_coverage * (1 - escape_penalty)
detection_gap     = max(0.05, 1 - detector_coverage)
```

This couples MDF-12's `correlated_green_failures` back into every mode's
`detection_gap`: the moment a serious bug escapes the live checks, the residual
risk for that mode rises even after the bug itself is fixed. Without it, the
register measures detector *headcount* rather than detector *efficacy* and
becomes the vanity scorecard the rest of this document warns against.

| Dimension | Examples |
|---|---|
| Static | parser/linker/validator/linter/drift gate |
| Runtime | generated route smoke, DB schema check, policy check |
| Behaviour | Playwright, trial, write-path exercise, real HTTP flow |
| Orthogonal | visual geometry, accessibility, consumer-app report, external scanner |
| Traceability | inspect command, MCP report, source-to-runtime provenance |

## 5. Metric definitions

These are proposed scanner outputs. A later implementation should write JSON
with the same names so the risk calculation is reproducible.

### MDF-01 essential complexity hidden

```text
exposure = min(1.0, semantic_escape_count / max(1, surface_count))
semantic_escape_count =
  route_overrides_without_declared_reason
  + custom_services_without_process_or_integration_binding
  + trial_findings_missing_semantics_last_30d
```

Required detector dimensions: static, behaviour, traceability.

### MDF-02 model/runtime drift

```text
exposure = drift_failures / max(1, checked_runtime_projections)
checked_runtime_projections =
  routes_checked + tables_checked + rendered_surfaces_checked + policy_matrix_checked
```

Required detector dimensions: static, runtime, traceability.

### MDF-03 opaque generation

```text
exposure = 1 - inspectability_coverage
inspectability_coverage =
  constructs_with_source_to_runtime_trace / max(1, runtime_construct_count)
```

Required detector dimensions: traceability, runtime.

### MDF-04 escape-hatch collapse

```text
exposure = unsafe_escape_hatches / max(1, all_escape_hatches)
unsafe_escape_hatches =
  route_overrides_without_policy_check
  + custom_renderers_without_contract
  + app_code_imports_private_dazzle_modules
  + direct_db_access_outside_repository_boundary
```

Required detector dimensions: static, runtime.

### MDF-05 metamodel overgrowth

```text
exposure = incomplete_constructs / max(1, parser_construct_count)
incomplete_constructs =
  parser_constructs_missing_ir
  + parser_constructs_missing_validator
  + parser_constructs_missing_runtime_or_explicit_no_runtime_note
  + parser_constructs_missing_docs
  + parser_constructs_missing_tests
```

Required detector dimensions: static, traceability.

### MDF-06 version-control impedance

```text
exposure = unreviewable_artifacts / max(1, model_artifacts)
unreviewable_artifacts =
  binary_or_visual_model_files
  + generated_files_without_provenance
  + generated_files_changed_without_source_change
```

Required detector dimensions: static.

### MDF-07 database abstraction inversion

```text
exposure = postgres_semantics_in_python / max(1, db_semantic_sites)
postgres_semantics_in_python =
  python_row_filtering_after_unscoped_query
  + hand_rolled_uniqueness_checks_without_db_constraint
  + hand_rolled_scope_checks_without_policy_or_predicate
  + raw_json_text_handling_where_jsonb_fits
```

Required detector dimensions: static, runtime.

### MDF-08 integration/conformity blind spot

```text
exposure = untyped_integrations / max(1, integration_touchpoints)
untyped_integrations =
  raw_http_calls_in_app_code
  + integrations_without_request_response_schema
  + webhook_handlers_without_event_model
```

Required detector dimensions: static, behaviour.

### MDF-09 round-trip engineering loss

```text
exposure = round_trip_violations / max(1, generated_artifacts)
round_trip_violations =
  modified_auto_generated_files
  + stale_generated_specs
  + manual_migration_without_appspec_source
```

Required detector dimensions: static, runtime.

### MDF-10 tool maturity gap

```text
exposure = min(1.0, maturity_findings_last_30d / 20)
maturity_findings_last_30d =
  flaky_test_count
  + repeated_subsystem_bug_count
  + diagnostics_missing_count
  + qa_harness_rotted_count
```

Required detector dimensions: behaviour, orthogonal, traceability.

### MDF-11 adoption fantasy

```text
exposure = onboarding_failures / max(1, onboarding_trials)
onboarding_failures =
  docs_search_failures
  + placement_decision_failures
  + user_or_agent_edits_bypassing_dsl_due_to_confusion
```

Required detector dimensions: behaviour, traceability.

### MDF-12 correlated QA blind spots

```text
exposure = correlated_green_failures / max(1, total_serious_findings)
correlated_green_failures =
  serious_findings_where_static_and_contract_layers_were_green
```

Required detector dimensions: orthogonal, behaviour.

### MDF-13 demo cliff

```text
exposure = real_workflow_failures / max(1, real_workflow_trials)
real_workflow_failures =
  create_update_delete_trial_failures
  + persona_dead_ends
  + large_dataset_failures
  + permission_edge_failures
```

Required detector dimensions: behaviour, runtime, orthogonal.

### MDF-14 agent-amplified abstraction debt

```text
exposure = risky_agent_changes / max(1, agent_authored_changes)
risky_agent_changes =
  large_changes_without_trace_note
  + repeated_agent_fixes_same_subsystem
  + changes_touching_parser_ir_runtime_without_construct_matrix_update
```

Required detector dimensions: static, traceability.

The *discovery* mechanism for the agent-era constructs this mode amplifies —
how we find and validate new counter-priors for agent production specifically —
is [Agent self-reflection](agent-self-reflection.md).

## 6. Initial risk register

This is a qualitative seed register. The numbers below are **hand-set
placeholders, not computed** — they encode current judgement, not scanner
output, and must not be read as if the formula produced them. They stay
deliberately coarse until at least two detectors are live and calibrated against
real escapes (see section 10); a precise-looking computed score before then
would itself be an MDF-02 (the stated model drifting from actual values).

| ID | Current read | Seed risk | Why |
|---|---|---:|---|
| MDF-01 | Medium | 45 | Dazzle has strong DSL/IR structure, but trial findings can still reveal missing semantics. |
| MDF-02 | Medium-low | 30 | There are already drift gates, but runtime projection coverage is not complete. |
| MDF-03 | Medium | 50 | Some traces exist, but there is no single source-to-runtime inspect path for every construct. |
| MDF-04 | Medium-high | 60 | Escape hatches exist and need policy/contract auditing. |
| MDF-05 | High | 70 | Parser construct count is large. Completeness pressure is real. |
| MDF-06 | Low | 20 | Text DSL and Git help; generated artefact provenance still matters. |
| MDF-07 | Medium | 45 | Postgres-first ADRs are strong, but user app code can drift toward Python-side DB semantics. |
| MDF-08 | Medium | 50 | Integrations are inherently side-channel heavy. |
| MDF-09 | Medium-low | 35 | No generated app-code drift by design, but specs/migrations/docs can drift. |
| MDF-10 | Medium | 55 | Existing maturity docs show real but tractable runtime/harness defects. |
| MDF-11 | Medium | 45 | The mental-model transition is non-trivial, even for a competent engineer. |
| MDF-12 | High | 70 | The orthogonal QA doc shows this failure has already happened. |
| MDF-13 | High | 75 | Write paths, permissions, and real data are known weaker zones. |
| MDF-14 | Medium-high | 65 | Agent speed is a new accelerant for every other failure. |

## 7. First implementation slice

Do not start with all fourteen modes. Start with the failure modes that are both
high-risk and relatively measurable.

1. MDF-02 model/runtime drift
   - Add a JSON report that counts AppSpec surfaces, registered page routes,
     generated API routes, tables, and policy matrix rows.
   - Score drift as missing or extra runtime projections.

2. MDF-04 escape-hatch collapse
   - Scan route overrides, custom renderers, and app code imports.
   - Require explicit policy/contract/provenance comments for each escape hatch.

3. MDF-12 correlated QA blind spots
   - Extend QA reporting to classify detector dimensions.
   - A serious finding with only author-correlated green checks should increase
     risk even after the bug is fixed.

4. MDF-13 demo cliff
   - Turn qualitative trial outcomes into structured tags:
     `write_path`, `permission_edge`, `large_data`, `empty_state`,
     `integration`, `navigation_dead_end`.
   - Feed those tags into `real_workflow_failures`.

5. MDF-05 metamodel overgrowth
   - Maintain a construct completeness matrix:
     parser, IR, linker, validator, runtime, docs, examples, tests, inspect.
   - Any construct missing two or more cells is a risk contributor.

## 8. Output shape for a future scanner

A first CLI can emit this shape:

```json
{
  "generated_at": "2026-06-04T00:00:00Z",
  "project_root": "/path/to/project",
  "scores": [
    {
      "id": "MDF-04",
      "name": "escape-hatch collapse",
      "severity": 1.0,
      "exposure": 0.42,
      "detection_gap": 0.6,
      "agent_multiplier": 1.3,
      "risk": 33,
      "evidence": {
        "all_escape_hatches": 12,
        "unsafe_escape_hatches": 5,
        "detectors": {
          "static": "live",
          "runtime": "defined"
        }
      }
    }
  ],
  "overall": {
    "max_risk": 75,
    "mean_risk": 52,
    "high_risk_count": 3
  }
}
```

Overall score should not average away a severe mode, and several simultaneously
high modes should read as worse than one. Note that `mean(top_3_risks)` can
never exceed `max_risk`, so `max(max_risk, mean(top_3))` always degenerates to
`max_risk` and does nothing. Use instead:

```text
high_risk_count = count(scores where risk >= 60)
overall = min(100, round(max_risk + 5 * max(0, high_risk_count - 1)))
```

One high mode scores `max_risk`; each additional high mode adds 5, capped at
100. This keeps a single dangerous blind spot visible while still penalising a
framework that is broadly on fire, and never silently averages a severe mode
away.

## 9. Operating rule

When a new DSL construct, runtime subsystem, escape hatch, or QA harness is
proposed, reviewers should ask:

1. Which model-driven failure mode does this risk increasing?
2. Which detector dimension will catch it if we are wrong?
3. Is the detector live in the normal workflow, or merely documented?
4. Can a competent engineer trace the runtime behaviour back to DSL/AppSpec?
5. Does the abstraction preserve Postgres, auth, workflow, and UI semantics, or
   does it push them into side code?

If those questions cannot be answered, the change is not blocked by default, but
it should carry an explicit risk note and should not be sold as a new safe
pattern yet.

## 10. Self-application: what the register itself risks

This register is a QA harness and a small metamodel of its own, so it is subject
to the same failure modes it scores. Naming them is part of the design, not an
aside:

- **MDF-12 (false confidence).** A register that trends green as detectors are
  added — independent of whether bugs still escape — manufactures exactly the
  false comfort it is meant to catch. Mitigation: the efficacy-weighted
  `detection_gap` in section 4, plus the 0.05 floor so no mode reads as zero
  residual risk while it still has severity and exposure.
- **MDF-10 (tool maturity gap) / MDF-05 (metamodel overgrowth).** Fourteen modes
  and per-mode metrics are themselves surface that can rot or sprawl.
  Mitigations: (a) build the first version as a thin aggregator over JSON that
  existing gates already emit (`dazzle inspect api`, the drift gates, trial
  tags), not a new detector engine; (b) a new mode may not contribute a numeric
  score until it cites at least one *live* detector — modes with only `defined`
  detectors stay qualitative; (c) keep the register out of the blocking ship
  path until it has earned trust, so a rotted scanner cannot wedge releases.
- **MDF-02 (drift).** Hand-set seed numbers that look computed are themselves a
  drift. Keep the register qualitative until **at least two detectors are live
  and calibrated against real escapes**; only then turn on computed scores.

Operating consequence: ship the section 9 review questions and the corrected
formula first — they pay off with no scanner — and treat the scoring engine as
earned infrastructure, not a precondition.
