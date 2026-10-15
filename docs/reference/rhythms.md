# Rhythms

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

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
      [on: <surface_name>]                # optional if `story:` is cited (derived)
      [action: <verb1>[, <verb2>, ...]]
      [entity: <EntityName>]
      [expects: "<expected_outcome>"]
      [story: <story_id>]

    # Thin form — surface/action/entity derived from the cited story:
    scene <scene_name> "<Scene Title>":
      story: <story_id>
      [expects: "<expected_outcome>"]

    [scene ...]

  [phase ...]
```

### Properties

| Property | Level | Type | Validated? | Purpose |
|----------|-------|------|-----------|---------|
| `persona:` | rhythm | identifier | Yes — must reference existing persona | Who takes this journey |
| `cadence:` | rhythm | quoted string | No — agent-interpreted | Temporal frequency hint |
| `kind:` | phase | keyword | Yes if present — must be a valid phase kind | Phase lifecycle classification |
| `on:` | scene | identifier | Yes — must reference an existing surface/workspace. Optional when `story:` is cited: the surface is then derived from the story (loud error if ambiguous). | Which surface this scene exercises |
| `action:` | scene | identifier(s) | No — agent-interpreted | What the persona does |
| `entity:` | scene | identifier | Yes if present — must reference existing entity | What data is involved |
| `expects:` | scene | quoted string | No — agent-interpreted | Expected outcome assertion |
| `story:` | scene | identifier | Yes if present — must reference existing story | Link to atomic story |

### Validation Rules

The linker validates structural references at compile time:

1. `rhythm.persona` must match a defined persona
2. `scene.on` must match a defined surface/workspace — or be omitted when `scene.story` is cited, in which case the surface is derived from the story (and a derivation that is ambiguous or has no candidate is a loud link error)
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

The `rhythm(gaps)` step of the `pipeline` quality run identifies missing or weak coverage in the persona journey. It combines static analysis of the AppSpec with any stored scene evaluation.

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

If `.dazzle/evaluations/` holds a scene-evaluation file (`eval-*.json`), the most
recent one adds gaps from its failed dimensions: a failed `action` is a blocking
`capability` gap, a failed `arrival` or `orientation` a degraded `surface` gap, and a
failed `completion` a blocking `workflow` gap.

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
