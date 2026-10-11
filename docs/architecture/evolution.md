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

The dated framework-gap analyses (April 2026 `/ux-cycle` → `/improve` output) and the
snapshots, briefings and retrospectives that used to be linked here were moved out of the
working tree under ADR-0057. They live under `archive/docs-history/` on the `archive`
branch, alongside the superpowers plans and specs and the research notes.
