# Project Evolution

How Dazzle grew — and where to read the primary record of that growth.

Most of this site is **greenfield documentation**: it tells you how to build with
Dazzle *as it is today*. This page is the opposite. It is the curated front door to
Dazzle's **historical record** — the analyses, retrospectives, and snapshots produced
while the framework was being built — so the reasoning behind today's design stays
inspectable without cluttering the learning path.

!!! warning "These linked documents are point-in-time"
    Every document in the archive below is a dated snapshot and carries a banner
    saying so. Many describe gaps that have since been closed or decisions that were
    later superseded. They are kept for provenance, not as current guidance. For
    durable decisions, read the [ADRs](../adr/INDEX.md); for the released timeline,
    read the [CHANGELOG](https://github.com/manwithacat/dazzle/blob/main/CHANGELOG.md).

## The thesis that stayed constant

From early on, Dazzle has been built as a **prior-correction substrate**: a DSL whose
restricted grammar, strong conventions, and conformance gates exist to counteract the
statistical biases an LLM brings from its training data. The DSL is consumed primarily
by AI agents, so it favours precision and formal correctness over human ergonomics.
That framing — restrict the grammar, bias the inference, filter the output — is the
through-line connecting almost every decision recorded below. The
[Counter-Prior Catalogue](../counter-priors/INDEX.md) is the operational expression of it.

## How it grew

A few overlapping arcs account for most of the archive:

- **A typed UI substrate.** The UI runtime moved off Jinja2 to a frozen-dataclass
  Fragment tree rendered to HTML (ADR-0023), with contract verification asserting DOM
  shape against the AppSpec. Much of the gap archive comes from hardening this layer.
- **An autonomous-improvement loop.** What is now `/improve` began as `/ux-cycle`: a
  loop that walks the framework, finds gaps, files issues, and fixes them. Its
  `framework_gap_analysis` strategy periodically *synthesises* what it has learned into
  a standalone document — those syntheses are the **framework-gap analyses** archived
  below. They are the loop thinking out loud about where the framework was thin.
- **Authorization as algebra.** Access control converged on a formal predicate algebra:
  `permit:` for who, `scope:` for which rows, with `as:` clauses binding filters to
  personas (ADR-0010), statically validated against the FK graph and backed by a
  provable-RBAC package.
- **Tenancy and identity.** Row tenancy pivoted toward framework-owned discriminators
  and generated Postgres RLS; identity grew into a global-identity + organization +
  fenced-membership model with two-phase auth.
- **A failure-mode lens.** Most recently, that whole history was turned into a threat
  model: the [Model-Driven Failure Modes](model-driven-failure-modes.md) catalogue
  generalises 4GL/CASE/MDE history into named risks Dazzle scores itself against. The
  dated gaps below are the *empirical instances*; the catalogue is the generalisation.

## The archive

These pages are **searchable but deliberately kept out of the main navigation**. They
are reachable from here and from search — not from the learning path.

### Framework-gap analyses (autonomous-improvement cycles, April 2026)

Synthesised output of the `/ux-cycle` → `/improve` loop, in cycle order:

- [Component Menagerie Roadmap](../history/framework-gaps/2026-04-15-component-menagerie-roadmap.md)
- [Error-Page Navigation Dead-End](../history/framework-gaps/2026-04-15-error-page-navigation-dead-end.md)
- [Persona-Unaware Affordances](../history/framework-gaps/2026-04-15-persona-unaware-affordances.md)
- [Resumed /ux-cycle Arc — Closing Retrospective (Cycles 220–235)](../history/framework-gaps/2026-04-15-resumed-arc-retrospective.md)
- [Silent Form Submit](../history/framework-gaps/2026-04-15-silent-form-submit.md)
- [Widget Selection for Ref and Typed Form Fields](../history/framework-gaps/2026-04-15-widget-selection-gap.md)
- [Workspace Region Naming Drift](../history/framework-gaps/2026-04-15-workspace-region-naming-drift.md)
- [DaisyUI Residuals in Uncontracted Templates](../history/framework-gaps/2026-04-19-daisyui-residuals-in-uncontracted-templates.md)
- [Trial Harness Maturation](../history/framework-gaps/2026-04-19-trial-harness-maturation.md)
- [Attention-Tier Taxonomy Drift Across Workspace Regions](../history/framework-gaps/2026-04-20-attention-tier-taxonomy-drift.md)
- [External Resource Integrity Gap](../history/framework-gaps/2026-04-20-external-resource-integrity.md)
- [PR #600 Dormant Alpine Primitives](../history/framework-gaps/2026-04-20-pr600-dormant-alpine-primitives.md)
- [Row-Click Keyboard Affordance Gap](../history/framework-gaps/2026-04-20-row-click-keyboard-affordance-gap.md)
- [Template-Ship-Without-Wiring Gap](../history/framework-gaps/2026-04-20-template-ship-without-wiring.md)
- [Silent-Drift Classes in the `/ux-cycle` Loop](../history/framework-gaps/2026-04-20-ux-cycle-silent-drift-classes.md)
- [IR Policy-Field Drift: DSL Vocabulary Ahead of Runtime](../history/framework-gaps/2026-04-21-ir-policy-field-drift.md)

### Snapshots, briefings & retrospectives

- [Jinja2 Retirement — Postmortem & Hypothesis Evaluation (2026-05-12)](../history/2026-05-12-jinja2-retirement-postmortem.md)
- [Framework Maturity Assessment — 2026-04-15](../history/framework-maturity-2026-04-15.md)
- [Frontier Agent Briefing — v0.55.47](../history/frontier-agent-briefing-v0.55.47.md)
- [/ux-cycle Session Retrospective — 2026-04-21](../history/ux-session-retro-2026-04-21.md)
- [v1.0.3 Anchor Backfill](../history/v1.0.3-anchor-backfill.md)
