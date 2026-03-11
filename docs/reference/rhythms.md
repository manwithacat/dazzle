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
    [kind: <phase_kind>]
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
| `kind:` | phase | keyword | Yes if present — must be a valid phase kind | Phase lifecycle classification |
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
    kind: onboarding
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
    kind: active
    scene complete_module "Complete First Module":
      on: module_view
      action: submit
      entity: ModuleCompletion
      expects: "progress_recorded"

  phase mastery:
    kind: periodic
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

**Related:** [Stories](stories.md#story), [Processes](processes.md#process), [Personas](ux.md#persona), [Surfaces](surfaces.md)

---

## Phase Kinds

The optional `kind:` field on a phase classifies its role in the persona's lifecycle. This classification drives gap analysis, ambient detection, and evaluation strategy.

| Kind | Description |
|------|-------------|
| `onboarding` | First-time setup and orientation. Scenes in this phase cover initial account creation, configuration wizards, and first meaningful interactions. |
| `active` | Event-driven work. The persona reacts to triggers — incoming requests, notifications, or state changes — and takes action on them. |
| `periodic` | Recurring scheduled tasks. Activities the persona performs on a regular cadence — daily reviews, weekly reports, monthly reconciliations. |
| `ambient` | No explicit trigger; proactive system value. The system surfaces insights, recommendations, or background maintenance without the persona asking. |
| `offboarding` | Wind-down, handoff, and archival. Covers account deactivation, data export, responsibility transfer, and cleanup. |

When `kind:` is omitted, the IR stores `None` (unspecified). Unspecified phases are still valid but will not participate in kind-aware gap analysis.

### Example

```dsl
rhythm quarterly_review "Quarterly Review Cycle":
  persona: finance_manager
  cadence: "quarterly"

  phase preparation:
    kind: periodic
    scene pull_reports "Pull Financial Reports":
      on: report_builder
      action: generate
      entity: FinancialReport
      expects: "reports_generated"

  phase review:
    kind: active
    scene review_anomalies "Review Flagged Anomalies":
      on: anomaly_dashboard
      action: browse, resolve
      expects: "anomalies_addressed"

  phase insights:
    kind: ambient
    scene system_trends "View System-Generated Trends":
      on: trend_dashboard
      action: browse
      expects: "trends_visible"
```

---

## Gaps Analysis

The `rhythm gaps` MCP operation identifies missing or weak coverage in the persona journey. It combines static analysis of the AppSpec with evaluated scores from scene evaluation.

### Static Gaps

Static gaps are derived from the AppSpec without requiring any evaluation data:

| Gap Type | Description |
|----------|-------------|
| `capability` | A surface exists that no scene exercises. The persona has no defined path to reach it. |
| `unmapped` | A scene references an entity but has no `story:` link, so its behavioral contract is undefined. |
| `orphan` | A scene references a story that does not exist in the AppSpec. |
| `ambient` | A phase is marked `kind: ambient` but has no scenes. Ambient value was declared but not designed. |
| `unscored` | Scenes exist but have never been evaluated. No quality signal is available. |

### Evaluated Gaps

When scene evaluations have been submitted (see [Scene Evaluation](#scene-evaluation)), additional gaps are derived from scoring patterns:

- Low `arrival` scores suggest navigation or discovery problems.
- Low `orientation` scores suggest the surface does not communicate its purpose.
- Low `action` scores suggest the interaction is blocked or unclear.
- Low `completion` scores suggest the persona cannot finish the task.
- Low `confidence` scores suggest the persona is uncertain about the outcome.

### Severity Levels

Each gap is assigned a severity that determines its priority in the roadmap:

| Severity | Meaning |
|----------|---------|
| `blocking` | The persona journey is broken. A required surface is unreachable or a scene consistently fails. |
| `degraded` | The journey works but the experience is poor. Scores are below threshold in one or more dimensions. |
| `advisory` | An opportunity for improvement. Missing coverage that does not block the journey. |

### Roadmap Ordering

Gaps are returned in priority order: `blocking` first, then `degraded`, then `advisory`. Within each severity level, gaps are ordered by the number of affected scenes (descending).

---

## Lifecycle Operation

The `rhythm lifecycle` MCP operation reports where a project stands in the rhythm development workflow. It reads the current state of the AppSpec and stored evaluations, then returns a structured assessment. It is purely advisory — it never blocks or modifies anything.

### Steps

The lifecycle tracks 8 steps in order:

| Step | Description | Maturity Level |
|------|-------------|---------------|
| `model_domain` | Define entities, surfaces, and personas | `new_domain` |
| `write_stories` | Write stories for key interactions | `new_domain` |
| `write_rhythms` | Define rhythms with phases and scenes | `building` |
| `map_scenes_to_stories` | Link scenes to stories via `story:` | `building` |
| `build_from_stories` | Build surfaces and logic from story contracts | `building` |
| `evaluate_from_scenes` | Run scene evaluations and submit scores | `evaluating` |
| `find_gaps` | Analyze gaps from evaluation results | `evaluating` |
| `iterate` | Address gaps, re-evaluate, converge on quality | `mature` |

### Maturity Levels

The lifecycle assigns one of four maturity levels based on which steps are complete:

- **new_domain** — Domain modeling and story writing are in progress. No rhythms exist yet.
- **building** — Rhythms and scenes are defined. The app is being built from story contracts.
- **evaluating** — Scenes are being evaluated. Gaps are being identified and prioritized.
- **mature** — Evaluation cycles are producing consistently high scores. Gaps are advisory only.

### Usage

Call `rhythm lifecycle` to get the current step, maturity level, and a list of completed/pending steps. Use this to guide what to work on next.

---

## Scene Evaluation

The `rhythm evaluate` MCP operation with `action: submit_scores` records quality scores for individual scenes. Scores are produced by agents (automated or human) who exercise the scene and rate their experience across five dimensions.

### Dimensions

Each scene is scored on 5 dimensions, each rated 0.0 to 1.0:

| Dimension | Question |
|-----------|----------|
| `arrival` | Can the persona reach this surface? Is the navigation path clear? |
| `orientation` | Does the surface communicate what it is and what the persona can do? |
| `action` | Can the persona perform the intended action? Are controls discoverable and functional? |
| `completion` | Does the action produce the expected outcome? Is success communicated? |
| `confidence` | Does the persona trust the result? Is the system state clear after the action? |

### Scoring Workflow

1. An agent navigates to the surface referenced by `scene.on`.
2. The agent attempts the actions listed in `scene.action`.
3. The agent checks the outcome against `scene.expects`.
4. The agent produces scores for each dimension.
5. Scores are submitted via `rhythm evaluate` with `action: submit_scores`.

### Gap Classification from Scores

Scoring patterns map to gap types for the gaps analysis:

- `arrival < 0.5` and `orientation < 0.5` together suggest the surface is unreachable or confusing — classified as `blocking`.
- `action < 0.5` suggests the interaction is broken — classified as `blocking`.
- `completion < 0.7` suggests the task cannot be reliably finished — classified as `degraded`.
- `confidence < 0.7` with other scores high suggests UX polish issues — classified as `advisory`.
- All dimensions above 0.8 means the scene is healthy and produces no gaps.

### Example

```dsl
# Scene definition in the rhythm
phase onboard:
  kind: onboarding
  scene create_account "Create Account":
    on: registration_form
    action: submit
    entity: User
    expects: "account_created"
    story: ST-001
```

After evaluation, scores might look like:

```
arrival: 0.9, orientation: 0.85, action: 0.7, completion: 0.6, confidence: 0.5
```

This pattern (low completion + low confidence) would produce a `degraded` gap indicating the registration flow works but does not clearly confirm success.

---
