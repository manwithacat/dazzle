# Compliance Compiler — Design Background

These documents were produced during the AegisMark proof-of-concept that led to this Dazzle feature branch. They provide the full design context, architectural decisions, and implementation plan.

## Documents

### [design-spec.md](design-spec.md)
The full design specification (883 lines). Covers:
- Vision and architecture overview
- Framework taxonomy format (YAML)
- AuditSpec IR format (JSON)
- Document specification layer
- AI agent architecture (per-document dispatch)
- Human-in-the-loop workflow (review.yaml, tier 2/3 gaps)
- Compliance graph (document dependencies, DSL→app surface links)
- Brand identity pack (brandspec.yaml for print rendering)
- DSL evidence baseline (what AegisMark already had)
- Implementation approach and success criteria

### [implementation-plan.md](implementation-plan.md)
The task-by-task implementation plan (15 tasks). Covers:
- Framework taxonomy loader (TDD, dataclasses)
- ISO 27001 full taxonomy authoring
- DSL evidence extractor (MCP-first, anchored entity search)
- AuditSpec compiler
- WeasyPrint renderer
- Document spec loader and slicer
- Citation validator
- Coordinator module and /audit skill
- End-to-end generation test

### [../compliance-compiler.md](../compliance-compiler.md)
The Dazzle-specific proposal summarising what's in this branch and suggested next steps.

## Design Process

The design was produced through collaborative brainstorming:
1. Explored existing DSL compliance metadata (112 classify, 53 permit/scope, 88 transitions, 49 processes)
2. Identified the compiler pipeline architecture (taxonomy → evidence → IR → AI agents → documents)
3. Designed framework-agnostic YAML taxonomy format
4. Designed AuditSpec IR with per-control evidence/gap tracking
5. Designed document specification layer separating "what evidence" from "how to present"
6. Designed compliance graph for document dependencies and app surface links
7. Spec reviewed (2 rounds) and plan reviewed (2 rounds) before implementation
8. 15-task implementation executed with subagent-driven development

## AegisMark Proof-of-Concept Results

- 21 documents generated (~166 pages, 473 KB markdown, 1.6 MB PDF)
- 93 ISO 27001 controls assessed (37 evidenced, 54 planned, 2 excluded)
- 110 human review markers for items needing manual input
- 0 citation validation errors
- Full branded PDF archive: 1.9 MB zip
