# Rhythm Documentation Design

**Issue**: Follow-up to #444
**Date**: 2026-03-11
**Status**: Design approved, pending implementation

## Problem

The rhythm/phase/scene construct is implemented but undocumented beyond design plans and grammar EBNF. The paradigm — longitudinal persona journey evaluation — is foreign to most developers. Without explanation, users won't understand why rhythms exist alongside stories and processes, or how the structural/semantic validation split works.

## Deliverables

### 1. Conceptual Guide: `docs/guides/rhythms.md`

The primary teaching document. ~250-350 lines. Structured as:

1. **Opening hook** — Concrete problem: "You have 12 surfaces, 4 personas, 30 stories — can a new user actually get from signup to their first meaningful outcome?"

2. **The gap** — Stories test atomic interactions. Processes model multi-actor state machines. Neither captures a single persona's journey through the app over time. Diagram showing coverage boundaries of each construct.

3. **Core concepts via worked example** — Education domain (course enrollment → module completion → credential). Introduce rhythm, phase, and scene incrementally, building up DSL step by step.

4. **The structural/semantic split** — `persona`, `on`, `entity`, `story` are compile-time validated. `cadence`, `action`, `expects` are free-form strings — agents interpret per domain. The DSL captures structure; agents add temporal meaning.

5. **When to use what** — Decision table: stories vs processes vs rhythms. Direct answer to "why not just stories?"

6. **MCP workflow** — `rhythm propose` generates from natural language. `rhythm evaluate` runs static checks. `rhythm coverage` finds gaps. Founders don't hand-write rhythm DSL — the agent translates intent.

### 2. Reference Page: `docs/reference/rhythms.md`

Standard reference template matching existing pages. ~120-150 lines:

- Overview paragraph
- Full DSL syntax with annotations
- Properties table (keyword, level, type, validated?, purpose)
- Validation rules (what the linker checks)
- 2-3 complete examples (minimal, full-featured, multi-phase)
- Related constructs (stories, processes, personas, surfaces)

### 3. README.md Updates

Surgical changes:

1. **Feature table** — Add row after Stories linking to the guide
2. **MCP "Test and Verify" table** — Add `rhythm` tool row with 5 operations
3. **Documentation section** — Add bullet linking to guide

## Non-Goals

- Auto-generation from TOML KB (rhythm KB entries don't exist yet — manual doc is appropriate for a new construct)
- Tutorial/getting-started changes (rhythm is intermediate-to-advanced)
- Example project modifications (no example project uses rhythms yet)
