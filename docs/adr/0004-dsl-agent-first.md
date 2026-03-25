# ADR-0004: DSL Optimized for AI Agents

**Status:** Accepted
**Date:** 2026-03-20

## Context

Every DSL design involves tradeoffs between competing goals:

- **Human ergonomics** — brevity, implicit defaults, syntactic sugar, forgiving parsers
- **Formal correctness** — explicit structure, unambiguous grammar, static verifiability
- **AI agent legibility** — predictable patterns, auditable constraints, minimal ambiguity

The initial Dazzle DSL leaned toward ergonomics: optional keywords, flexible indentation, implicit defaults, and shortcuts. As the user base evolved toward institutional and regulated domains (finserv, education), and as AI agents became the primary authors and readers of DSL files, this tradeoff needed revisiting.

The central question: **who is the primary consumer of Dazzle DSL, and what do they need?**

Observation: in practice, AI agents write the majority of DSL. Human developers review and occasionally edit it. The DSL is not typed by hand at high frequency — it is generated, validated, and reasoned about.

## Decision

**DSL is primarily consumed by AI agents. Design for precision and formal correctness over human ergonomics.**

Specific implications:

- **Explicit over implicit** — required fields stay required; defaults are declared, not assumed
- **Auditability over brevity** — verbose constructs that make intent clear are preferred over terse shortcuts
- **Formal validation** — scope rules compile to a predicate algebra and are statically validated against the FK graph; ambiguous constructs are rejected rather than coerced
- **Stable grammar** — grammar changes are documented formally in `docs/reference/grammar.md`; no ad-hoc extensions
- **No syntactic sugar** — convenience shorthands that expand to multiple meanings are not added

This applies to all DSL constructs: entities, surfaces, scopes, permissions, ledgers, processes, stories, rhythms, and all future constructs.

## Consequences

### Positive

- AI agents produce fewer invalid DSL files — the grammar is learnable and consistent
- Static validation catches scope rule errors at `dazzle validate` time rather than at runtime
- DSL files are auditable artifacts — reviewers can reason about correctness without running the app
- Regulated domains (finserv, education) can rely on formal guarantees from the DSL layer

### Negative

- More verbose DSL for simple cases — a basic CRUD surface requires more explicit declaration than comparable frameworks
- Newcomers writing DSL by hand face a steeper initial learning curve
- Grammar changes require updating `grammar.md`, parser, IR, and tests — no fast informal extensions

### Neutral

- Human readability remains a secondary goal, not abandoned — clear naming and structure are still valued
- The MCP `dsl` tool exposes validation and inspection so agents can verify their output programmatically

## Alternatives Considered

### 1. Human Readability as Primary Goal

Design DSL to be writable and readable by non-technical users with minimal training.

**Rejected:** The actual user base is technical developers working with AI agents. Optimising for non-technical users would degrade agent reliability without serving a real constituency.

### 2. Syntactic Sugar for Common Patterns

Add shorthand forms that expand to verbose equivalents (e.g., implicit `id: uuid pk` on every entity).

**Rejected:** Implicit expansion increases the surface area agents must understand. Every implicit rule is a potential source of agent confusion or hallucinated DSL.

### 3. Convenience at Cost of Clarity

Accept ambiguous grammar where the parser can resolve intent heuristically.

**Rejected:** Heuristic resolution is unpredictable. Agents cannot reliably generate DSL that will parse consistently if the parser applies implicit rules. Unambiguous grammar is a hard requirement.

## Implementation

The predicate algebra for scope rules (ADR companion: scope block design) is the clearest instance of this principle in production. Scope rules are validated against the FK graph at `dazzle validate` time; no ambiguous or unverifiable rule is accepted.
