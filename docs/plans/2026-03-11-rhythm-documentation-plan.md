# Rhythm Documentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Document the rhythm/phase/scene construct with a conceptual guide, a reference page, and README updates.

**Architecture:** Three files — a teaching guide (`docs/guides/rhythms.md`) that explains the paradigm from scratch with worked examples, a standard reference page (`docs/reference/rhythms.md`) matching existing reference template style, and surgical README.md edits to surface the new construct.

**Tech Stack:** Markdown only. No code changes.

---

### Task 1: Create Conceptual Guide

**Files:**
- Create: `docs/guides/rhythms.md`

**Context:**

The guide teaches a foreign paradigm — longitudinal persona journey evaluation. Most developers think in CRUD screens, not persona journeys over time. The guide must explain WHY rhythms exist, HOW they relate to stories and processes, and WHAT the structural/semantic split means.

Use the education domain example from the design doc (course enrollment → module completion → credential). Build up DSL incrementally, not as a finished block.

Match the tone of existing guides (e.g., `docs/guides/operations.md`) — direct, practical, no fluff.

**Step 1: Write the guide**

Create `docs/guides/rhythms.md` with this structure and content:

```markdown
# Rhythms: Longitudinal UX Evaluation

## The Problem

You've built an app with a dozen surfaces, four personas, and thirty stories. Every story passes. Every surface renders. But can a new user actually get from signup to their first meaningful outcome?

Stories test atomic interactions — "user submits form, record is created." Processes model multi-actor state machines — "student submits, teacher grades, student views result." Neither asks the longitudinal question: does this persona's journey through the app make sense over time?

A new user doesn't just "enroll in a course." They discover courses, enroll, engage with content across weeks, and eventually earn a credential. Each step works in isolation; the question is whether the journey holds together.

## What Rhythms Are

A **rhythm** is a journey map for a single persona through your app, organized into temporal phases. It expresses the natural cadence of how someone uses the system over time.

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "first 30 days"

  phase discovery:
    scene browse_catalog "Browse Available Courses":
      on: course_list
      action: filter, browse
      expects: "visible_results"

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

Three constructs, nested:

- **Rhythm** — the journey. Bound to one persona. Has a cadence hint and one or more phases.
- **Phase** — a stage in the journey (discovery, engagement, mastery). Groups related scenes.
- **Scene** — a single evaluable action. Bound to a specific surface. This is what gets checked.

## Building a Rhythm Step by Step

Start with the persona and the question you want to answer:

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "first 30 days"
```

`persona:` is a hard reference — it must match an existing persona definition. The linker validates this at compile time. `cadence:` is a free-form string — the framework doesn't interpret it. An AI agent uses it to understand temporal context when evaluating or proposing changes.

Add a phase:

```dsl
  phase discovery:
```

Phase names must be unique within the rhythm. They represent journey stages, not calendar dates. "Discovery" could mean "day 1" for a SaaS onboarding or "September" for an academic app — the DSL doesn't prescribe this.

Add scenes to the phase:

```dsl
    scene browse_catalog "Browse Available Courses":
      on: course_list
      action: filter, browse
      expects: "visible_results"
```

- `on:` is a hard reference — must match an existing surface. The linker validates this.
- `action:` is free-form — describes what the persona does. Not an enum. Domain-specific.
- `expects:` is free-form — the expected outcome. Agents interpret this during evaluation.

Optionally link to an entity or story:

```dsl
    scene enroll "Enroll in First Course":
      on: course_detail
      action: submit
      entity: Enrollment
      expects: "enrollment_confirmed"
      story: ST-005
```

- `entity:` if present, must match an existing entity. Validated at compile time.
- `story:` if present, must match an existing story. Bridges rhythms and stories — "this scene exercises this story."

## The Structural/Semantic Split

This is the key design principle. Some properties are **structural** — validated deterministically at compile time:

| Property | Validated Against |
|----------|-------------------|
| `persona:` | Must match existing persona |
| `on:` | Must match existing surface |
| `entity:` | Must match existing entity (if present) |
| `story:` | Must match existing story (if present) |

Others are **semantic** — free-form strings that agents interpret per domain:

| Property | Purpose |
|----------|---------|
| `cadence:` | Temporal frequency hint ("quarterly", "first 30 days", "academic year") |
| `action:` | What the persona does ("filter, browse", "submit", "review") |
| `expects:` | Expected outcome ("visible_results", "enrollment_confirmed") |

The DSL captures structure deterministically. Agents add temporal and domain-specific meaning. This means:

