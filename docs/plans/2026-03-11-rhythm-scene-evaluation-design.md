# Rhythm & Scene: Longitudinal UX Evaluation

**Issue**: #444
**Date**: 2026-03-11
**Status**: Design approved, pending implementation

## Problem

Dazzle evaluates UX through atomic stories (one interaction, one outcome) and discovery missions (broad capability scanning). Neither captures the longitudinal question: "Can a persona complete their journey through this app over time?"

A new user doesn't just "enroll in a course" — they discover courses, enroll, engage with content across weeks, and eventually earn a credential. Evaluating each step in isolation misses the journey arc.

## Core Concepts

### Rhythm

A **rhythm** is a longitudinal journey map for a single persona through the app, organized into temporal phases. It expresses the natural cadence of how a persona uses the system over time.

Rhythms are abstract — they define journey structure without hardcoded dates or schedules. An AI agent specializes the abstract rhythm to a domain-specific context:

- Cyfuture (accounting): maps phases to UK annual regulatory calendar (Apr–Mar)
- Aegismark (education): maps phases to academic calendar (Sept–Sept)
- A SaaS onboarding: maps phases to "days since signup"

The DSL captures structure deterministically. Agents interpret temporal semantics per domain.

### Scene

A **scene** is a single persona action within a rhythm phase, bound to a specific surface. Scenes are the evaluable units — each one asserts "this persona can do this thing on this surface."

### Phase

A **phase** groups scenes in temporal order within a rhythm. Phases represent journey stages (discovery, engagement, mastery) without prescribing calendar dates.

## DSL Syntax

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "quarterly"

  phase discovery:
    scene browse_catalog "Browse Available Courses":
      on: course_list
      action: filter, browse
      expects: "visible_results"

    scene enroll "Enroll in First Course":
      on: course_detail
      action: submit
      entity: Enrollment
      expects: "enrollment_confirmed"

  phase engagement:
    scene complete_module "Complete First Module":
      on: module_view
      action: submit
      entity: ModuleCompletion
      expects: "progress_recorded"

  phase mastery:
    scene view_progress "Check Progress":
      on: progress_dashboard
      action: browse
      expects: "credential_visible"
```

### Keywords

| Keyword | Level | Purpose |
|---------|-------|---------|
| `rhythm` | Top-level | Declares a rhythm construct |
| `phase` | Within rhythm | Groups scenes into temporal stages |
| `scene` | Within phase | Declares a persona action on a surface |

### Properties

| Property | On | Type | Validated? | Purpose |
|----------|----|------|-----------|---------|
| `persona:` | rhythm | identifier | Yes — must reference existing persona | Who takes this journey |
| `cadence:` | rhythm | quoted string | No — agent-interpreted | Temporal frequency hint |
| `on:` | scene | identifier | Yes — must reference existing surface | Which surface this scene exercises |
| `action:` | scene | identifier(s) | No — agent-interpreted, evaluator infers | What the persona does |
| `entity:` | scene | identifier | Yes if present — must reference existing entity | What data is involved |
| `expects:` | scene | quoted string | No — agent-interpreted | Expected outcome assertion |
| `story:` | scene | identifier | Yes if present — must reference existing story | Optional link to atomic story |

### Validation Split

**Structural references** (deterministic, compile-time):
- `persona`, `on`, `entity`, `story` — must reference existing constructs
- Phase names unique within rhythm
- Scene names unique within rhythm (global, not per-phase)

**Semantic hints** (agent-interpreted, not validated):
- `cadence`, `action`, `expects` — free strings, domain-specific

This split ensures deterministic compilation while giving agents freedom to express domain-specific concepts.

## IR Types

```python
# src/dazzle/core/ir/rhythm.py

class SceneSpec(BaseModel):
    name: str
    title: str | None = None
    surface: str                # maps to `on:` keyword
    actions: list[str] = []     # free-form, agent-interpreted
    entity: str | None = None
    expects: str | None = None  # free-form, agent-interpreted
    story: str | None = None    # optional link to existing story
    source: SourceLocation | None = None
    model_config = ConfigDict(frozen=True)

class PhaseSpec(BaseModel):
    name: str
    scenes: list[SceneSpec] = []
    source: SourceLocation | None = None
    model_config = ConfigDict(frozen=True)

class RhythmSpec(BaseModel):
    name: str
    title: str | None = None
    persona: str
    cadence: str | None = None  # free-form, agent-interpreted
    phases: list[PhaseSpec] = []
    source: SourceLocation | None = None
    model_config = ConfigDict(frozen=True)
