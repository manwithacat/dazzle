---
id: bootstrap_pollution
name: Bootstrap / spec_analyze domain pollution
layer: inference
status: active
summary: >-
  Trusting bootstrap or analyze-spec / discover_entities as the primary path
  from a prose SPEC to DSL. LLMs invent chrome entities (Optional, Field,
  Display) and off-domain clarification questions. Prefer hand-author from
  the brief + knowledge concepts + validate loop; treat bootstrap as optional
  and untrusted (#1629 G4).
triggers_text:
  - "bootstrap"
  - "analyze-spec"
  - "analyze spec"
  - "discover entities"
  - "extract entities from"
  - "spec to dsl"
  - "generate entities from markdown"
triggers_code:
  - "spec_analyze"
  - "discover_entities"
  - "bootstrap"
refs:
  adrs: ["0002"]
  memories: []
  pr_review_agents: []
  kb_patterns: ["first_principles_demo", "demo_identity"]
  tests: ["tests/unit/mcp/test_spec_analyze_handlers.py"]
detectors: []
---

# Bootstrap / spec_analyze domain pollution

## The corpus prior

Agents default to **generate-then-fix**: feed SPEC → bootstrap / analyze-spec →
accept invented entities. Training data rewards full scaffolds from prose.
Markdown tables, field names, and UI chrome become fake domain types
(`Optional`, `Raise`, `Field`, `Display`). Offline hangs and unbounded
clarification questions are sibling failures.

## Wrong shape

```text
spec_analyze(discover_entities) on a clear spend brief
→ entities: Optional, Field, Display, Refund, Booking…
→ agent authors DSL around pollution
```

Worse than hand-authoring from the brief.

## Right shape

1. **Default path:** founder brief → **`dazzle domain extract`** / `domain(extract)`
   → AGENT_DOMAIN.md (agent audience) → `domain gaps` research → `domain promote`
   → knowledge concepts → hand-author DSL → validate.
2. Rank bootstrap **below** domain intermediate and validate loop.
3. If bootstrap is used: it should write/refresh AGENT_DOMAIN; treat
   `analysis.entities` as **untrusted draft**, not SSOT.
4. **Offline path (#1631):** domain extract uses chrome-safe offline noun mining;
   LLM `analyze-spec` times out loud (90s) — never wait on bootstrap to ship.

## Why this matters here

#1629 A/B: MCP already wins on validate/knowledge; bootstrap **polluted** the
domain model. Agent cognition improves by **not calling** the polluting path
by default, not by waiting for perfect extraction.
