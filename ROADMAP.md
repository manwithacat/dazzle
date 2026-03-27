# DAZZLE Development Roadmap

**Last Updated**: 2026-03-24
**Current Version**: v0.49.11

For past releases, see [CHANGELOG.md](CHANGELOG.md).

---

## How Software Evolves Now

Dazzle does not have a quarterly roadmap. It has a growth model.

Traditional software roadmaps assume human developers who plan, estimate, and execute in sprints. That model is already obsolete. The agents building with Dazzle today — and the agents that will build with it in 2028, 2030, and beyond — don't work in sprints. They work in continuous loops: build, encounter friction, adapt. The framework must evolve the same way.

This document describes Dazzle's growth philosophy: how it changes, what constrains that change, and how we prevent the most dangerous failure mode in agent-driven development — uncontrolled proliferation.

---

## The Biological Model

Software frameworks are biological systems. They grow. They respond to environmental pressure. They can develop pathologies. The language of biology is more honest about what happens to long-lived codebases than the language of project management.

### Growth Mechanism: Domain Pressure

Dazzle grows when agents build real applications and encounter gaps — constructs the DSL can't express, patterns the runtime doesn't support, compliance controls with no evidence mapping. Each new domain (finserv, edtech, healthcare, logistics) stresses a different surface of the framework. The stress produces structured friction reports: issues, gap analyses, sentinel findings.

This is not a deficiency. It is the mechanism. A framework that doesn't grow in response to real usage is either complete (unlikely) or dead (common). The question is not whether Dazzle grows, but whether it grows well.

### Boundaries: The Anti-Turing Constraint

The single most important property of the Dazzle DSL is that it is **not Turing-complete**. You cannot write arbitrary computation in it. This is not a limitation — it is the immune system.

Because the DSL is anti-Turing:
- Every application can be **statically validated** in finite time
- Every access rule can be **mechanically verified** against every role
- Every compliance-relevant construct can be **automatically mapped** to framework controls
- The entire security surface is **enumerable** — there are no dark corners

Any proposed extension to the DSL must preserve these properties. This is a mechanical check, not a judgment call. An extension that makes the DSL Turing-complete — or that introduces constructs whose behavior cannot be statically analyzed — is rejected regardless of how useful it would be for one application. This is the hard boundary that prevents cancer.

### Immune System: Separation of Proposer and Reviewer

The most dangerous failure mode in agent-driven evolution is **eager extension**. Every agent sees its current application's needs as universal. Without governance, the DSL becomes a superset of every app ever built on it — which is just a general-purpose language, defeating the purpose.

The governance mechanism:

1. **The agent that needs a feature does not approve it.** Proposals are reviewed by a separate agent (or human) with different incentives — framework coherence, not application completion.
2. **Every extension must serve multiple domains.** A construct that only makes sense for one application is a code smell. The DSL vocabulary should be domain-agnostic; domain-specific patterns belong in example apps and API packs.
3. **Removal is as important as addition.** When a construct is superseded by a better abstraction, the old construct is deleted — not deprecated, not shimmed. The DSL must stay small enough for an agent to hold in context.

### Homeostasis: The Convergence Hypothesis

We believe the DSL will converge. There is a finite vocabulary sufficient to describe the structure of SaaS applications: data models, access control, state machines, workflows, approval chains, audit trails, integrations, ledgers, graphs. Each domain stress-tests a different combination, but the underlying constructs are shared.

The evidence for convergence: Dazzle currently has ~30 top-level DSL constructs. A 39-entity accountancy platform, a medical prescribing system, an education assessment tool, and a field operations hub all use the same constructs in different combinations. New constructs are added less frequently with each release. The vocabulary is stabilizing.

When a domain genuinely requires a new construct (not a new combination of existing ones), that is a significant event worth careful attention. Most apparent gaps are really missing patterns, not missing constructs.

---

## Autonomy Phases

Dazzle's development is progressing through increasing levels of agent autonomy. These are not planned milestones — they are descriptions of how the feedback loop between agents and framework is tightening over time.

### Phase 1: Guided Construction (current)