```

## Linker Validation

The linker validates structural references only:

1. `rhythm.persona` must match a defined `PersonaSpec.id`
2. `scene.surface` (the `on:` value) must match a defined surface name
3. `scene.entity` if present, must match a defined entity name
4. `scene.story` if present, must match a defined story name
5. Phase names unique within rhythm
6. Scene names unique within rhythm (globally, not per-phase)

Errors reported with source locations, consistent with existing constructs.

## Relationship to Existing Constructs

### Stories: Complement, Converge Organically

Rhythms do not replace stories. They serve different purposes:

- **Stories** = atomic invariants (system guarantees, regression tests)
- **Rhythms** = longitudinal journey maps (UX completeness, temporal evaluation)

Some stories describe interactions that are also rhythm scenes. Over time, agents will naturally identify this overlap via coverage analysis and recommend retiring redundant stories. No planned deprecation — convergence is organic.

A scene's optional `story:` property bridges the two: "this scene exercises story X."

### Processes: Clear Boundary

- **Rhythms** = single-persona journeys through the app over time
- **Processes** = multi-actor state machines with transitions and triggers

If an interaction involves handoffs between personas (student submits → teacher grades → student views), that's a process. If it follows one persona's arc through the app, that's a rhythm.

### Personas: Required Input

Every rhythm requires a persona. The persona provides the "who" that gives the journey meaning. Rhythms without personas are structural nonsense.

## MCP Operations

Tool name: `rhythm`

| Operation | Purpose | Key Input | Output |
|-----------|---------|-----------|--------|
| `propose` | Generate rhythm from app analysis | persona name, optional natural language intent | Proposed rhythm DSL text |
| `evaluate` | Static analysis of rhythm completeness | rhythm name | Gap report: surface existence, action support, navigation coherence |
| `coverage` | Persona/surface coverage matrix | none | Which personas have rhythms, which surfaces are exercised, gaps |
| `get` | Inspect a specific rhythm | rhythm name | Full rhythm detail as JSON |
| `list` | List all rhythms in project | none | Summary of all rhythms |

### `propose` Operation

The most important operation. Accepts natural language intent and resolves it to correct DSL:

- "Generate an onboarding rhythm for new users" → analyzes surfaces + entities, generates complete rhythm
- "Add a weekly check-in to the onboarding rhythm" → modifies existing rhythm, adds scene to appropriate phase

Uses the KG + AppSpec to determine which surfaces a persona would naturally use, groups them into phases, and emits valid DSL with explicit surface bindings.

### `evaluate` Operation

Static analysis — deterministic, no runtime required:

1. **Surface completeness** — do all referenced surfaces exist?
2. **Entity coverage** — if a scene references an entity, does the surface use that entity?
3. **Navigation coherence** — can the persona navigate between surfaces in scene order? (Uses workspace/experience definitions)
4. **Phase progression** — do later phases reference data that earlier phases would create?

Output is a structured report: pass/fail per check, with specific gaps identified.

### `coverage` Operation

Cross-cutting analysis:

- Which personas have rhythms vs which don't?
- Which surfaces appear in rhythms vs which are unexercised?
- Which entities are referenced in scenes vs which are orphaned?

Highlights gaps to guide the agent toward proposing additional rhythms.

## Evaluation Architecture

### V1: Static (This Implementation)

Deterministic analysis against the parsed AppSpec. No running app required. Runs in pipeline and nightly.

### V2: Agent Walkthrough (Future)

Agent navigates the running app as the persona, attempting each scene in phase order. Records observations and blockers. Uses the existing agent framework (DazzleAgent, Observer, Executor, Transcript).

Not in scope for this implementation.

## Design Principle: Constructive MCP

MCP tools are constructive, not destructive. The agent acts as a translator and guardrail between the founder's intent and the DSL:

- `propose` is the primary interface — founders express intent in natural language, the agent emits correct DSL
- `evaluate` catches structural errors before they land in DSL files
- `coverage` shows gaps, prompting agent suggestions rather than founder guessing

There is no raw-edit operation. The agent proposes changes, the founder reviews the diff. This prevents founders from breaking their app by asking for the wrong construct.

Post-bootstrap ad-hoc requests ("add a weekly check-in") go through `propose`, which resolves ambiguity (is this a scene, a rhythm, a process, or a surface?) before touching DSL.

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `src/dazzle/core/ir/rhythm.py` | IR types: RhythmSpec, PhaseSpec, SceneSpec |
| `src/dazzle/core/dsl_parser_impl/rhythm.py` | Parser mixin: RhythmParserMixin |
| `src/dazzle/mcp/server/handlers/rhythm.py` | MCP handler: propose, evaluate, coverage, get, list |
| `tests/unit/test_rhythm_parser.py` | Parser tests |
| `tests/unit/test_rhythm_linker.py` | Linker validation tests |
| `tests/unit/test_rhythm_evaluation.py` | Static evaluation tests |

### Modified Files

| File | Change |
|------|--------|
| `src/dazzle/core/lexer.py` | Add RHYTHM, PHASE, SCENE token types |
| `src/dazzle/core/ir/__init__.py` | Export rhythm types |
| `src/dazzle/core/ir/module.py` | Add `rhythms: list[RhythmSpec]` to ModuleFragment |
| `src/dazzle/core/ir/appspec.py` | Add `rhythms: list[RhythmSpec]` to AppSpec |
| `src/dazzle/core/dsl_parser_impl/__init__.py` | Add RhythmParserMixin to Parser class |
| `src/dazzle/core/linker_impl.py` | Add rhythm symbol registration + validation |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add rhythm tool schema |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Add rhythm handler dispatch |
| `docs/reference/grammar.md` | Add rhythm/phase/scene EBNF |

## Non-Goals

- Agent walkthrough (v2)
- Domain-specific calendar implementations
- Timing/scheduling syntax
- Multi-persona rhythms (use `process` for handoffs)
- Story deprecation or migration tooling
