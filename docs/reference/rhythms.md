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

**Related:** [Stories](stories.md#story), [Processes](processes.md#process), [Personas](ux.md#persona), [Surfaces](surfaces.md)

---