Agents build applications within the DSL's existing vocabulary. When they hit a gap, a human files an issue, designs the solution, and implements it. The agent is a consumer of the framework. The feedback loop runs through human cognition.

**What exists today:** 26 MCP tools, ~30 DSL constructs, structured gap reporting via `discovery`, `sentinel`, and `compliance gaps`. The infrastructure for observing friction is in place; the loop back to framework evolution is human-mediated.

### Phase 2: Observed Friction

Agents instrument their own experience. When they encounter a gap — a construct they wish existed, an evidence mapping they expected but didn't find, a pattern they had to work around — they log structured friction reports. A human or higher-order agent triages the friction log, identifies patterns across multiple applications, and decides which gaps warrant closing.

**What this requires:** A friction reporting format. Aggregation across projects. Pattern detection that distinguishes "this agent wanted a shortcut" from "this class of application cannot be expressed."

### Phase 3: Proposed Evolution

Agents don't just report friction — they propose solutions. "I needed to express an availability SLA but no construct exists. Here is a DSL sketch, here is how it maps to SOC 2 A1, here is the IR type." The proposal is structured enough to be reviewed but is not implemented — it is a spec waiting for approval.

**What this requires:** A proposal format that includes: the DSL syntax, the IR type, the evidence mapping, proof that the extension preserves static analyzability, and examples from at least two domains demonstrating the need is not application-specific.

### Phase 4: Supervised Self-Extension

Agents implement their own proposals — writing the parser mixin, IR type, evidence extractor, and tests — in an isolated worktree. A review gate validates the change before it merges. The framework grows, but every extension is auditable and reversible.

**What this requires:** The review gate. This is the hardest piece. It must verify: the DSL remains anti-Turing, the extension is domain-agnostic, the test coverage is sufficient, the compliance pipeline still works, and no existing application breaks. Most of these checks are mechanical. The judgment call — "is this construct worth its weight?" — may remain human for a long time.

### Phase 5: Equilibrium

The DSL vocabulary stabilizes. New applications mostly work within existing constructs. Extensions become rare and increasingly domain-specific — not new constructs, but new patterns composed from existing ones. The framework's growth rate asymptotically approaches zero. This is not stagnation; it is maturity.

---

## Current Focus Areas

### Compliance Pipeline Expansion

The compliance system (ISO 27001, SOC 2) demonstrates a key principle: the DSL's structure contains implicit compliance evidence. Expanding this to more frameworks (GDPR, HIPAA, PCI-DSS) and deepening the evidence mapping is high-leverage work that makes every Dazzle application more auditable without any per-app effort.

See issues [#666](https://github.com/manwithacat/dazzle/issues/666) (availability/processing integrity constructs) and [#667](https://github.com/manwithacat/dazzle/issues/667) (cross-framework metadata).

### Domain Stress-Testing

The most productive contributions are **example applications from complex, real-world domains** that push the DSL's boundaries. Each domain that doesn't fit cleanly generates friction. That friction, properly channeled, drives the framework forward.

Domains of particular interest:
- **Multi-tenant SaaS** — tenancy isolation, delegated admin, cross-tenant reporting
- **Regulated industries** — audit trails, approval workflows, separation of duty
- **Complex state machines** — many lifecycle states, conditional transitions, escalation
- **Graph-heavy domains** — social networks, supply chains, org hierarchies

### Runtime Hardening

Production deployments expose a different class of issue than development. Connection pool behavior, transaction isolation, event delivery guarantees, and deployment integrity verification are ongoing concerns. Each production incident teaches something about what the runtime must handle that the DSL cannot express.

---

## Contributing

The best way to contribute to Dazzle is to **build something with it** and tell us where it breaks.

1. Pick a domain you know well
2. Write the DSL (start with entities + surfaces)
3. Run `dazzle serve --local` and `dazzle compliance compile`
4. File issues for anything that doesn't work or can't be expressed
5. Submit your example as a PR to `examples/`

Each example app that exercises a new combination of constructs is a permanent regression test and a data point for the convergence hypothesis.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: https://manwithacat.github.io/dazzle/
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
