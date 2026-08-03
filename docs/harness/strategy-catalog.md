# Improve strategy catalog

One-line map of playbooks under `.claude/commands/improve/strategies/`.
**Executable detail stays in those files** — this index is for humans scanning
structure. Driver + force table: `.claude/commands/improve.md`.

Lanes: `framework-ux` · `example-apps` · `trials` · `ux-converge` · `test-suite` ·
`hm-convergence` (see `improve/lanes/`).

---

## Safety / inbox (often preempt product)

| Strategy | Question it answers | Typical trigger |
|----------|---------------------|-----------------|
| `cimonitor` | Is main CI green? What failed? | Step 0c; force `cimonitor` |
| `codeql` | Open high/error code-scanning alerts? | Step 0c2; force `codeql` |
| `consumer_issues` | Consumer or owner/pilot bugs open? | Inbox heat `consumer_bug` / `owner_bug` |
| `github_prs` | Dependabot ready / human PRs? | Inbox heat; Dependabot auto-merge path |
| `semgrep_hygiene` | Sentinel / Semgrep hygiene debt? | Force `semgrep` / cadence |

---

## Example-apps maturity & Goal B

| Strategy | Question it answers | Probe / prove |
|----------|---------------------|---------------|
| `product_maturity` | Thin product surfaces? | `example_product_maturity.py` |
| `demo_fleet` | Demo / bake-off residual? | `demo_fleet_bar.py` |
| `journey_dogfood` | Journey maturity residual? | `example_journey_maturity.py` |
| `story_walk` | Landing stories ↔ walks? | `story_walk_bar.py` |
| `agent_acceptance_panel` | Live trial / adoption criteria? | `trial_verdict_bar.py` + `qa trial` |
| `agent_qa_smoke` | Smoke dig residual? | `qa_smoke_bar.py` |
| `domain_lifecycle_priors` | Lifecycle / process priors stale? | `domain_cognition_bar.py` |
| `interesting_product` | Residual clear — buyer-visible depth? | Goal B depth + stills (post-5.8) |
| `hyperpart_presentation` | Presentation residual (OCR smells)? | `presentation` / demo quality |
| `visual_tier2_subagent` | Visual judgment on capture set? | after `dazzle qa capture` |

---

## Framework / HM / explore

| Strategy | Question it answers | Notes |
|----------|---------------------|-------|
| `dual_lock_expand` | Dual-lock / open-via expansion? | framework-ux / hm |
| `hyperpart_coherence` | Hyperpart coherence queue? | hm-convergence |
| `gallery_probes` | Gallery visual probes? | metered |
| `shadcn_parity` | Shadcn parity debt? | framework |
| `api_surface_audit` | API surface drift? | |
| `explore-subagent` | Explore phase fan-out? | budgeted |
| `owned_idle_exercise` | Exercise owned-but-idle tools? | capability map |

---

## Cadence / meta

| Strategy | Question it answers | Cadence |
|----------|---------------------|---------|
| `self_audit` | Recent tipward commits invent drift? | ~every 15 cycles; workflow `improve-self-audit` |
| *(driver)* capability-sweep | Map STALE/USED; top digs | ~every 20 cycles; workflow `improve-capability-sweep` |
| `trial_signal_action` | Drain trial-friction signals? | TR rows / signals |

---

## Workflows (parallel panels)

Driver still owns lock, gates, pick, ship, schedule. See `.grok/workflows/README.md`.

| Workflow | Replaces panel | Budget note |
|----------|----------------|-------------|
| `improve-self-audit` | self_audit fan-out | `budget_consumed: 0` |
| `improve-capability-sweep` | inventory + recommenders | `budget_consumed: 0` |
| `improve-visual-review` | visual tier-2 judgment | budget **5** |

---

## Related

- [Exemplar](improve-exemplar.md) · [Operator field guide](operator-field-guide.md) · Runtime: `.claude/commands/improve.md`