- Compilation is always deterministic — no LLM involved in parsing or linking
- The same rhythm DSL works across domains — an agent specializes "quarterly" to mean April–March for accounting or September–September for education
- Validation catches real errors (referencing a surface that doesn't exist) without false positives on domain-specific language

## When to Use What

| Question | Construct | Why |
|----------|-----------|-----|
| "Does submitting this form create a record?" | **Story** | Atomic interaction, one step, one outcome |
| "When an order is confirmed, does payment → fulfillment → notification happen?" | **Process** | Multi-actor state machine with handoffs and compensations |
| "Can a new user get from signup to their first meaningful outcome?" | **Rhythm** | Single persona, multiple surfaces, temporal progression |
| "Do all personas have complete journeys through the app?" | **Rhythm coverage** | Cross-cutting gap analysis |

**Rules of thumb:**

- If it involves one persona acting on one surface → **story**
- If it involves handoffs between personas (student submits → teacher grades) → **process**
- If it follows one persona through multiple surfaces over time → **rhythm**
- Stories and rhythms can coexist — a scene's `story:` property bridges them

## Using MCP Tools

Most users won't hand-write rhythm DSL. The MCP agent generates it from natural language:

**Generate a rhythm:**
```
"Generate an onboarding rhythm for new users"
→ rhythm propose (analyzes surfaces + entities, generates complete rhythm DSL)
```

**Check a rhythm for gaps:**
```
"Are there any issues with the onboarding rhythm?"
→ rhythm evaluate (static analysis: surface existence, entity coverage, navigation coherence)
```

**Find missing rhythms:**
```
"Which personas don't have rhythms yet?"
→ rhythm coverage (persona/surface coverage matrix, highlights gaps)
```

**Inspect a rhythm:**
```
"Show me the onboarding rhythm"
→ rhythm get (full rhythm detail as JSON)
```

The `propose` operation is the primary interface. It translates natural language intent into correct DSL — resolving which surfaces a persona would naturally use, grouping them into phases, and emitting valid DSL with explicit surface bindings.

## Evaluation: What Gets Checked

Rhythm evaluation (v1) is static analysis against the parsed AppSpec. No running app required.

Four checks:

1. **Surface existence** — do all `on:` references point to real surfaces?
2. **Entity coverage** — if a scene references an entity, does the bound surface actually use that entity?
3. **Navigation coherence** — can the persona navigate between surfaces in scene order? (Uses workspace/experience definitions)
4. **Phase progression** — do later phases reference data that earlier phases would create?

The output is a structured report: pass/fail per check, with specific gaps identified.

A future v2 will add agent walkthrough — an LLM agent navigating the running app as the persona, attempting each scene in phase order. Not yet implemented.

## Full Example

A multi-phase rhythm for an accounting app:

```dsl
rhythm quarterly_close "Quarterly Close Process":
  persona: accountant
  cadence: "quarterly"

  phase preparation:
    scene review_outstanding "Review Outstanding Invoices":
      on: invoice_list
      action: filter, browse
      expects: "all_invoices_visible"

    scene reconcile_accounts "Reconcile Bank Accounts":
      on: reconciliation_surface
      action: submit
      entity: Reconciliation
      expects: "accounts_balanced"

  phase execution:
    scene generate_reports "Generate Financial Reports":
      on: report_builder
      action: submit
      entity: FinancialReport
      expects: "reports_generated"

    scene review_pnl "Review Profit & Loss":
      on: pnl_dashboard
      action: browse
      expects: "pnl_accurate"

  phase completion:
    scene submit_filing "Submit Regulatory Filing":
      on: filing_surface
      action: submit
      entity: RegulatoryFiling
      expects: "filing_submitted"
      story: ST-040
```

This rhythm answers: "Can an accountant complete a full quarterly close using this app?" Static evaluation checks that every surface exists, every entity is used by its bound surface, and the persona can navigate between them.
```

**Step 2: Verify no broken links**

Check that the guide doesn't reference files that don't exist:

Run: `ls docs/reference/stories.md docs/reference/processes.md docs/reference/ux.md docs/reference/surfaces.md`
Expected: All four files exist.

**Step 3: Commit**

```bash
git add docs/guides/rhythms.md
git commit -m "docs: add rhythm conceptual guide"
```

---

### Task 2: Create Reference Page

**Files:**
- Create: `docs/reference/rhythms.md`

**Context:**

Match the exact style of `docs/reference/stories.md` and `docs/reference/processes.md`. This is NOT auto-generated (no TOML KB entries for rhythm yet), so omit the auto-generated banner. Keep it terse — syntax lookup, not teaching.

**Step 1: Write the reference page**

Create `docs/reference/rhythms.md` with this content:

```markdown
# Rhythms

Rhythms capture longitudinal persona journeys through the app, organized into temporal phases containing scenes — evaluable actions on specific surfaces. They answer "can this persona complete their journey over time?" rather than testing atomic interactions (stories) or multi-actor state machines (processes).

For a full introduction to the rhythm paradigm, see the [Rhythm Guide](../guides/rhythms.md).

---

## Rhythm

A longitudinal journey map for a single persona through the app. Organized into temporal phases, each containing scenes. Every rhythm is bound to exactly one persona.

Workflow: propose → evaluate → coverage → get → list

### Syntax

```dsl
rhythm <name> "<Title>":
  persona: <persona_id>
  [cadence: "<temporal_hint>"]

  phase <phase_name>:
    scene <scene_name> "<Scene Title>":
      on: <surface_name>
      [action: <verb1>[, <verb2>, ...]]
      [entity: <EntityName>]
      [expects: "<expected_outcome>"]
      [story: <story_id>]

    [scene ...]

  [phase ...]
```

### Properties

| Property | Level | Type | Validated? | Purpose |
|----------|-------|------|-----------|---------|
| `persona:` | rhythm | identifier | Yes — must reference existing persona | Who takes this journey |
| `cadence:` | rhythm | quoted string | No — agent-interpreted | Temporal frequency hint |
| `on:` | scene | identifier | Yes — must reference existing surface | Which surface this scene exercises |
| `action:` | scene | identifier(s) | No — agent-interpreted | What the persona does |
| `entity:` | scene | identifier | Yes if present — must reference existing entity | What data is involved |
| `expects:` | scene | quoted string | No — agent-interpreted | Expected outcome assertion |
| `story:` | scene | identifier | Yes if present — must reference existing story | Link to atomic story |

### Validation Rules

The linker validates structural references at compile time:

1. `rhythm.persona` must match a defined persona
2. `scene.on` must match a defined surface
3. `scene.entity` (if present) must match a defined entity
4. `scene.story` (if present) must match a defined story
5. Phase names must be unique within the rhythm
6. Scene names must be unique within the rhythm (globally, not per-phase)

### Examples

**Minimal rhythm:**

```dsl
rhythm first_use "First Use":
  persona: new_user

  phase start:
    scene view_dashboard "View Dashboard":
      on: main_dashboard
      action: browse
      expects: "dashboard_loads"
```

**Multi-phase with entity and story references:**

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "first 30 days"

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
      story: ST-005

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

### Best Practices

- One persona per rhythm — use processes for multi-actor handoffs
- Keep phases abstract (discovery, engagement, mastery) — agents specialize to domain calendars
- Use `story:` to bridge rhythms and stories where they overlap
- Use `rhythm coverage` to find personas without rhythms and surfaces without scenes
- Let the MCP `propose` operation generate rhythms — it analyzes your app's surfaces and entities

**Related:** Stories, Processes, Personas, Surfaces (see docs/reference/)

---
```

**Step 2: Commit**

```bash
git add docs/reference/rhythms.md
git commit -m "docs: add rhythm reference page"
```

---

### Task 3: Update Reference Index

**Files:**
- Modify: `docs/reference/index.md:16` (after Stories row)

**Context:**

The reference index is auto-generated by `docs_gen.py`, but since rhythm has no TOML KB entry yet, add the row manually. Place it after Stories (line 16) since rhythms are the temporal companion to stories.

**Step 1: Add rhythm row**

After the Stories row in `docs/reference/index.md`, add:

```markdown
| [Rhythms](rhythms.md) | Rhythms capture longitudinal persona journeys through the app, organized into temporal phases containing scenes — evaluable actions on specific surfaces. |
```

**Step 2: Commit**

```bash
git add docs/reference/index.md
git commit -m "docs: add rhythm to reference index"
```

---

### Task 4: Update README.md

**Files:**
- Modify: `README.md:133` (Feature Highlights table, after Stories row)
- Modify: `README.md:178-180` (MCP "Test and Verify" table)
- Modify: `README.md:495` (Documentation section)

**Context:**

Three surgical edits. The Feature Highlights table has `<!-- BEGIN FEATURE TABLE -->` / `<!-- END FEATURE TABLE -->` markers. The MCP tables are in "The MCP Tooling Pipeline" section. The Documentation section is near the bottom.

**Step 1: Add Feature Highlights row**

After the Stories row (line 133), add:

```markdown
| [Rhythms](docs/guides/rhythms.md) | Rhythms capture longitudinal persona journeys organized into temporal phases containing scenes — evaluable actions on specific surfaces. Use `rhythm propose` to generate from natural language. |
```

**Step 2: Add MCP tool row**

In the "2. Test and Verify" table (after `demo_data` row, around line 180), add:

```markdown
| `rhythm` | propose, evaluate, coverage, get, list | Longitudinal persona journey maps — propose rhythms from natural language, evaluate surface/entity coverage, find persona gaps |
```

**Step 3: Add Documentation bullet**

In the Documentation section (around line 495), after the Getting Started bullet, add:

```markdown
- **[Rhythm Guide](docs/guides/rhythms.md)** — understanding longitudinal persona journey evaluation
```

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add rhythm to README feature table, MCP tools, and docs section"
```

---

### Task 5: Quality Check and Push

**Step 1: Verify all links resolve**

Run: `grep -r 'rhythms.md' docs/ README.md`
Expected: Shows links from README, index.md, and the guide itself. No broken references.

**Step 2: Check no lint issues**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean (docs-only changes shouldn't affect Python lint, but verify).

**Step 3: Run tests to confirm nothing broke**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All tests pass.

**Step 4: Push**

```bash
git push origin main
```
